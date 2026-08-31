"""Maintenance tasks — one-off data repair/backfill jobs that need to run
once against existing rows when a feature ships after that data already
exists (see TASKS in tasks.py). Reuses the scan job registry
(app/scanning/job_registry.py) for background execution + progress polling
rather than inventing a second job system, since the needs are identical:
long-running, real-API-bound, needs a job id the frontend can poll."""
