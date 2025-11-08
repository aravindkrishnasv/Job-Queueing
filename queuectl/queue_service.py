# queuectl/queue_service.py
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from queuectl.database import get_db_connection
from queuectl.settings import get_setting

def add_job(job_spec_json):
    """
    Adds a new job to the queue.
    """
    try:
        job_details = json.loads(job_spec_json)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON provided.")
        return None

    if 'command' not in job_details:
        print("Error: Job must contain a 'command' field.")
        return None

    job_id = job_details.get('id', str(uuid.uuid4()))
    default_retries = get_setting('max_retries', 3)
    
    now = datetime.now(timezone.utc).isoformat()
    
    job_to_insert = {
        "id": job_id,
        "command": job_details['command'],
        "state": "pending",
        "attempts": 0,
        "retry_limit": job_details.get('max_retries', default_retries),
        "created_at": now,
        "updated_at": now,
        "next_run_at": None
    }

    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO jobs (id, command, state, attempts, retry_limit, created_at, updated_at)
                VALUES (:id, :command, :state, :attempts, :retry_limit, :created_at, :updated_at)
                """,
                job_to_insert
            )
            conn.commit()
        print(f"Job enqueued with ID: {job_id}")
        return job_id
    except sqlite3.IntegrityError:
        print(f"Error: A job with ID '{job_id}' already exists.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def get_queue_summary():
    """Returns a summary of job states and active workers."""
    summary = {}
    with get_db_connection() as conn:
        rows = conn.execute("SELECT state, COUNT(*) as count FROM jobs GROUP BY state")
        summary = {row['state']: row['count'] for row in rows}

    from queuectl.worker_logic import get_active_worker_pids
    worker_pids = get_active_worker_pids()
    summary['active_workers'] = len(worker_pids)
    
    return summary

def find_jobs_by_state(state):
    """Returns a list of jobs matching a specific state."""
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM jobs WHERE state = ? ORDER BY created_at ASC", (state,))
        return [dict(row) for row in rows]

def show_dlq_jobs():
    """Convenience function to list 'dead' jobs."""
    return find_jobs_by_state('dead')

def resurrect_dlq_job(job_id):
    """Moves a 'dead' job back to 'pending' to be retried."""
    now = datetime.now(timezone.utc).isoformat()
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE jobs
            SET state = 'pending', attempts = 0, next_run_at = NULL, updated_at = ?
            WHERE id = ? AND state = 'dead'
            """,
            (now, job_id)
        )
        conn.commit()
        
        if cursor.rowcount == 0:
            print(f"Error: Job ID '{job_id}' not found in DLQ.")
            return False
        else:
            print(f"Job '{job_id}' moved from DLQ to 'pending' queue.")
            return True