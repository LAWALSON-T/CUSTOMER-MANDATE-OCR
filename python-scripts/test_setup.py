"""
Comprehensive test script to validate the ETL pipeline setup
"""
import sys
import os

# Add scripts to path
sys.path.insert(0, '/opt/airflow/scripts')

from db_utils import MySQLConnection, MongoDBConnection, MYSQL_CONFIG, MONGODB_CONFIG
from etl_pipeline import CustomerMandateETL


def test_mysql_connection():
    """Test MySQL database connection"""
    print("\n" + "="*60)
    print("TEST 1: MySQL Connection")
    print("="*60)
    
    try:
        mysql_conn = MySQLConnection(**MYSQL_CONFIG)
        mysql_conn.connect()
        print("✓ MySQL connection successful")
        
        # Test query
        customers = mysql_conn.fetch_customers(status='pending', limit=1)
        print(f"✓ Query successful - Found {len(customers)} pending customer(s)")
        
        mysql_conn.close()
        print("✓ MySQL connection closed")
        return True
        
    except Exception as e:
        print(f"✗ MySQL test failed: {str(e)}")
        return False


def test_mongodb_connection():
    """Test MongoDB database connection"""
    print("\n" + "="*60)
    print("TEST 2: MongoDB Connection")
    print("="*60)
    
    try:
        mongo_conn = MongoDBConnection(**MONGODB_CONFIG)
        mongo_conn.connect()
        print("✓ MongoDB connection successful")
        
        # Test query
        count = mongo_conn.count_documents()
        print(f"✓ Query successful - Current document count: {count}")
        
        mongo_conn.close()
        print("✓ MongoDB connection closed")
        return True
        
    except Exception as e:
        print(f"✗ MongoDB test failed: {str(e)}")
        return False


def test_file_access():
    """Test access to customer document files"""
    print("\n" + "="*60)
    print("TEST 3: File System Access")
    print("="*60)
    
    try:
        base_path = "/opt/airflow/source_files/customer_documents"
        
        if not os.path.exists(base_path):
            print(f"✗ Directory not found: {base_path}")
            return False
        
        files = os.listdir(base_path)
        print(f"✓ Directory accessible: {base_path}")
        print(f"✓ Found {len(files)} files")
        
        # Check for specific files
        test_files = [
            "CUST001_passport.pdf",
            "CUST001_signature.png",
            "CUST002_drivers_license.jpg"
        ]
        
        for test_file in test_files:
            file_path = os.path.join(base_path, test_file)
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                print(f"✓ File exists: {test_file} ({file_size} bytes)")
            else:
                print(f"✗ File missing: {test_file}")
                return False
        
        return True
        
    except Exception as e:
        print(f"✗ File access test failed: {str(e)}")
        return False


def test_data_extraction():
    """Test customer data extraction from MySQL"""
    print("\n" + "="*60)
    print("TEST 4: Data Extraction")
    print("="*60)
    
    try:
        etl = CustomerMandateETL()
        customers = etl.extract_customers(status='pending', limit=1)
        
        if not customers:
            print("✗ No customers found to extract")
            etl.mysql_conn.close()
            return False
        
        print(f"✓ Extracted {len(customers)} customer(s)")
        
        # Validate customer structure
        customer = customers[0]
        required_fields = ['customer_id', 'first_name', 'last_name', 'email']
        
        for field in required_fields:
            if field in customer:
                print(f"✓ Field present: {field}")
            else:
                print(f"✗ Missing field: {field}")
                etl.mysql_conn.close()
                return False
        
        print(f"✓ Sample customer: {customer['customer_id']} - {customer['first_name']} {customer['last_name']}")
        
        etl.mysql_conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Data extraction test failed: {str(e)}")
        return False


