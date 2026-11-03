"""Run optional pose processing without changing video playback state."""
import logging
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .models import Attempt, PoseJob

log = logging.getLogger(__name__)


def run_pose(app):
    cfg = app.state.settings
    if not cfg.pose_model:
        return False
    engine = app.state.engine
    with Session(engine) as session, session.begin():
        if engine.dialect.name == 'sqlite':
            session.execute(text('BEGIN IMMEDIATE'))
        now = time.time()
        job = session.scalar(
            select(PoseJob)
            .where((PoseJob.state == 'QUEUED') | ((PoseJob.state == 'RUNNING') & (PoseJob.lease < now)))
            .order_by(PoseJob.attempt_id).limit(1).with_for_update(skip_locked=True)
        )
        if not job:
            return False
        attempt = session.get(Attempt, job.attempt_id)
        if not attempt or attempt.deleted:
            job.state = 'CANCELLED'
            return True
        if job.attempts >= 3:
            job.state = 'FAILED'
            return True
        job.state = 'RUNNING'
        job.lease = lease = now + 600
        job.attempts += 1
        attempt_id = job.attempt_id

    output = cfg.storage_dir / f'{attempt_id}.{uuid.uuid4().hex}.pose'
    source = cfg.storage_dir / f'{attempt_id}.mp4'
    ready = False
    try:
        cache = cfg.storage_dir.parent / "pose-cache"
        cache.mkdir(exist_ok=True)
        subprocess.run([
            cfg.pose_python or sys.executable, str(Path(__file__).with_name('pose_runner.py')),
            str(source), cfg.pose_model, str(output),
        ], check=True, timeout=540, capture_output=True,
           env={**os.environ, "MPLCONFIGDIR": str(cache)})
        ready = output.is_file()
    except (OSError, subprocess.SubprocessError) as error:
        log.warning('Pose processing failed for %s (%s)', attempt_id, type(error).__name__)
    try:
        with Session(engine) as session, session.begin():
            if engine.dialect.name == 'sqlite':
                session.execute(text('BEGIN IMMEDIATE'))
            attempt = session.scalar(select(Attempt).where(Attempt.id == attempt_id).with_for_update())
            job = session.scalar(select(PoseJob).where(PoseJob.attempt_id == attempt_id).with_for_update())
            if job.lease == lease and job.state == 'RUNNING':
                if not attempt or attempt.deleted:
                    job.state = 'CANCELLED'
                elif ready:
                    output.replace(cfg.storage_dir / f'{attempt_id}.pose.json')
                    job.state = 'READY'
                else:
                    job.state = 'FAILED'
    finally:
        output.unlink(missing_ok=True)
    return True
