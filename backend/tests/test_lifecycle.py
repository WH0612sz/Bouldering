import io, time, subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest, imageio_ffmpeg
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from PIL import Image
from app.main import create_app
from app.config import Settings
from app.models import Upload, Attempt, Job
from app.worker import run_one, maintenance

@pytest.fixture(scope='session')
def video(tmp_path_factory):
    path=tmp_path_factory.mktemp('fixture')/'clip.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','lavfi','-i','color=c=green:s=160x288:r=15','-t','1','-c:v','libx264','-pix_fmt','yuv420p',str(path)],check=True)
    return path.read_bytes()
@pytest.fixture
def env(tmp_path):
    cfg=Settings(database_url='sqlite:///'+str(tmp_path/'db.sqlite'),storage_dir=tmp_path/'files',dev_login=True)
    app=create_app(cfg);client=TestClient(app)
    def auth(name='alice'):
        return {'Authorization':'Bearer '+client.post('/v1/auth/dev',json={'identity':name}).json()['token']}
    return app,client,auth

def begin(c,h,submission='submission-123',**overrides):
    payload={'submission_id':submission,'name':'测试攀爬','climb_date':'2026-10-28','trim_start':0,'trim_end':1,**overrides}
    r=c.post('/v1/uploads',headers=h,json=payload);assert r.status_code==200,r.text
    return r.json()['id']
def submit(c,h,video,submission='submission-123',**overrides):
    id=begin(c,h,submission,**overrides)
    r=c.post('/v1/uploads/'+id+'/content',headers=h,files={'file':('clip.mp4',video,'video/mp4')});assert r.status_code==200,r.text
    return id,c.post('/v1/uploads/'+id+'/commit',headers=h)

def test_save_only_after_commit_and_restart(env,video):
    app,c,auth=env;h=auth();u=begin(c,h,route_name='蓝色线路')
    assert c.get('/v1/attempts',headers=h).json()['items']==[]
    assert c.get('/v1/routes',headers=h).json()['items']==[]
    c.post('/v1/uploads/'+u+'/content',headers=h,files={'file':('x.mp4',video)})
    assert c.get('/v1/attempts',headers=h).json()['items']==[]
    r=c.post('/v1/uploads/'+u+'/commit',headers=h);assert r.status_code==200
    aid=r.json()['attempt_id'];assert c.post('/v1/uploads/'+u+'/commit',headers=h).json()['attempt_id']==aid
    assert c.get('/v1/me',headers=h).json()['stats']=={'videos':1,'days':1,'routes':1}
    app2=create_app(app.state.settings);c2=TestClient(app2)
    assert c2.get('/v1/attempts/'+aid,headers=h).status_code==200
    with Session(app.state.engine) as s:assert len(list(s.scalars(select(Job))))==1

def test_cancel_before_commit_cleans_source(env,video):
    app,c,auth=env;h=auth();u=begin(c,h)
    c.post('/v1/uploads/'+u+'/content',headers=h,files={'file':('x.mp4',video)})
    assert c.delete('/v1/uploads/'+u,headers=h).json()['state']=='CANCELLED'
    assert c.post('/v1/uploads/'+u+'/commit',headers=h).status_code==409
    maintenance(app);assert not (app.state.settings.storage_dir/(u+'.source')).exists()
    assert c.get('/v1/me',headers=h).json()['stats']['videos']==0

def test_cancel_after_commit_reports_saved(env,video):
    _,c,auth=env;h=auth();u,r=submit(c,h,video);assert r.status_code==200
    assert c.delete('/v1/uploads/'+u,headers=h).json()['attempt_id']==r.json()['attempt_id']
    assert len(c.get('/v1/attempts',headers=h).json()['items'])==1

def test_invalid_media_trim_and_size(env,video):
    app,c,auth=env;h=auth();u,r=submit(c,h,b'not video');assert r.status_code==422
    assert not c.get('/v1/attempts',headers=h).json()['items']
    _,r=submit(c,h,video,'submission-456',trim_end=4);assert r.status_code==422
    app.state.settings.max_bytes=10
    u=begin(c,h,'submission-789')
    assert c.post('/v1/uploads/'+u+'/content',headers=h,files={'file':('x',video)}).status_code==413
    assert c.get('/v1/uploads/'+u,headers=h).json()['state']=='CREATED'

def test_isolation_auth_and_private_storage(env,video):
    app,c,auth=env;a=auth();b=auth('bob');u,r=submit(c,a,video);aid=r.json()['attempt_id']
    for path in ['/v1/uploads/'+u,'/v1/attempts/'+aid,'/v1/attempts/'+aid+'/playback']:
        assert c.get(path,headers=b).status_code==404
        assert c.get(path).status_code==401
    assert c.delete('/v1/attempts/'+aid,headers=b).status_code==404
    assert c.post('/v1/uploads/'+u+'/commit',headers=b).status_code==404
    assert c.get('/storage/'+u+'.source').status_code==404
    assert c.get('/v1/media/video/'+aid+'?expires=1&sig=wrong').status_code==403

def test_transcode_range_and_delete_revokes_signed_media(env,video):
    app,c,auth=env;h=auth();u,r=submit(c,h,video);aid=r.json()['attempt_id']
    assert c.get('/v1/attempts/'+aid+'/playback',headers=h).status_code==409
    assert run_one(app)
    assert c.get('/v1/attempts/'+aid,headers=h).json()['state']=='PLAYABLE'
    url=c.get('/v1/attempts/'+aid+'/playback',headers=h).json()['url'];path=url.replace('http://127.0.0.1:8000','')
    result=c.get(path,headers={'Range':'bytes=0-99'});assert result.status_code==206 and len(result.content)==100
    assert c.delete('/v1/attempts/'+aid,headers=h).status_code==200
    assert c.get(path).status_code==404
    assert c.get('/v1/me',headers=h).json()['stats']=={'videos':0,'days':0,'routes':0}
    maintenance(app);assert not (app.state.settings.storage_dir/(aid+'.mp4')).exists()
    assert not (app.state.settings.storage_dir/(u+'.source')).exists()

