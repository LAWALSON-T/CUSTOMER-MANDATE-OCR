"""One-off migration for the mandate extraction upgrade. Safe to run more than once.

    docker exec airflow_scheduler python /opt/airflow/scripts/migrate_upgrade.py           (dry run)
    docker exec airflow_scheduler python /opt/airflow/scripts/migrate_upgrade.py --apply

1. MySQL: add the mandate_form_path column (the init SQL only runs on a brand-new volume).
2. MongoDB: remove duplicate customer documents, keeping the best copy of each customer.
3. MongoDB: add a unique index on customer_id so duplicates cannot come back.

Without --apply it only reports what it would do.
"""
import sys

from db_utils import MONGODB_CONFIG, MYSQL_CONFIG, MongoDBConnection, MySQLConnection


def migrate_mysql(apply):
    conn = MySQLConnection(**MYSQL_CONFIG)
    conn.connect()
    try:
        with conn.connection.cursor() as cur:
            cur.execute("""SELECT COUNT(*) AS n FROM information_schema.COLUMNS
                           WHERE TABLE_SCHEMA = %s AND TABLE_NAME = 'customer_mandates'
                           AND COLUMN_NAME = 'mandate_form_path'""", (MYSQL_CONFIG['database'],))
            if cur.fetchone()['n']:
                print("MySQL: mandate_form_path already exists")
                return
            print("MySQL: will add column mandate_form_path VARCHAR(500) NULL")
            if apply:
                cur.execute("ALTER TABLE customer_mandates "
                            "ADD COLUMN mandate_form_path VARCHAR(500) NULL AFTER signature_path")
                conn.connection.commit()
                print("MySQL: column added")
    finally:
        conn.close()


def keep_rank(doc):
    """Which copy to keep: the one with the most documents, then the most recently processed."""
    processed = (doc.get('metadata') or {}).get('processed_at') or ''
    return (len(doc.get('documents') or []), processed, doc['_id'].generation_time)


def migrate_mongo(apply):
    mongo = MongoDBConnection(**MONGODB_CONFIG)
    mongo.connect()
    coll = mongo.db['customer_mandates']
    try:
        dupes = list(coll.aggregate([
            {'$group': {'_id': '$customer_id', 'ids': {'$push': '$_id'}, 'n': {'$sum': 1}}},
            {'$match': {'n': {'$gt': 1}}},
        ]))
        to_delete = []
        for group in dupes:
            docs = list(coll.find({'_id': {'$in': group['ids']}},
                                  {'documents.binary_data': 0}))  # no need to load the files
            docs.sort(key=keep_rank, reverse=True)
            keep, drop = docs[0], docs[1:]
            print(f"MongoDB: {group['_id']}: keep {keep['_id']} "
                  f"({len(keep.get('documents') or [])} docs), drop {len(drop)} older/emptier copy(ies)")
            to_delete += [d['_id'] for d in drop]

        if not dupes:
            print("MongoDB: no duplicate customers")
        elif apply:
            result = coll.delete_many({'_id': {'$in': to_delete}})
            print(f"MongoDB: deleted {result.deleted_count} duplicate document(s)")

        if apply:
            mongo.ensure_indexes()
            print("MongoDB: unique index on customer_id in place")
        else:
            print("MongoDB: will create a unique index on customer_id")
    finally:
        mongo.close()


if __name__ == '__main__':
    apply = '--apply' in sys.argv
    print("APPLYING CHANGES" if apply else "DRY RUN: nothing will change (add --apply to make changes)")
    migrate_mysql(apply)
    migrate_mongo(apply)
