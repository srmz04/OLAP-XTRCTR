import os
import sys
import json
import adodbapi
import psycopg2
import argparse
from datetime import datetime

def run_job(job_id):
    print(f"🚀 Starting job runner for ID: {job_id}")
    
    # 1. Connect to Postgres
    try:
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            raise ValueError("DATABASE_URL env var missing")
            
        conn_pg = psycopg2.connect(db_url)
        cur_pg = conn_pg.cursor()
        print("✅ Connected to PostgreSQL")
    except Exception as e:
        print(f"❌ Failed to connect to DB: {e}")
        sys.exit(1)

    try:
        # 2. Get Job Details
        cur_pg.execute("SELECT mdx_query, catalog_code FROM jobs WHERE id = %s", (job_id,))
        job = cur_pg.fetchone()
        
        if not job:
            print(f"❌ Job {job_id} not found in database")
            sys.exit(1)

        mdx_query, catalog = job
        print(f"📋 Job found: Catalog={catalog}")
        print(f"📝 MDX Query length: {len(mdx_query)} chars")

        # 3. Update Status -> RUNNING
        cur_pg.execute("UPDATE jobs SET status = 'RUNNING', updated_at = NOW() WHERE id = %s", (job_id,))
        conn_pg.commit()
        
        # 4. Connect to OLAP Server
        print("🔌 Connecting to OLAP server...")
        conn_str = (
            f"Provider=MSOLAP;Data Source={os.environ['DGIS_SERVER']};"
            f"Initial Catalog={catalog};"
            f"User ID={os.environ['DGIS_USER']};"
            f"Password={os.environ['DGIS_PASSWORD']};"
        )
        
        conn_olap = adodbapi.connect(conn_str)
        cur_olap = conn_olap.cursor()
        print("✅ Connected to OLAP server")
        
        # 5. Execute MDX
        print("▶️ Executing MDX query...")
        start_time = datetime.now()
        cur_olap.execute(mdx_query)
        
        # Fetch data
        data = cur_olap.fetchall()
        duration = (datetime.now() - start_time).total_seconds()
        print(f"✅ Query executed in {duration:.2f}s. Rows: {len(data)}")
        
        # 6. Process Results
        # Get column names
        column_names = [d[0] for d in cur_olap.description]
        
        # Convert rows to serializable format
        # adodbapi returns pywintypes for some things, need to ensure standard types
        result_rows = []
        for row in data:
            result_rows.append([str(cell) if cell is not None else None for cell in row])
            
        result_json = {
            'columns': column_names,
            'data': result_rows,
            'count': len(result_rows),
            'duration_seconds': duration,
            'executed_at': datetime.now().isoformat()
        }
        
        # 7. Update Status -> COMPLETED
        print("💾 Saving results to database...")
        cur_pg.execute(
            "UPDATE jobs SET status = 'COMPLETED', result_data = %s, updated_at = NOW() WHERE id = %s", 
            (json.dumps(result_json), job_id)
        )
        conn_pg.commit()
        print("✅ Job completed successfully")
        
    except Exception as e:
        print(f"❌ Error during execution: {e}")
        # Try to log error to DB
        try:
            cur_pg.execute(
                "UPDATE jobs SET status = 'FAILED', error_message = %s, updated_at = NOW() WHERE id = %s", 
                (str(e), job_id)
            )
            conn_pg.commit()
        except:
            print("❌ Could not save error state to DB")
        sys.exit(1)
        
    finally:
        if 'conn_olap' in locals(): conn_olap.close()
        if 'conn_pg' in locals(): conn_pg.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job-id', required=True, help='UUID of the job to run')
    args = parser.parse_args()
    
    run_job(args.job_id)
