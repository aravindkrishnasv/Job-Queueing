# queuectl/worker_logic.py
import subprocess
import sqlite3
import time
import os
import signal
import multiprocessing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queuectl.database import get_db_connection
from queuectl.settings import get_setting

PID_DIR = Path.home() / ".queuectl" / "workers"
POLL_INTERVAL_SECONDS = 1

shutdown_requested = False

def handle_shutdown_signal(sig, frame):
    """Sets the global flag to stop worker loops."""
    global shutdown_requested
    if not shutdown_requested:
        print(f"Worker (PID: {os.getpid()}) received signal {sig}. Shutting down gracefully...")
        shutdown_requested = True

def run_worker_instance(worker_id):
    """
    The main loop for a single worker process.
    It continuously polls for jobs, executes them, and handles results.
    """
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    PID_DIR.mkdir(parents=True, exist_ok=True)
    pid_file_path = PID_DIR / f"worker.{os.getpid()}.pid"
    with open(pid_file_path, 'w') as f:
        f.write(str(worker_id))
    
    print(f"Worker {worker_id} started (PID: {os.getpid()})")

    try:
        while not shutdown_requested:
            job = claim_next_job()
            if job:
                print(f"[Worker {worker_id}]: Processing job {job['id']}...")
                process_job(job)
            else:
                time.sleep(POLL_INTERVAL_SECONDS)
    finally:
        if pid_file_path.exists():
            pid_file_path.unlink()
        print(f"Worker {worker_id} (PID: {os.getpid()}) stopped.")

def claim_next_job():
    """
    Atomically claims the next available job from the queue.
    This is the most critical concurrent part of the system.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    
    with get_db_connection() as conn:
        try:
            with conn:
                cursor = conn.execute(
                    """
                    SELECT id FROM jobs
                    WHERE state = 'pending' AND (next_run_at IS NULL OR next_run_at <= ?)
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (now_iso,)
                )
                row = cursor.fetchone()

                if row is None:
                    return None

                job_id = row['id']
                
                conn.execute(
                    """
                    UPDATE jobs
                    SET state = 'processing', updated_at = ?
                    WHERE id = ? AND state = 'pending'
                    """,
                    (now_iso, job_id)
                )
                
                job_row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
                return dict(job_row)
                
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e):
                return None
            else:
                raise e

def process_job(job):
    """Executes the job's command and updates its state based on the result."""
    try:
        result = subprocess.run(
            job['command'],
            shell=True,
            check=True,
            capture_output=True,
            text=True,
            timeout=300
        )
        print(f"Job {job['id']} completed successfully.")
        update_job_status(job['id'], 'completed')

    except subprocess.CalledProcessError as e:
        print(f"Job {job['id']} failed with exit code {e.returncode}.")
        print(f"Stderr: {e.stderr}")
        handle_job_failure(job)
    except subprocess.TimeoutExpired:
        print(f"Job {job['id']} timed out.")
        handle_job_failure(job)
    except Exception as e:
        print(f"Job {job['id']} failed with an unexpected error: {e}")
        handle_job_failure(job)

def handle_job_failure(job):
    """Handles failed jobs, increments attempts, and calculates backoff."""
    new_attempts = job['attempts'] + 1
    
    if new_attempts >= job['retry_limit']:
        print(f"Job {job['id']} reached max retries. Moving to DLQ.")
        update_job_status(job['id'], 'dead')
    else:
        backoff_base = get_setting('backoff_base_seconds', 2)
        delay_seconds = backoff_base ** new_attempts
        
        next_run_time = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        next_run_iso = next_run_time.isoformat()
        
        print(f"Job {job['id']} failed. Retrying in {delay_seconds}s (Attempt {new_attempts}).")
        update_job_status(
            job['id'],
            'pending',
            attempts=new_attempts,
            next_run_at=next_run_iso
        )

def update_job_status(job_id, state, attempts=None, next_run_at=None):
    """Updates a job's state and metadata in the database."""
    now_iso = datetime.now(timezone.utc).isoformat()
    
    with get_db_connection() as conn:
        if attempts is not None:
            conn.execute(
                """
                UPDATE jobs
                SET state = ?, attempts = ?, next_run_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (state, attempts, next_run_at, now_iso, job_id)
            )
        else:
            conn.execute(
                """
                UPDATE jobs
                SET state = ?, updated_at = ?
                WHERE id = ?
                """,
                (state, now_iso, job_id)
            )
        conn.commit()

def get_active_worker_pids():
    """Finds all running worker PIDs by checking the PID files."""
    if not PID_DIR.exists():
        return []
    
    pids = []
    for pid_file in PID_DIR.glob("worker.*.pid"):
        try:
            pid = int(pid_file.stem.split('.')[1])
            os.kill(pid, 0)
            pids.append(pid)
        except (OSError, ValueError):
            pid_file.unlink()
    return pids

def start_workers(count):
    """Launches the specified number of worker processes."""
    processes = []
    for i in range(count):
        process = multiprocessing.Process(
            target=run_worker_instance,
            args=(i + 1,),
            daemon=True
        )
        process.start()
        processes.append(process)
    
    print(f"Successfully started {count} worker(s).")
    print("They will run in the background. Use 'queuectl worker stop' to stop them.")

def stop_workers():
    """Stops all running workers gracefully using SIGTERM."""
    pids = get_active_worker_pids()
    if not pids:
        print("No active workers found.")
        return

    print(f"Stopping {len(pids)} active worker(s)...")
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    
    retries = 10
    while retries > 0 and len(get_active_worker_pids()) > 0:
        time.sleep(0.5)
        retries -= 1
    
    if len(get_active_worker_pids()) == 0:
        print("All workers stopped gracefully.")
    else:
        print("Some workers did not stop in time. They may need to be killed manually.")