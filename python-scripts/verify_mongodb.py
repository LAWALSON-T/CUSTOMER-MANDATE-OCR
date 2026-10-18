"""
Verify and display customer mandate data from MongoDB
"""
from db_utils import MongoDBConnection, MONGODB_CONFIG
import json
from datetime import datetime


def verify_mongodb_data():
    """Connect to MongoDB and display customer mandate data"""
    
    print("=" * 70)
    print("MongoDB Data Verification")
    print("=" * 70)
    print()
    
    # Connect to MongoDB
    mongo_conn = MongoDBConnection(**MONGODB_CONFIG)
    mongo_conn.connect()
    
    # Get total count
    total_count = mongo_conn.count_documents()
    print(f"Total Customer Mandates in MongoDB: {total_count}")
    print()
    
    if total_count == 0:
        print("No customer mandates found in MongoDB.")
        print("Run the ETL pipeline first to load data.")
        return
    
    # Get all customers
    collection = mongo_conn.db['customer_mandates']
    customers = collection.find()
    
    print("=" * 70)
    print("Customer Mandate Details")
    print("=" * 70)
    print()
    
    for idx, customer in enumerate(customers, 1):
        print(f"\n{'─' * 70}")
        print(f"Customer #{idx}: {customer['customer_id']}")
        print(f"{'─' * 70}")
        
        # Personal Info
        print("\n📋 Personal Information:")
        personal = customer.get('personal_info', {})
        print(f"   Name: {personal.get('first_name')} {personal.get('last_name')}")
        print(f"   Email: {personal.get('email')}")
        print(f"   Phone: {personal.get('phone_number')}")
        print(f"   DOB: {personal.get('date_of_birth')}")
        
        # Address
        print("\n🏠 Address:")
        address = customer.get('address', {})
        print(f"   {address.get('street')}")
        print(f"   {address.get('city')}, {address.get('state')} {address.get('postal_code')}")
        print(f"   {address.get('country')}")
        
        # Documents
        documents = customer.get('documents', [])
        print(f"\n📁 Documents ({len(documents)} files):")
        
        total_size = 0
        for doc in documents:
            metadata = doc.get('metadata', {})
            filename = metadata.get('filename', 'Unknown')
            file_size = metadata.get('file_size', 0)
            file_type = metadata.get('file_type', 'Unknown')
            category = doc.get('category', 'Unknown')
            doc_type = doc.get('type', 'Unknown')
            
            # Convert binary data size
            binary_size = len(doc.get('binary_data', b''))
            total_size += binary_size
            
            size_kb = binary_size / 1024
            
            print(f"   • {filename}")
            print(f"     Category: {category}")
            print(f"     Type: {doc_type}")
            print(f"     File Type: {file_type}")
            print(f"     Binary Size: {size_kb:.2f} KB")
            
            # Check if image has dimensions
            if 'width' in metadata and 'height' in metadata:
                print(f"     Dimensions: {metadata['width']}x{metadata['height']}")
        
        total_size_kb = total_size / 1024
        print(f"\n   Total Documents Size: {total_size_kb:.2f} KB")
        
        # Metadata
        print("\n⏱️  Processing Metadata:")
        metadata = customer.get('metadata', {})
        print(f"   Processed At: {metadata.get('processed_at')}")
        print(f"   Status: {metadata.get('processing_status')}")
    
    print("\n" + "=" * 70)
    print("Verification Complete")
    print("=" * 70)
    
    # Close connection
    mongo_conn.close()


def export_customer_sample(customer_id: str):
    """Export a single customer record to JSON (without binary data for readability)"""
    
    mongo_conn = MongoDBConnection(**MONGODB_CONFIG)
    mongo_conn.connect()
    
    customer = mongo_conn.get_customer_by_id(customer_id)
    
    if customer:
        # Remove binary data for JSON export
        export_data = customer.copy()
        
        # Replace binary data with size info
        if 'documents' in export_data:
            for doc in export_data['documents']:
                if 'binary_data' in doc:
                    binary_size = len(doc['binary_data'])
                    doc['binary_data'] = f"<Binary data: {binary_size} bytes>"
        
        # Remove MongoDB _id
        export_data.pop('_id', None)
        
        # Save to file
        output_file = f"{customer_id}_export.json"
        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2)
        
        print(f"Exported customer {customer_id} to {output_file}")
    else:
        print(f"Customer {customer_id} not found")
    
    mongo_conn.close()


if __name__ == "__main__":
    verify_mongodb_data()
    
    # Optional: Export first customer to JSON file
    # export_customer_sample("CUST001")