def test_metadata_route_revision_and_pagination(env,video):
    _,c,auth=env;h=auth();u,r=submit(c,h,video);aid=r.json()['attempt_id']
    result=c.put('/v1/attempts/'+aid,headers=h,json={'revision':1,'name':'新名称','completion':'已完成','route_name':'新线路'});assert result.status_code==200
    item=result.json();assert item['route_name']=='新线路' and item['revision']==2
    assert c.put('/v1/attempts/'+aid,headers=h,json={'revision':1,'name':'旧修改'}).status_code==409
    assert c.put('/v1/attempts/'+aid,headers=h,json={'revision':2,'route_id':None}).json()['route_id'] is None
    submit(c,h,video,'submission-222')
    first=c.get('/v1/attempts?limit=1',headers=h).json();assert first['next_cursor']
    second=c.get('/v1/attempts?limit=1&cursor='+first['next_cursor'],headers=h).json();assert first['items'][0]['id']!=second['items'][0]['id']
    assert len(c.get('/v1/attempts?completion=已完成',headers=h).json()['items'])==1

def test_concurrent_duplicate_submission(env,video):
    app,c,auth=env;h=auth();u=begin(c,h);c.post('/v1/uploads/'+u+'/content',headers=h,files={'file':('x.mp4',video)})
    def commit(_):return c.post('/v1/uploads/'+u+'/commit',headers=h)
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(commit,range(3)))
    assert all(r.status_code==200 for r in results)
    assert len({r.json()['attempt_id'] for r in results})==1
    assert len(c.get('/v1/attempts',headers=h).json()['items'])==1

def test_changed_submission_conflict(env):
    _,c,auth=env;h=auth();begin(c,h)
    r=c.post('/v1/uploads',headers=h,json={'submission_id':'submission-123','name':'changed','climb_date':'2026-10-28','trim_start':0,'trim_end':1});assert r.status_code==409

def test_worker_failure_retry_and_cancel_writeback(env,video):
    app,c,auth=env;h=auth();u,r=submit(c,h,video);aid=r.json()['attempt_id']
    (app.state.settings.storage_dir/(u+'.source')).write_bytes(b'broken')
    run_one(app);assert c.get('/v1/attempts/'+aid,headers=h).json()['state']=='FAILED'
    assert c.post('/v1/attempts/'+aid+'/retry',headers=h).json()['state']=='PREPARING'
    c.delete('/v1/attempts/'+aid,headers=h);assert not run_one(app)
    assert c.get('/v1/attempts/'+aid,headers=h).status_code==404

def test_profile_avatar_and_production_guards(env,tmp_path):
    app,c,auth=env;h=auth();assert c.put('/v1/me',headers=h,json={'nickname':'岩友'}).status_code==200
    assert c.get('/v1/me',headers=h).json()['nickname']=='岩友'
    im=Image.new('RGB',(20,20),'green');f=io.BytesIO();im.save(f,format='PNG')
    r=c.post('/v1/me/avatar',headers=h,files={'file':('avatar.png',f.getvalue())});assert r.status_code==200
    assert c.get(r.json()['avatar_url'].replace('http://127.0.0.1:8000','')).status_code==200
    assert c.post('/v1/me/avatar',headers=h,files={'file':('x.svg',b'<svg/>')}).status_code==400
    app2=create_app(Settings(database_url='sqlite:///'+str(tmp_path/'off.db'),storage_dir=tmp_path/'off',dev_login=False))
    assert TestClient(app2).post('/v1/auth/dev',json={'identity':'hacker'}).status_code==404
    with pytest.raises(RuntimeError):create_app(Settings(environment='production',database_url='sqlite:///'+str(tmp_path/'prod.db'),storage_dir=tmp_path/'prod',dev_login=True))


def test_pose_queue_result_is_private_and_deleted_with_video(env, video, tmp_path, monkeypatch):
    from app.pose_worker import run_pose

    app, client, auth = env
    owner, outsider = auth(), auth('outsider')
    model = tmp_path / 'model.task'
    model.touch()
    app.state.settings.pose_model = str(model)
    _, committed = submit(client, owner, video)
    attempt_id = committed.json()['attempt_id']
    assert run_one(app)
    endpoint = f'/v1/attempts/{attempt_id}/pose'
    assert client.get(endpoint, headers=owner).json() == {'state': 'QUEUED'}
    assert client.get(endpoint, headers=outsider).status_code == 404
    assert client.post(endpoint, headers=outsider).status_code == 404
    assert client.post(endpoint, headers=owner).json() == {'state': 'QUEUED'}

    def write_result(command, **kwargs):
        Path(command[-1]).write_text('{"version":"pose-v1","frames":[]}')

    monkeypatch.setattr('app.pose_worker.subprocess.run', write_result)
    assert run_pose(app)
    assert not run_pose(app)
    assert client.get(endpoint, headers=owner).json()['version'] == 'pose-v1'
    from os import utime
    result = app.state.settings.storage_dir / f'{attempt_id}.pose.json'
    old = time.time() - 2 * 86400
    utime(result, (old, old))
    maintenance(app)
    assert result.exists()
    assert client.delete(f'/v1/attempts/{attempt_id}', headers=owner).status_code == 200
    assert client.get(endpoint, headers=owner).status_code == 404
    maintenance(app)
    assert not (app.state.settings.storage_dir / f'{attempt_id}.pose.json').exists()
