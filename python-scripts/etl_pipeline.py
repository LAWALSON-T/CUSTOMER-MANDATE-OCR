"""
ETL Pipeline for Customer Mandate Processing
Extracts data from MySQL, converts documents to binary, loads to MongoDB.

Source status after a run:
    processed   loaded with every document the row points to
    incomplete  loaded, but at least one referenced file was missing or unreadable
    failed      not loaded
"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image

from db_utils import MySQLConnection, MongoDBConnection, MYSQL_CONFIG, MONGODB_CONFIG

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# (column holding the path, category, type, or column holding the type)
DOCUMENT_COLUMNS = [
    ('id_document_path', 'identification', None),            # type comes from id_document_type
    ('proof_of_address_path', 'proof_of_address', 'address_verification'),
    ('signature_path', 'signature', 'customer_signature'),
    ('mandate_form_path', 'mandate_form', 'account_mandate'),  # read by extract_mandate_forms
]

# Each batch removes its rows from 'pending'. If that ever stops happening, this cap
# ends the run instead of reprocessing the same rows forever.
MAX_BATCHES_PER_RUN = 500


class DocumentProcessor:
    """Handle document reading and conversion to binary"""

    def __init__(self, base_path: str = "/opt/airflow/source_files"):
        self.base_path = base_path

    def read_file_to_binary(self, file_path: str) -> Optional[bytes]:
        """Read file and return as binary data"""
        try:
            full_path = os.path.join(self.base_path, file_path.lstrip('/'))

            if not os.path.exists(full_path):
                logger.warning(f"File not found: {full_path}")
                return None

            with open(full_path, 'rb') as file:
                binary_data = file.read()

            logger.info(f"Read file: {file_path} ({len(binary_data)} bytes)")
            return binary_data

        except Exception as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            return None

    def get_file_metadata(self, file_path: str) -> Dict:
        """Extract file metadata"""
        try:
            full_path = os.path.join(self.base_path, file_path.lstrip('/'))

            if not os.path.exists(full_path):
                return {}

            file_stat = os.stat(full_path)
            file_extension = Path(full_path).suffix.lower()

            metadata = {
                'filename': os.path.basename(file_path),
                'file_type': file_extension,
                'file_size': file_stat.st_size,
                'original_path': file_path
            }

            if file_extension in ['.jpg', '.jpeg', '.png', '.gif']:
                try:
                    with Image.open(full_path) as img:
                        metadata['width'] = img.width
                        metadata['height'] = img.height
                        metadata['format'] = img.format
                except Exception as e:
                    logger.warning(f"Could not extract image metadata: {str(e)}")

            return metadata

        except Exception as e:
            logger.error(f"Error getting file metadata: {str(e)}")
            return {}


class CustomerMandateETL:
    """Main ETL class for customer mandate processing"""

    def __init__(self):
        self.mysql_conn = MySQLConnection(**MYSQL_CONFIG)
        self.mongo_conn = MongoDBConnection(**MONGODB_CONFIG)
        self.doc_processor = DocumentProcessor()

    def extract_customers(self, status: str = 'pending', limit: Optional[int] = None) -> List[Dict]:
        """Extract customer data from MySQL. Reuses the open connection."""
        logger.info(f"Starting extraction of customers with status: {status}")
        if self.mysql_conn.connection is None:
            self.mysql_conn.connect()
        customers = self.mysql_conn.fetch_customers(status=status, limit=limit)
        logger.info(f"Extracted {len(customers)} customers")
        return customers

    def transform_customer_data(self, customer: Dict) -> Dict:
        """Transform customer data and add binary documents.
        Records every referenced file that could not be read in metadata.missing_documents."""
        logger.info(f"Transforming data for customer: {customer['customer_id']}")

        transformed_data = {
            'customer_id': customer['customer_id'],
            'personal_info': {
                'first_name': customer['first_name'],
                'last_name': customer['last_name'],
                'email': customer['email'],
                'phone_number': customer['phone_number'],
                'date_of_birth': customer['date_of_birth'].isoformat() if customer['date_of_birth'] else None,
            },
            'address': {
                'street': customer['address'],
                'city': customer['city'],
                'state': customer['state'],
                'country': customer['country'],
                'postal_code': customer['postal_code']
            },
            'documents': [],
            'metadata': {
                'source_created_at': customer['created_at'].isoformat() if customer['created_at'] else None,
                'source_updated_at': customer['updated_at'].isoformat() if customer['updated_at'] else None,
                'processed_at': datetime.utcnow().isoformat(),
                'missing_documents': [],
            }
        }

        for column, category, doc_type in DOCUMENT_COLUMNS:
            path = customer.get(column)  # .get: mandate_form_path may not exist before migration
            if not path:
                continue
            doc = self._process_document(path, category, doc_type or customer.get('id_document_type'))
            if doc:
                transformed_data['documents'].append(doc)
            else:
                transformed_data['metadata']['missing_documents'].append(
                    {'category': category, 'path': path})

        missing = transformed_data['metadata']['missing_documents']
        transformed_data['metadata']['processing_status'] = 'incomplete' if missing else 'processed'
        logger.info(f"Transformation complete for {customer['customer_id']}: "
                    f"{len(transformed_data['documents'])} documents, {len(missing)} missing")
        return transformed_data

    def _process_document(self, file_path: str, doc_category: str, doc_type: str) -> Optional[Dict]:
        """Process a single document: read binary, extract metadata"""
        try:
            binary_data = self.doc_processor.read_file_to_binary(file_path)
            if not binary_data:
                return None

            return {
                'category': doc_category,
                'type': doc_type,
                'binary_data': binary_data,
                'metadata': self.doc_processor.get_file_metadata(file_path),
                'uploaded_at': datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error processing document {file_path}: {str(e)}")
            return None

    def load_to_mongodb(self, customer_data: Dict) -> bool:
        """Load transformed customer data to MongoDB. Upserts: reprocessing never duplicates."""
        try:
            logger.info(f"Loading customer {customer_data['customer_id']} to MongoDB")
            self.mongo_conn.upsert_customer_mandate(customer_data)
            logger.info(f"Successfully loaded customer {customer_data['customer_id']}")
            return True
        except Exception as e:
            logger.error(f"Failed to load customer to MongoDB: {str(e)}")
            return False

    def update_source_status(self, customer_id: str, status: str):
        """Update status in source MySQL. Errors are NOT swallowed: if the status cannot be
        written, the row stays 'pending' and would be fetched again, so the run must stop."""
        self.mysql_conn.update_customer_status(customer_id, status)

    def process_customer(self, customer: Dict) -> str:
        """Process one customer. Returns the status written back to MySQL."""
        customer_id = customer['customer_id']
        try:
            transformed_data = self.transform_customer_data(customer)
            loaded = self.load_to_mongodb(transformed_data)
            status = transformed_data['metadata']['processing_status'] if loaded else 'failed'
        except Exception as e:
            logger.error(f"Error processing customer {customer_id}: {str(e)}")
            status = 'failed'
        self.update_source_status(customer_id, status)
        return status

    def run_pipeline(self, batch_size: int = 100) -> Dict[str, int]:
        """Process every pending customer, one batch at a time. Returns counts by status."""
        logger.info("=" * 50)
        logger.info("Starting Customer Mandate ETL Pipeline")
        logger.info(f"Batch size: {batch_size}")
        logger.info("=" * 50)

        start_time = datetime.utcnow()
        totals = {'processed': 0, 'incomplete': 0, 'failed': 0}

        try:
            self.mysql_conn.connect()
            self.mongo_conn.connect()   # once per run, not once per customer

            for batch_number in range(1, MAX_BATCHES_PER_RUN + 1):
                customers = self.extract_customers(status='pending', limit=batch_size)
                if not customers:
                    logger.info("No more pending customers to process")
                    break

                logger.info(f"Processing batch {batch_number}: {len(customers)} customers")
                for customer in customers:
                    totals[self.process_customer(customer)] += 1

                if len(customers) < batch_size:
                    break
            else:
                logger.warning(f"Stopped after {MAX_BATCHES_PER_RUN} batches; "
                               "remaining customers will be picked up by the next run")

            duration = (datetime.utcnow() - start_time).total_seconds()
            total = sum(totals.values())
            logger.info("=" * 50)
            logger.info("ETL Pipeline Complete")
            logger.info(f"Total customers: {total}  {totals}")
            logger.info(f"Duration: {duration:.2f} seconds")
            if duration > 0:
                logger.info(f"Throughput: {total / duration:.2f} customers/sec")
            logger.info("=" * 50)
            return totals

        except Exception as e:
            logger.error(f"Pipeline error: {str(e)}")
            raise

        finally:
            self.mysql_conn.close()
            self.mongo_conn.close()


if __name__ == "__main__":
    etl = CustomerMandateETL()
    etl.run_pipeline()