def test_transformation():
    """Test data transformation logic"""
    print("\n" + "="*60)
    print("TEST 5: Data Transformation")
    print("="*60)
    
    try:
        etl = CustomerMandateETL()
        customers = etl.extract_customers(status='pending', limit=1)
        
        if not customers:
            print("✗ No customers available for transformation test")
            etl.mysql_conn.close()
            return False
        
        customer = customers[0]
        print(f"✓ Testing transformation for: {customer['customer_id']}")
        
        # Transform
        transformed = etl.transform_customer_data(customer)
        
        # Validate transformed structure
        if 'customer_id' not in transformed:
            print("✗ Missing customer_id in transformed data")
            etl.mysql_conn.close()
            return False
        
        print("✓ customer_id present")
        
        if 'personal_info' not in transformed:
            print("✗ Missing personal_info in transformed data")
            etl.mysql_conn.close()
            return False
        
        print("✓ personal_info present")
        
        if 'documents' not in transformed:
            print("✗ Missing documents in transformed data")
            etl.mysql_conn.close()
            return False
        
        doc_count = len(transformed['documents'])
        print(f"✓ documents present ({doc_count} documents)")
        
        # Validate document structure
        if doc_count > 0:
            doc = transformed['documents'][0]
            if 'binary_data' in doc:
                binary_size = len(doc['binary_data'])
                print(f"✓ Binary data present ({binary_size} bytes)")
            else:
                print("✗ Binary data missing from document")
                etl.mysql_conn.close()
                return False
        
        etl.mysql_conn.close()
        return True
        
    except Exception as e:
        print(f"✗ Transformation test failed: {str(e)}")
        return False


def test_end_to_end():
    """Test complete end-to-end ETL process"""
    print("\n" + "="*60)
    print("TEST 6: End-to-End ETL Pipeline")
    print("="*60)
    
    try:
        # First, reset one customer to pending for testing
        print("Preparing test data...")
        mysql_conn = MySQLConnection(**MYSQL_CONFIG)
        mysql_conn.connect()
        
        # Get a processed customer and reset to pending
        with mysql_conn.connection.cursor() as cursor:
            cursor.execute("SELECT customer_id FROM customer_mandates WHERE status='processed' LIMIT 1")
            result = cursor.fetchone()
            
            if result:
                test_customer_id = result['customer_id']
                cursor.execute("UPDATE customer_mandates SET status='pending' WHERE customer_id=%s", (test_customer_id,))
                mysql_conn.connection.commit()
                print(f"✓ Reset customer {test_customer_id} to pending status")
            else:
                # If no processed customers, use a pending one
                cursor.execute("SELECT customer_id FROM customer_mandates WHERE status='pending' LIMIT 1")
                result = cursor.fetchone()
                if result:
                    test_customer_id = result['customer_id']
                    print(f"✓ Using pending customer {test_customer_id}")
                else:
                    print("✗ No customers available for testing")
                    mysql_conn.close()
                    return False
        
        mysql_conn.close()
        
        # Run the ETL pipeline
        print("\nRunning ETL pipeline...")
        etl = CustomerMandateETL()
        etl.run_pipeline(batch_size=1)
        
        # Verify in MongoDB
        print("\nVerifying data in MongoDB...")
        mongo_conn = MongoDBConnection(**MONGODB_CONFIG)
        mongo_conn.connect()
        
        customer = mongo_conn.get_customer_by_id(test_customer_id)
        
        if customer:
            print(f"✓ Customer {test_customer_id} found in MongoDB")
            print(f"✓ Document count: {len(customer.get('documents', []))}")
            print("✓ End-to-end test PASSED")
            mongo_conn.close()
            return True
        else:
            print(f"✗ Customer {test_customer_id} not found in MongoDB")
            mongo_conn.close()
            return False
        
    except Exception as e:
        print(f"✗ End-to-end test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests and generate report"""
    print("\n" + "="*60)
    print("CUSTOMER MANDATE ETL PIPELINE - TEST SUITE")
    print("="*60)
    
    tests = [
        ("MySQL Connection", test_mysql_connection),
        ("MongoDB Connection", test_mongodb_connection),
        ("File System Access", test_file_access),
        ("Data Extraction", test_data_extraction),
        ("Data Transformation", test_transformation),
        ("End-to-End Pipeline", test_end_to_end),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ Test '{test_name}' crashed: {str(e)}")
            results.append((test_name, False))
    
    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} - {test_name}")
    
    print("="*60)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ All tests PASSED! System is ready.")
    else:
        print("✗ Some tests FAILED. Please review the errors above.")
    
    print("="*60)
    
    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
