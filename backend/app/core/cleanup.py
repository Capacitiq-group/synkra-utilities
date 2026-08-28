"""
Every job gets its own throwaway directory under TEMP_DIR. Nothing here
is ever meant to survive the request/response cycle for longer than
TEMP_FILE_TTL_SECONDS — this is a processing service, not storage.
"""
import shutil
import time
import uuid
from pathlib import Path

from starlette.background import BackgroundTask

from app.config import TEMP_DIR, TEMP_FILE_TTL_SECONDS


def new_job_dir() -> Path:
    job_dir = TEMP_DIR / uuid.uuid4().hex
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


def delete_dir(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


def cleanup_task(job_dir: Path) -> BackgroundTask:
    """Attach to a FileResponse so the temp dir is removed right after send."""
    return BackgroundTask(delete_dir, job_dir)


def sweep_expired_dirs() -> int:
    """
    Belt-and-braces sweep for anything a crashed request left behind.
    Call this from a periodic task (cron / APScheduler / k8s CronJob) —
    it is NOT invoked automatically by the API process itself.
    """
    removed = 0
    now = time.time()
    if not TEMP_DIR.exists():
        return removed
    for entry in TEMP_DIR.iterdir():
        try:
            if now - entry.stat().st_mtime > TEMP_FILE_TTL_SECONDS:
                delete_dir(entry)
                removed += 1
        except FileNotFoundError:
            continue
    return removed
