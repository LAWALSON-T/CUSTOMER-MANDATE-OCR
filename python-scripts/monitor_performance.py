"""
Monitor ETL performance in real-time
"""
import time
from db_utils import MySQLConnection, MongoDBConnection, MYSQL_CONFIG, MONGODB_CONFIG

def monitor():
    mysql_conn = MySQLConnection(**MYSQL_CONFIG)
    mongo_conn = MongoDBConnection(**MONGODB_CONFIG)
    
    mysql_conn.connect()
    mongo_conn.connect()
    
    start_time = time.time()
    last_count = 0
    
    print("=" * 80)
    print("ETL Performance Monitor")
    print("=" * 80)
    print(f"{'Time':<12} {'Processed':<12} {'Rate/sec':<12} {'Status':<30}")
    print("-" * 80)
    
    try:
        while True:
            # Get counts
            with mysql_conn.connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM customer_mandates WHERE status='processed'")
                processed = cursor.fetchone()['count']
            
            mongo_count = mongo_conn.count_documents()
            
            elapsed = time.time() - start_time
            rate = (processed - last_count) / 5 if elapsed > 0 else 0
            
            print(f"{int(elapsed):<12} {processed:<12} {rate:<12.2f} MySQL:{processed} | Mongo:{mongo_count}")
            
            last_count = processed
            
            # Check if done
            if processed >= 1005:
                print("\n" + "=" * 80)
                print(f"✓ COMPLETE! Processed all 1005 customers in {elapsed:.2f} seconds")
                print(f"✓ Average rate: {1005/elapsed:.2f} customers/second")
                print("=" * 80)
                break
            
            time.sleep(5)  # Update every 5 seconds
            
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped")
    finally:
        mysql_conn.close()
        mongo_conn.close()

if __name__ == "__main__":
    monitor()