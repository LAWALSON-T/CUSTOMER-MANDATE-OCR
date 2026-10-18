"""
Airflow DAG for the Customer Mandate ETL pipeline.

check connections -> extract -> load (run_etl_pipeline) -> extract mandate forms -> verify -> report
"""
import os
import sys
from datetime import datetime, timedelta

import pymysql
from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.python import PythonOperator

sys.path.insert(0, '/opt/airflow/scripts')

from etl_pipeline import CustomerMandateETL  # noqa: E402
from db_utils import MySQLConnection, MongoDBConnection, MYSQL_CONFIG, MONGODB_CONFIG  # noqa: E402
from mandate_extraction_task import mongo_collection, run_extraction  # noqa: E402

default_args = {
    'owner': 'data_engineer',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

dag = DAG(
    'customer_mandate_etl',
    default_args=default_args,
    description='ETL pipeline for customer mandate processing, with mandate form extraction',
    schedule_interval=timedelta(hours=1),
    catchup=False,
    tags=['etl', 'customer', 'mandate'],
)


def check_source_connection():
    print("Checking MySQL source connection...")
    mysql_conn = MySQLConnection(**MYSQL_CONFIG)
    mysql_conn.connect()
    customers = mysql_conn.fetch_customers(status='pending', limit=1)
    mysql_conn.close()
    print(f"MySQL connection successful. Found {len(customers)} pending customer(s)")
    return True


def check_target_connection():
    print("Checking MongoDB target connection...")
    mongo_conn = MongoDBConnection(**MONGODB_CONFIG)
    mongo_conn.connect()
    count = mongo_conn.count_documents()
    mongo_conn.close()
    print(f"MongoDB connection successful. Current document count: {count}")
    return True


def extract_customers(**context):
    print("Extracting customers from MySQL...")
    etl = CustomerMandateETL()
    customers = etl.extract_customers(status='pending')
    etl.mysql_conn.close()
    context['ti'].xcom_push(key='customer_count', value=len(customers))
    print(f"Extracted {len(customers)} customers")
    return len(customers)


def run_etl_pipeline(**context):
    print("Starting ETL pipeline...")
    etl = CustomerMandateETL()
    totals = etl.run_pipeline(batch_size=10)  # loops in batches of 10 until nothing is pending
    context['ti'].xcom_push(key='load_totals', value=totals)
    print(f"ETL pipeline completed: {totals}")
    return totals


def extract_mandate_forms(**context):
    """Read every newly loaded mandate form. Skipped, not failed, if no API key is configured,
    so the rest of the ETL keeps working without it."""
    if not os.environ.get('ANTHROPIC_API_KEY'):
        raise AirflowSkipException("ANTHROPIC_API_KEY not set; mandate extraction skipped")
    counts = run_extraction()
    context['ti'].xcom_push(key='extraction_counts', value=counts)
    return counts


def verify_load(**context):
    """Compare the source and the target instead of only counting documents."""
    conn = pymysql.connect(host=os.environ.get('MYSQL_HOST', 'mysql'),
                           user=os.environ['MYSQL_USER'], password=os.environ['MYSQL_PASSWORD'],
                           database=os.environ.get('MYSQL_DATABASE', 'customer_db'))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT status, COUNT(*) FROM customer_mandates GROUP BY status")
            by_status = {status: n for status, n in cur.fetchall()}
    finally:
        conn.close()

    client, coll = mongo_collection()
    try:
        total_docs = coll.count_documents({})
        distinct_customers = len(coll.distinct('customer_id'))
        extraction = {s: coll.count_documents({'mandate_extraction.status': s})
                      for s in ('auto_accept', 'needs_review', 'error')}
        extraction['not_yet_extracted'] = coll.count_documents(
            {'documents.category': 'mandate_form', 'mandate_extraction': {'$exists': False}})
    finally:
        client.close()

    stats = {
        'mysql_by_status': by_status,
        'mongo_documents': total_docs,
        'mongo_distinct_customers': distinct_customers,
        'mongo_duplicates': total_docs - distinct_customers,
        'extraction': extraction,
    }
    print(stats)
    context['ti'].xcom_push(key='stats', value=stats)

    # Every customer marked loaded in MySQL must exist in MongoDB. Anything else is lost data.
    loaded = by_status.get('processed', 0) + by_status.get('incomplete', 0)
    if distinct_customers < loaded:
        raise ValueError(f"{loaded} customers marked processed/incomplete in MySQL, "
                         f"but only {distinct_customers} found in MongoDB")
    return stats


def generate_report(**context):
    ti = context['ti']
    customer_count = ti.xcom_pull(key='customer_count', task_ids='extract_customers') or 0
    stats = ti.xcom_pull(key='stats', task_ids='verify_load') or {}
    run = ti.xcom_pull(key='extraction_counts', task_ids='extract_mandate_forms')
    load_totals = ti.xcom_pull(key='load_totals', task_ids='run_etl_pipeline')

    problems = []
    if stats.get('mongo_duplicates'):
        problems.append(f"{stats['mongo_duplicates']} duplicate customer document(s) in MongoDB")
    if stats.get('mysql_by_status', {}).get('failed'):
        problems.append(f"{stats['mysql_by_status']['failed']} customer(s) failed to load")
    if stats.get('mysql_by_status', {}).get('incomplete'):
        problems.append(f"{stats['mysql_by_status']['incomplete']} customer(s) loaded with missing documents")
    ext = stats.get('extraction', {})
    if ext.get('needs_review'):
        problems.append(f"{ext['needs_review']} mandate form(s) waiting for human review")
    if ext.get('error'):
        problems.append(f"{ext['error']} mandate form(s) failed extraction")

    report = f"""
    ===================================================
    Customer Mandate ETL Pipeline - Execution Report
    ===================================================
    Execution Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

    Load
    - Pending customers at start of run: {customer_count}
    - This run: {load_totals}
    - MySQL by status: {stats.get('mysql_by_status')}
    - MongoDB documents: {stats.get('mongo_documents')} for {stats.get('mongo_distinct_customers')} customers

    Mandate form extraction
    - This run: {run if run is not None else 'skipped'}
    - All time: {ext}

    Status: {'OK' if not problems else 'ATTENTION NEEDED'}
    {chr(10).join('    - ' + p for p in problems)}
    ===================================================
    """
    print(report)
    return report


task_check_mysql = PythonOperator(task_id='check_mysql_connection',
                                  python_callable=check_source_connection, dag=dag)
task_check_mongodb = PythonOperator(task_id='check_mongodb_connection',
                                    python_callable=check_target_connection, dag=dag)
task_extract = PythonOperator(task_id='extract_customers', python_callable=extract_customers, dag=dag)
task_run_etl = PythonOperator(task_id='run_etl_pipeline', python_callable=run_etl_pipeline, dag=dag)
task_extract_forms = PythonOperator(task_id='extract_mandate_forms',
                                    python_callable=extract_mandate_forms, dag=dag)
# none_failed: still verify and report when extraction was skipped
task_verify = PythonOperator(task_id='verify_load', python_callable=verify_load,
                             trigger_rule='none_failed', dag=dag)
task_report = PythonOperator(task_id='generate_report', python_callable=generate_report,
                             trigger_rule='all_done', dag=dag)

[task_check_mysql, task_check_mongodb] >> task_extract
task_extract >> task_run_etl >> task_extract_forms >> task_verify >> task_report
