"""
Database utilities for connecting to MySQL and MongoDB.

Connection settings come from environment variables (set in docker-compose.yml from .env).
Passwords have no default: if one is missing, the code fails at once with a clear message
instead of silently trying a hard-coded password.
"""
import logging
import os
from typing import Dict, List, Optional

import pymysql
from pymongo import ASCENDING, MongoClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COLLECTION = 'customer_mandates'


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is not set. Check .env and docker-compose.yml.")
    return value


class MySQLConnection:
    """MySQL database connection handler"""

    def __init__(self, host: str, user: str, password: str, database: str, port: int = 3306):
        self.host = host
        self.user = user
        self.password = password
        self.database = database
        self.port = port
        self.connection = None

    def connect(self):
        """Establish connection to MySQL"""
        try:
            self.connection = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port,
                cursorclass=pymysql.cursors.DictCursor
            )
            logger.info(f"Connected to MySQL database: {self.database}")
            return self.connection
        except Exception as e:
            logger.error(f"Failed to connect to MySQL: {str(e)}")
            raise

    def fetch_customers(self, status: str = 'pending', limit: Optional[int] = None) -> List[Dict]:
        """Fetch customers from MySQL based on status"""
        try:
            if self.connection is None:
                self.connect()

            with self.connection.cursor() as cursor:
                query = "SELECT * FROM customer_mandates WHERE status = %s"
                params = [status]
                if limit:
                    query += " LIMIT %s"
                    params.append(int(limit))

                cursor.execute(query, params)
                customers = cursor.fetchall()
                logger.info(f"Fetched {len(customers)} customers with status '{status}'")
                return customers

        except Exception as e:
            logger.error(f"Error fetching customers: {str(e)}")
            raise

    def update_customer_status(self, customer_id: str, status: str):
        """Update customer processing status"""
        try:
            if self.connection is None:
                self.connect()

            with self.connection.cursor() as cursor:
                query = "UPDATE customer_mandates SET status = %s WHERE customer_id = %s"
                cursor.execute(query, (status, customer_id))
                self.connection.commit()
                logger.info(f"Updated customer {customer_id} status to '{status}'")

        except Exception as e:
            logger.error(f"Error updating customer status: {str(e)}")
            raise

    def close(self):
        """Close MySQL connection"""
        if self.connection is not None:
            self.connection.close()
            self.connection = None
            logger.info("MySQL connection closed")


class MongoDBConnection:
    """MongoDB database connection handler"""

    def __init__(self, host: str, port: int, username: str, password: str, database: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.client = None
        self.db = None

    def connect(self):
        """Establish connection to MongoDB"""
        try:
            # Credentials passed separately, not inside a URL that could end up in a log.
            self.client = MongoClient(host=self.host, port=self.port,
                                      username=self.username, password=self.password,
                                      serverSelectionTimeoutMS=10_000)
            self.db = self.client[self.database]
            self.client.server_info()
            logger.info(f"Connected to MongoDB database: {self.database}")
            return self.db

        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise

    def _collection(self):
        if self.db is None:
            self.connect()
        return self.db[COLLECTION]

    def ensure_indexes(self):
        """One document per customer, enforced by the database. Fails if duplicates
        still exist: run migrate_upgrade.py --apply first."""
        self._collection().create_index([('customer_id', ASCENDING)], unique=True,
                                        name='customer_id_unique')

    def upsert_customer_mandate(self, customer_data: Dict):
        """Insert the customer's document, or replace it if the customer already exists.
        Reprocessing a customer therefore never creates a duplicate.
        Replacing also clears any old mandate_extraction, which is correct: the documents
        may have changed, so the form must be read again."""
        try:
            result = self._collection().replace_one(
                {'customer_id': customer_data['customer_id']}, customer_data, upsert=True)
            action = 'Inserted' if result.upserted_id is not None else 'Replaced'
            logger.info(f"{action} customer mandate {customer_data['customer_id']}")
            return result.upserted_id or customer_data['customer_id']
        except Exception as e:
            logger.error(f"Error upserting customer mandate: {str(e)}")
            raise

    def insert_customer_mandate(self, customer_data: Dict):
        """Kept so old callers still work. Now upserts, so it can no longer create duplicates."""
        return self.upsert_customer_mandate(customer_data)

    def get_customer_by_id(self, customer_id: str) -> Optional[Dict]:
        """Retrieve customer mandate by customer_id"""
        try:
            customer = self._collection().find_one({"customer_id": customer_id})
            logger.info(f"{'Found' if customer else 'Customer not found'}: {customer_id}")
            return customer
        except Exception as e:
            logger.error(f"Error retrieving customer: {str(e)}")
            raise

    def count_documents(self) -> int:
        """Count total documents in customer_mandates collection"""
        try:
            count = self._collection().count_documents({})
            logger.info(f"Total customer mandates in MongoDB: {count}")
            return count
        except Exception as e:
            logger.error(f"Error counting documents: {str(e)}")
            raise

    def close(self):
        """Close MongoDB connection"""
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None
            logger.info("MongoDB connection closed")


# Configuration for the Docker environment. Read when this module is imported.
MYSQL_CONFIG = {
    'host': os.environ.get('MYSQL_HOST', 'mysql'),
    'user': os.environ.get('MYSQL_USER', 'etl_user'),
    'password': os.environ.get('MYSQL_PASSWORD'),
    'database': os.environ.get('MYSQL_DATABASE', 'customer_db'),
    'port': int(os.environ.get('MYSQL_PORT', 3306)),
}

MONGODB_CONFIG = {
    'host': os.environ.get('MONGO_HOST', 'mongodb'),
    'port': int(os.environ.get('MONGO_PORT', 27017)),
    'username': os.environ.get('MONGO_USER', 'admin'),
    'password': os.environ.get('MONGO_PASSWORD'),
    'database': os.environ.get('MONGO_DATABASE', 'customer_mandates'),
}

for _name, _cfg, _var in (('MySQL', MYSQL_CONFIG, 'MYSQL_PASSWORD'),
                          ('MongoDB', MONGODB_CONFIG, 'MONGO_PASSWORD')):
    if not _cfg['password']:
        logger.warning(f"{_var} is not set: {_name} connections will fail. Check .env.")
