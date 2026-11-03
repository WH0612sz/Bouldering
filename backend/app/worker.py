"""Durable media job runner for milestone M2. Video preparation and optional pose processing."""
import argparse,time,uuid
from pathlib import Path
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from .main import create_app
from .models import Job,Attempt,Upload,User,PoseJob
from .media import prepare
from .pose_worker import run_pose

def claim(engine):
    with Session(engine) as s:
        if engine.dialect.name=='sqlite':s.execute(text('BEGIN IMMEDIATE'))
        now=time.time()
        job=s.scalar(select(Job).where((Job.state=='QUEUED')|((Job.state=='RUNNING')&(Job.lease<now))).order_by(Job.id).with_for_update(skip_locked=True))
        if not job:s.commit();return None
        a=s.get(Attempt,job.attempt_id)
        if not a or a.deleted:job.state='CANCELLED';s.commit();return None
        if job.attempts>=5:job.state='FAILED';a.state='FAILED';a.error='视频处理重试次数已达上限';s.commit();return None
        job.state='RUNNING';job.attempts+=1;job.lease=now+900;a.state='PREPARING';s.commit()
        return {'job_id':job.id,'id':a.id,'upload_id':a.upload_id,'start':a.trim_start,'end':a.trim_end,'lease':job.lease}

def run_one(app):
    engine=app.state.engine;root=app.state.settings.storage_dir;job=claim(engine)
    if not job:return False
    stamp=uuid.uuid4().hex;video=root/(job['id']+'.'+stamp+'.mp4');poster=root/(job['id']+'.'+stamp+'.jpg')
    error=''
    try:prepare(root/(job['upload_id']+'.source'),video,poster,job['start'],job['end'])
    except Exception:error='视频处理失败，请重试或重新选择视频'
    with Session(engine) as s:
        if engine.dialect.name=='sqlite':s.execute(text('BEGIN IMMEDIATE'))
        a=s.scalar(select(Attempt).where(Attempt.id==job['id']).with_for_update());j=s.get(Job,job['job_id'])
        if a and not a.deleted and j.state=='RUNNING' and j.lease==job['lease']:
            if error:a.state='FAILED';a.error=error;j.state='FAILED';j.error=error
            else:
                video.replace(root/(a.id+'.mp4'));poster.replace(root/(a.id+'.jpg'));a.state='PLAYABLE';a.error='';j.state='SUCCEEDED'
                model = app.state.settings.pose_model
                if model and Path(model).is_file() and not s.get(PoseJob, a.id):
                    s.add(PoseJob(attempt_id=a.id))
        s.commit()
    video.unlink(missing_ok=True);poster.unlink(missing_ok=True);return True

def maintenance(app):
    root=app.state.settings.storage_dir;engine=app.state.engine
    with Session(engine) as s:
        if engine.dialect.name=='sqlite':s.execute(text('BEGIN IMMEDIATE'))
        for u in s.scalars(select(Upload).where(Upload.state!='COMMITTED',Upload.expires<time.time()).with_for_update(skip_locked=True)):
            u.state='CANCELLED';(root/(u.id+'.source')).unlink(missing_ok=True)
        for u in s.scalars(select(Upload).where(Upload.state=='CANCELLED').with_for_update(skip_locked=True)):(root/(u.id+'.source')).unlink(missing_ok=True)
        for a in s.scalars(select(Attempt).where(Attempt.deleted.is_not(None)).with_for_update(skip_locked=True)):
            for suffix in ['.mp4','.jpg','.pose.json']:(root/(a.id+suffix)).unlink(missing_ok=True)
            (root/(a.upload_id+'.source')).unlink(missing_ok=True)
        avatars={u.avatar for u in s.scalars(select(User)) if u.avatar}
        for f in root.glob('avatar-*.jpg'):
            if f.name not in avatars and time.time()-f.stat().st_mtime>86400:f.unlink(missing_ok=True)
        # Abandoned multipart/worker output is never publicly served.
        for f in root.iterdir():
            parts = f.name.split('.')
            is_worker_temp = len(parts) == 3 and parts[-1] in {'mp4', 'jpg', 'pose'}
            if ('.incoming-' in f.name or is_worker_temp) and time.time() - f.stat().st_mtime > 86400:
                f.unlink(missing_ok=True)
        s.commit()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args();app=create_app(initialize=False)
    while True:
        maintenance(app);worked=run_one(app) or run_pose(app)
        if args.once:break
        if not worked:time.sleep(2)
if __name__=='__main__':main()
