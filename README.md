# queuectl: A CLI-Based Job Queue System

`queuectl` is a minimal, production-grade background job queue system built in Python. It manages background jobs with worker processes, handles retries using exponential backoff, and maintains a Dead Letter Queue (DLQ) for permanently failed jobs.

This project was built as an internship assignment.

[Link to CLI Demo Video] <- *Don't forget to add your demo link here!*

## 🌟 Core Features

* **Persistent Jobs:** Uses SQLite to ensure jobs are not lost on restart.
* **Concurrent Workers:** Runs multiple worker processes in parallel using Python's `multiprocessing` module.
* **Atomic Operations:** Safely claims jobs without race conditions using SQLite's transaction locking.
* **Exponential Backoff:** Automatically retries failed jobs with an increasing delay (`base ^ attempts`).
* **Dead Letter Queue (DLQ):** Moves jobs to a DLQ after all retry attempts are exhausted.
* **Graceful Shutdown:** Workers can be stopped with `queuectl worker stop`, allowing them to finish their current job before exiting.
* **Clean CLI:** A user-friendly interface powered by `click`.

## 🛠️ Setup and Installation

**Prerequisites:**
* Python 3.8+
* `pip`

**Instructions:**

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/aravindkrishnasv/Job-Queueing.git](https://github.com/aravindkrishnasv/Job-Queueing.git)
    cd queuectl-project
    ```

2.  **Install the package:**
    This command uses `setup.py` to install the `queuectl` command-line tool in your environment.
    ```bash
    pip install .
    ```

3.  **Initialize the database:**
    Before you can use the queue, you must initialize the database. This creates the `queue.db` file in your home directory (`~/.queuectl/`).
    ```bash
    queuectl init-db
    ```

You are now ready to use `queuectl`!

## Usage Examples

All operations are accessible through the `queuectl` command. You can get help for any command by adding `--help`.

### 1. Enqueueing Jobs

Add a new job to the queue. The only required field is `"command"`. An `id` will be auto-generated if not provided.

```bash
# Enqueue a simple job
$ queuectl enqueue '{"id":"job1","command":"echo Hello World"}'
Job enqueued with ID: job1

# Enqueue a job that will fail
$ queuectl enqueue '{"id":"job2","command":"ls /nonexistent-directory"}'
Job enqueued with ID: job2

# Enqueue a job with a custom retry limit
$ queuectl enqueue '{"command":"sleep 5", "max_retries": 5}'
Job enqueued with ID: 5a8e...
```

### 2. Managing Workers

Workers run in the background and process jobs from the queue.

```bash
# Start 3 workers
$ queuectl worker start --count 3
Successfully started 3 worker(s).
They will run in the background. Use 'queuectl worker stop' to stop them.

# Check the status
$ queuectl status
--- Queue Status ---
Active Workers: 3
Pending:        0
Processing:     1  # 'sleep 5' job
Completed:      1  # 'job1'
Dead (DLQ):     1  # 'job2'

# Stop all running workers gracefully
$ queuectl worker stop
Stopping 3 active worker(s)...
All workers stopped gracefully.
```

### 3. Listing Jobs

You can inspect the state of all jobs.

```bash
# List all jobs (grouped by state)
$ queuectl list

--- State: completed (1) ---
{
  "id": "job1",
  "command": "echo Hello World",
  "state": "completed",
  ...
}

--- State: dead (1) ---
{
  "id": "job2",
  "command": "ls /nonexistent-directory",
  "state": "dead",
  "attempts": 3,
  ...
}

# List only jobs in the 'pending' state
$ queuectl list --state pending
```

### 4. Managing the DLQ

View and retry permanently failed jobs.

```bash
# List all jobs in the Dead Letter Queue
$ queuectl dlq list
--- DLQ Jobs (1) ---
{
  "id": "job2",
  "command": "ls /nonexistent-directory",
  "state": "dead",
  ...
}

# Retry a job from the DLQ
$ queuectl dlq retry job2
Job 'job2' moved from DLQ to 'pending' queue.
```

### 5. Configuration

You can change system settings, which are persisted in the database.

```bash
# Set the default max retries for new jobs to 5
$ queuectl config set max_retries 5

# Set the base for exponential backoff to 3 seconds
$ queuectl config set backoff_base_seconds 3

# Check a value
$ queuectl config get max_retries
max_retries = 5
```

## 📐 Architecture and Design Decisions

### Job Lifecycle

A job moves through the following states:

1.  **`pending`**: The job is new and waiting to be processed.
2.  **`processing`**: A worker has claimed the job and is currently executing its command.
3.  **`completed`**: The job's command finished with an exit code of 0.
4.  **`failed`**: The job's command failed (non-zero exit code) but it still has retries left. It is immediately moved back to `pending` with a `next_run_at` timestamp for the backoff.
5.  **`dead`**: The job failed and has exhausted all its `retry_limit` attempts. It is moved to the DLQ and will not be processed again unless manually re-queued with `queuectl dlq retry`.

### Persistence (SQLite)

I chose **SQLite** over a simple JSON file for persistence.
* **Why:** SQLite is an embedded, file-based database that provides full transaction (ACID) support. This is **critical** for handling concurrency.
* **Concurrency:** When multiple workers try to get a job at the same time, a JSON file would lead to a race condition where two workers could grab the same job. SQLite's `BEGIN IMMEDIATE TRANSACTION` command acquires an immediate write lock, ensuring that only **one worker** can claim the next available job at a time. This makes the system robust and correct.
* **Performance:** Using `PRAGMA journal_mode=WAL` (Write-Ahead Logging) allows high read concurrency while writers are active.

### Worker Management

* **`multiprocessing`**: The `queuectl worker start` command uses the `multiprocessing` module to spawn new, independent Python processes. This is superior to threading for CPU-bound tasks and avoids Python's Global Interpreter Lock (GIL).
* **PID Files**: Each worker, upon starting, writes a small file to `~/.queuectl/workers/worker.<PID>.pid`.
* **Graceful Shutdown**: When `queuectl worker stop` is run:
    1.  It reads all PIDs from the PID directory.
    2.  It sends a `SIGTERM` (terminate) signal to each PID.
    3.  Each worker process has a signal handler that catches `SIGTERM`.
    4.  The handler sets a global `shutdown_requested` flag.
    5.  The worker's main loop checks this flag and, instead of picking a new job, exits cleanly.
    6.  A `finally` block in the worker ensures it deletes its own PID file before exiting.

### Assumptions and Trade-offs

* **`shell=True`**: Job commands are executed with `shell=True` for simplicity (e.g., to allow commands like `echo 'hi' | wc -l`). In a real production system, this is a security risk (shell injection). A safer approach would parse the command and arguments separately.
* **Polling**: Workers find jobs by polling the database every 1 second. This is simple but not the most efficient. A more advanced system might use a notification mechanism (e.g., `LISTEN/NOTIFY` in
    PostgreSQL).
* **Scope**: Features like job timeouts, priority, and scheduled jobs are implemented as simple stubs or left for future work, per the "Bonus" section.

## ✅ How to Test

To run a simple, automated test of the core system flow:

1.  Make sure you have installed the package (`pip install .`).
2.  Run the test script:

    ```bash
    bash tests/test_workflow.sh
    ```

This script will:
1.  Clean up any old database.
2.  Initialize a new database.
3.  Set retries to 2 for fast testing.
4.  Start workers.
5.  Enqueue one job that succeeds and two that fail.
6.  Wait for them to be processed.
7.  Check that the successful job is in `completed`.
8.  Check that the failed jobs are in the `dead` (DLQ) state.
9.  Test the `dlq retry` command.
10. Stop the workers.