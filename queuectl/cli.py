# queuectl/cli.py
import click
import json
from queuectl.database import initialize_database
from queuectl import queue_service, worker_logic, settings

@click.group()
def cli():
    """
    queuectl: A simple CLI-based background job queue system.
    """
    pass

@cli.command(name="init-db")
def init_db():
    """Initializes the job queue database."""
    initialize_database()

@cli.command()
@click.argument('job_spec_json', type=str)
def enqueue(job_spec_json):
    """
    Add a new job to the queue.
    
    Example:
    queuectl enqueue '{"id":"job1","command":"echo hello"}'
    """
    queue_service.add_job(job_spec_json)

@cli.group()
def worker():
    """Manage worker processes."""
    pass

@worker.command()
@click.option('--count', default=1, type=int, help='Number of workers to start.')
def start(count):
    """Start one or more worker processes."""
    worker_logic.start_workers(count)

@worker.command()
def stop():
    """Stop all running workers gracefully."""
    worker_logic.stop_workers()

@cli.command()
def status():
    """Show a summary of all job states & active workers."""
    summary = queue_service.get_queue_summary()
    click.echo("--- Queue Status ---")
    click.echo(f"Active Workers: {summary.get('active_workers', 0)}")
    click.echo(f"Pending:        {summary.get('pending', 0)}")
    click.echo(f"Processing:     {summary.get('processing', 0)}")
    click.echo(f"Completed:      {summary.get('completed', 0)}")
    click.echo(f"Dead (DLQ):     {summary.get('dead', 0)}")

@cli.command()
@click.option('--state', 
              type=click.Choice(['pending', 'processing', 'completed', 'dead'], case_sensitive=False),
              help='Filter jobs by state.')
def list(state):
    """List jobs, optionally filtering by state."""
    if not state:
        click.echo("Listing all jobs (use --state to filter):")
        states_to_list = ['pending', 'processing', 'completed', 'dead']
    else:
        states_to_list = [state]
    
    for s in states_to_list:
        jobs = queue_service.find_jobs_by_state(s)
        if jobs:
            click.echo(f"\n--- State: {s.upper()} ({len(jobs)}) ---")
            for job in jobs:
                click.echo(json.dumps(job, indent=2))

@cli.group()
def dlq():
    """Manage the Dead Letter Queue (permanently failed jobs)."""
    pass

@dlq.command(name="list")
def dlq_list():
    """View all jobs in the DLQ."""
    jobs = queue_service.show_dlq_jobs()
    if not jobs:
        click.echo("Dead Letter Queue is empty.")
        return
        
    click.echo(f"--- DLQ Jobs ({len(jobs)}) ---")
    for job in jobs:
        click.echo(json.dumps(job, indent=2))

@dlq.command(name="retry")
@click.argument('job_id', type=str)
def dlq_retry(job_id):
    """Move a specific job from the DLQ back to the pending queue."""
    queue_service.resurrect_dlq_job(job_id)

@cli.group()
def config():
    """Manage system configuration."""
    pass

@config.command(name="set")
@click.argument('key', type=str)
@click.argument('value', type=str)
def config_set(key, value):
    """
    Set a configuration value.
    
    Known keys: 'max_retries', 'backoff_base_seconds'
    """
    if key not in ['max_retries', 'backoff_base_seconds']:
        click.echo(f"Warning: '{key}' is not a recognized setting.")
        
    settings.update_setting(key, value)
    click.echo(f"Config updated: {key} = {value}")

@config.command(name="get")
@click.argument('key', type=str)
def config_get(key):
    """Get a configuration value."""
    value = settings.get_setting(key)
    if value is not None:
        click.echo(f"{key} = {value}")
    else:
        click.echo(f"Error: Config key '{key}' not found.")

def main():
    cli()

if __name__ == "__main__":
    main()