from contextlib import asynccontextmanager
from pathlib import Path
from datetime import date
import base64, hashlib, hmac, io, json, secrets, time, uuid
from typing import Annotated
import httpx
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, event, select, func, text
from sqlalchemy.orm import Session as DB
from .config import Settings
from .models import Base, User, Session, Upload, Attempt, Route, Job, PoseJob
from .schemas import Login, DevLogin, Profile, UploadCreate, AttemptPatch, RouteCreate
from .media import probe, MediaError

def fail(code, message, status=400):
    raise HTTPException(status, detail={'code':code,'message':message,'retryable':status>=500})
def digest(token): return hashlib.sha256(token.encode()).hexdigest()

def create_app(settings=None, initialize=True):
    cfg=settings or Settings();cfg.prepare()
    engine=create_engine(cfg.database_url,connect_args={'check_same_thread':False,'timeout':30} if cfg.database_url.startswith('sqlite') else {},pool_pre_ping=True)
    if cfg.database_url.startswith('sqlite'):
        @event.listens_for(engine,'connect')
        def sqlite_setup(conn,_):
            conn.execute('PRAGMA foreign_keys=ON');conn.execute('PRAGMA journal_mode=WAL')
    if initialize: Base.metadata.create_all(engine)
    app=FastAPI(title='攀岩 · 记录服务',version='0.1.0');app.state.engine=engine;app.state.settings=cfg
    @app.middleware('http')
    async def headers(request,call_next):
        request.state.request_id=uuid.uuid4().hex
        if request.method=='POST' and ('/content' in request.url.path or '/avatar' in request.url.path):
            length=request.headers.get('content-length')
            if not length or not length.isdigit():return JSONResponse({'code':'LENGTH_REQUIRED','message':'上传需提供文件大小','retryable':False},status_code=411)
            if int(length)>cfg.max_bytes+1024*1024:return JSONResponse({'code':'FILE_TOO_LARGE','message':'视频超过大小限制','retryable':False},status_code=413)
        response=await call_next(request)
        response.headers['X-Request-ID']=request.state.request_id
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response
    @app.exception_handler(HTTPException)
    async def http_error(request,e):
        detail=e.detail if isinstance(e.detail,dict) else {'code':'REQUEST_FAILED','message':str(e.detail),'retryable':e.status_code>=500}
        return JSONResponse({**detail,'request_id':getattr(request.state,'request_id','')},status_code=e.status_code)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,e):return JSONResponse({'code':'INVALID_INPUT','message':'输入格式或范围不正确','retryable':False,'request_id':request.state.request_id},status_code=422)
    def db(request:Request):
        with DB(engine,expire_on_commit=False) as s:
            if cfg.database_url.startswith('sqlite') and request.method not in ('GET','HEAD'):
                s.execute(text('BEGIN IMMEDIATE'))
            try:
                yield s;s.commit()
            except BaseException:s.rollback();raise
    Database=Annotated[DB,Depends(db,scope='function')]
    def current_user(request:Request,s:Database):
        raw=request.headers.get('authorization','').removeprefix('Bearer ')
        session=s.get(Session,digest(raw)) if raw else None
        if not session or session.expires<time.time():fail('UNAUTHORIZED','登录已过期，请重试',401)
        return s.get(User,session.user_id)
    Current=Annotated[User,Depends(current_user)]
    def serialize_key(s,key):
        if engine.dialect.name=='postgresql':
            number=int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],'big',signed=True)
            s.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':number})
    def issue(s,identity):
        serialize_key(s,'login:'+identity)
        # Identity is appid+openid in production; dev sessions are namespaced.
        user=s.scalar(select(User).where(User.identity==identity).with_for_update())
        if not user:user=User(identity=identity);s.add(user);s.flush()
        token=secrets.token_urlsafe(36);s.add(Session(token_hash=digest(token),user_id=user.id,expires=time.time()+30*86400))
        return {'token':token,'user_id':user.id,'expires_in':30*86400}
    def owned(s,model,id,user,lock=False):
        q=select(model).where(model.id==id,model.owner_id==user.id)
        if model is Attempt:q=q.where(Attempt.deleted.is_(None))
        obj=s.scalar(q.with_for_update() if lock else q)
        if not obj:fail('NOT_FOUND','记录不存在或无权访问',404)
        return obj
    def signature(kind,id,exp):return hmac.new(cfg.secret.encode(),f'{kind}:{id}:{exp}'.encode(),hashlib.sha256).hexdigest()
    def media_url(kind,id):
        exp=int(time.time()+900)
        return f'{cfg.public_url}/v1/media/{kind}/{id}?expires={exp}&sig={signature(kind,id,exp)}'
    def route_name(s,a):
        route=s.get(Route,a.route_id) if a.route_id else None
        return route.name if route else None
    def serialize(s,a):
        pose = s.get(PoseJob, a.id)
        return {'id':a.id,'name':a.name,'climb_date':a.climb_date,'completion':a.completion,'route_id':a.route_id,'route_name':route_name(s,a),'duration':a.duration,'trim_start':a.trim_start,'trim_end':a.trim_end,'state':a.state,'error':a.error,'revision':a.revision,'created_at':a.created,'poster_url':media_url('poster',a.id) if a.state=='PLAYABLE' else None,'analysis_state':pose.state if pose else 'NOT_STARTED','analysis_message':'视频已保存'}
    def resolve_route(s,user,route_id,route_label):
        if route_id:return owned(s,Route,route_id,user).id
        if route_label and route_label.strip():
            r=Route(owner_id=user.id,name=route_label.strip());s.add(r);s.flush();return r.id
        return None
    @app.get('/health')
    def health():return {'status':'ok','milestone':'record-save-view','environment':cfg.environment}
    @app.post('/v1/auth/dev')
    def dev_login(body:DevLogin,s:Database):
        if cfg.environment!='development' or not cfg.dev_login:fail('NOT_FOUND','接口不存在',404)
        return issue(s,'dev:'+body.identity)
    @app.post('/v1/auth/wechat')
    def login(body:Login,s:Database):
        if not cfg.appid or not cfg.appsecret:fail('WECHAT_NOT_CONFIGURED','尚未配置微信登录；本地使用开发身份',503)
        try:
            r=httpx.get('https://api.weixin.qq.com/sns/jscode2session',params={'appid':cfg.appid,'secret':cfg.appsecret,'js_code':body.code,'grant_type':'authorization_code'},timeout=15);r.raise_for_status();data=r.json()
        except (httpx.HTTPError,ValueError):fail('WECHAT_UNAVAILABLE','微信登录暂不可用，请重试',503)
        if not data.get('openid'):fail('WECHAT_LOGIN_FAILED','微信登录失败，请重新登录',401)
        return issue(s,cfg.appid+':'+data['openid'])
    @app.get('/v1/me')
    def me(user:Current,s:Database):
        q=select(Attempt).where(Attempt.owner_id==user.id,Attempt.deleted.is_(None));items=list(s.scalars(q))
        return {'id':user.id,'nickname':user.nickname,'avatar_url':media_url('avatar',user.id) if user.avatar else None,'stats':{'videos':len(items),'days':len({a.climb_date for a in items}),'routes':len({a.route_id for a in items if a.route_id})}}
    @app.put('/v1/me')
    @app.patch('/v1/me')
    def profile(body:Profile,user:Current,s:Database):
        if not body.nickname.strip():fail('INVALID_INPUT','昵称不能为空')
        user.nickname=body.nickname.strip();return {'nickname':user.nickname}
    @app.post('/v1/me/avatar')
    def avatar(user:Current,s:Database,file:UploadFile=File(...)):
        raw=file.file.read(5*1024*1024+1)
        if len(raw)>5*1024*1024:fail('FILE_TOO_LARGE','头像需小于5MB',413)
        try:
            im=Image.open(io.BytesIO(raw));im.load();im=ImageOps.fit(ImageOps.exif_transpose(im).convert('RGB'),(256,256))
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError):fail('INVALID_IMAGE','请选择有效图片')
        key='avatar-'+uuid.uuid4().hex+'.jpg';im.save(cfg.storage_dir/key,quality=88)
        previous=user.avatar;user.avatar=key
        # Old avatars are private and no longer served; maintenance later removes unreferenced files.
        return {'avatar_url':media_url('avatar',user.id)}
    @app.post('/v1/uploads')
    def begin(body:UploadCreate,user:Current,s:Database):
        serialize_key(s,'upload:'+user.id+':'+body.submission_id)
        payload=body.model_dump_json();existing=s.scalar(select(Upload).where(Upload.owner_id==user.id,Upload.submission_id==body.submission_id).with_for_update())
        if existing:
            if existing.request_json!=payload:fail('IDEMPOTENCY_CONFLICT','同一次提交的参数发生变化，请重新选择提交',409)
            if existing.state=='CANCELLED':fail('UPLOAD_CANCELLED','上传已放弃，请重新选择视频',409)
            return {'id':existing.id,'state':existing.state,'attempt_id':existing.attempt_id}
        if body.trim_end-body.trim_start>cfg.max_seconds:fail('TOO_LONG','所选范围超过时长限制')
        if body.route_id:owned(s,Route,body.route_id,user)
        u=Upload(owner_id=user.id,submission_id=body.submission_id,request_json=payload);s.add(u);s.flush()
        return {'id':u.id,'state':u.state,'attempt_id':None}
    @app.get('/v1/uploads/{id}')
    def upload_status(id:str,user:Current,s:Database):
        u=owned(s,Upload,id,user);return {'id':u.id,'state':u.state,'attempt_id':u.attempt_id,'size':u.size}
    @app.post('/v1/uploads/{id}/content')
    def upload_content(id:str,user:Current,s:Database,file:UploadFile=File(...)):
        u=owned(s,Upload,id,user,True)
        if u.state not in ('CREATED','UPLOADED'):fail('UPLOAD_LOCKED','此上传不可修改',409)
        if u.expires<time.time():fail('UPLOAD_EXPIRED','上传会话已过期，请重新选择',410)
        temp=cfg.storage_dir/(id+'.incoming-'+uuid.uuid4().hex);count=0;sha=hashlib.sha256()
        try:
            with temp.open('wb') as out:
                while chunk:=file.file.read(1024*1024):
                    count+=len(chunk)
                    if count>cfg.max_bytes:fail('FILE_TOO_LARGE','视频超过大小限制',413)
                    out.write(chunk);sha.update(chunk)
            if not count:fail('EMPTY_FILE','没有读取到视频内容')
            temp.replace(cfg.storage_dir/(id+'.source'))
        finally:temp.unlink(missing_ok=True)
        u.state='UPLOADED';u.size=count;u.sha256=sha.hexdigest()
        return {'state':u.state,'size':count,'sha256':u.sha256}
    @app.post('/v1/uploads/{id}/commit')
    def commit(id:str,user:Current,s:Database):
        u=owned(s,Upload,id,user,True)
        if u.state=='COMMITTED':return {'attempt_id':u.attempt_id,'state':'COMMITTED'}
        if u.state!='UPLOADED':fail('UPLOAD_NOT_READY','请先完成视频上传',409)
        if u.expires<time.time():fail('UPLOAD_EXPIRED','上传会话已过期',410)
        try:info=probe(cfg.storage_dir/(id+'.source'))
        except MediaError as e:fail('INVALID_VIDEO',str(e),422)
        body=UploadCreate.model_validate_json(u.request_json)
        if info['duration']>cfg.max_seconds+.2:fail('TOO_LONG','整段视频超过时长限制，请先在相册裁短',422)
        if body.trim_end>info['duration']+.15:fail('INVALID_TRIM','结束时间超过实际视频时长',422)
        if info['width']*info['height']>3840*2160*2:fail('RESOLUTION_TOO_HIGH','视频分辨率过高，请选择较小视频',422)
        route_id=resolve_route(s,user,body.route_id,body.route_name)
        a=Attempt(owner_id=user.id,upload_id=u.id,name=body.name.strip() or '攀爬记录',climb_date=body.climb_date.isoformat(),route_id=route_id,duration=info['duration'],trim_start=body.trim_start,trim_end=min(body.trim_end,info['duration']),width=info['width'],height=info['height'])
        s.add(a);s.flush();s.add(Job(attempt_id=a.id));u.state='COMMITTED';u.attempt_id=a.id
        return {'attempt_id':a.id,'state':'COMMITTED'}
    @app.delete('/v1/uploads/{id}')
    def cancel(id:str,user:Current,s:Database):
        u=owned(s,Upload,id,user,True)
        if u.state=='COMMITTED':return {'state':'COMMITTED','attempt_id':u.attempt_id}
        u.state='CANCELLED';return {'state':'CANCELLED'}
    @app.get('/v1/attempts')
    def listing(user:Current,s:Database,cursor:str|None=None,completion:str|None=None,route_id:str|None=None,limit:int=Query(20,ge=1,le=50)):
        q=select(Attempt).where(Attempt.owner_id==user.id,Attempt.deleted.is_(None))
        if completion:q=q.where(Attempt.completion==completion)
        if route_id:q=q.where(Attempt.route_id==route_id)
        if cursor:
            try:c,aid=json.loads(base64.urlsafe_b64decode(cursor).decode());c=float(c)
            except Exception:fail('INVALID_CURSOR','分页参数无效')
            q=q.where((Attempt.created<c)|((Attempt.created==c)&(Attempt.id<aid)))
        items=list(s.scalars(q.order_by(Attempt.created.desc(),Attempt.id.desc()).limit(limit+1)));more=len(items)>limit;items=items[:limit]
        next_cursor=base64.urlsafe_b64encode(json.dumps([items[-1].created,items[-1].id]).encode()).decode() if more else None
        return {'items':[serialize(s,a) for a in items],'next_cursor':next_cursor}
    @app.get('/v1/attempts/{id}')
    def detail(id:str,user:Current,s:Database):return serialize(s,owned(s,Attempt,id,user))
    @app.get('/v1/attempts/{id}/pose')
    def pose_status(id: str, user: Current, s: Database):
        attempt = owned(s, Attempt, id, user)
        job = s.get(PoseJob, id)
        if job and job.state == 'READY':
            result = cfg.storage_dir / (attempt.id + '.pose.json')
            if result.is_file():
                return FileResponse(result, media_type='application/json')
            return {'state': 'FAILED'}
        return {'state': job.state if job else 'NOT_STARTED'}

    @app.post('/v1/attempts/{id}/pose')
    def queue_pose(id: str, user: Current, s: Database):
        attempt = owned(s, Attempt, id, user, True)
        if attempt.state != 'PLAYABLE':
            fail('VIDEO_NOT_READY', '请等待视频准备完成', 409)
        if not cfg.pose_model or not Path(cfg.pose_model).is_file():
            fail('POSE_UNAVAILABLE', '本地姿态模型未配置', 503)
        job = s.get(PoseJob, id)
        if not job:
            job = PoseJob(attempt_id=id, state='QUEUED')
            s.add(job)
        elif job.state == 'FAILED' or (job.state == 'READY' and not (cfg.storage_dir / (id + '.pose.json')).is_file()):
            job.state = 'QUEUED'
            job.attempts = 0
        return {'state': job.state}

    @app.get('/v1/attempts/{id}/playback')
    def playback(id:str,user:Current,s:Database):
        a=owned(s,Attempt,id,user)
        if a.state!='PLAYABLE':fail('VIDEO_NOT_READY','视频正在准备或需要重试',409)
        return {'url':media_url('video',id),'expires_in':900,'media_version':'playback-v1','duration':a.trim_end-a.trim_start}
    @app.put('/v1/attempts/{id}')
    @app.patch('/v1/attempts/{id}')
    def patch(id:str,body:AttemptPatch,user:Current,s:Database):
        a=owned(s,Attempt,id,user,True)
        if a.revision!=body.revision:fail('REVISION_CONFLICT','记录已更新，请刷新后重试',409)
        if body.name is not None:
            if not body.name.strip():fail('INVALID_INPUT','名称不能为空')
            a.name=body.name.strip()
        if body.climb_date:a.climb_date=body.climb_date.isoformat()
        if body.completion:a.completion=body.completion
        if 'route_name' in body.model_fields_set or 'route_id' in body.model_fields_set:
            if body.route_name and body.route_id:fail('INVALID_ROUTE','请选择已有线路或输入新线路')
            a.route_id=resolve_route(s,user,body.route_id,body.route_name)
        a.revision+=1;return serialize(s,a)
    @app.delete('/v1/attempts/{id}')
    def delete(id:str,user:Current,s:Database):
        a=owned(s,Attempt,id,user,True);a.deleted=time.time();a.state='DELETED';job=s.scalar(select(Job).where(Job.attempt_id==id).with_for_update())
        if job:job.state='CANCELLED'
        return {'state':'DELETED'}
    @app.post('/v1/attempts/{id}/retry')
    def retry(id:str,user:Current,s:Database):
        a=owned(s,Attempt,id,user,True);job=s.scalar(select(Job).where(Job.attempt_id==id).with_for_update())
        if a.state!='FAILED':return {'state':a.state}
        if job.attempts>=5:fail('RETRY_LIMIT','重试次数已用尽，请联系维护者',429)
        a.state='PREPARING';a.error='';job.state='QUEUED';job.lease=0;return {'state':a.state}
    @app.get('/v1/routes')
    def routes(user:Current,s:Database):
        rs=list(s.scalars(select(Route).where(Route.owner_id==user.id).order_by(Route.name)))
        return {'items':[{'id':r.id,'name':r.name,'count':s.scalar(select(func.count()).select_from(Attempt).where(Attempt.route_id==r.id,Attempt.deleted.is_(None)))} for r in rs]}
    @app.post('/v1/routes')
    def add_route(body:RouteCreate,user:Current,s:Database):
        if not body.name.strip():fail('INVALID_INPUT','名称不能为空')
        r=Route(owner_id=user.id,name=body.name.strip());s.add(r);s.flush();return {'id':r.id,'name':r.name}
    @app.get('/v1/media/{kind}/{id}')
    def media(kind:str,id:str,expires:int,sig:str,s:Database):
        if expires<time.time() or expires>time.time()+901 or not hmac.compare_digest(sig,signature(kind,id,expires)):fail('MEDIA_EXPIRED','播放地址已失效，请重新打开记录',403)
        if kind=='avatar':
            u=s.get(User,id)
            if not u or not u.avatar:fail('NOT_FOUND','头像不存在',404)
            path=cfg.storage_dir/u.avatar;mime='image/jpeg'
        else:
            a=s.get(Attempt,id)
            if not a or a.deleted or a.state!='PLAYABLE':fail('NOT_FOUND','视频不可用',404)
            if kind not in ('video','poster'):fail('NOT_FOUND','资源不存在',404)
            path=cfg.storage_dir/(id+('.mp4' if kind=='video' else '.jpg'));mime='video/mp4' if kind=='video' else 'image/jpeg'
        if not path.exists():fail('NOT_FOUND','资源正在准备，请稍后重试',404)
        return FileResponse(path,media_type=mime,headers={'Cache-Control':'private, no-store'})
    # Local integration client shares the real API/database. Never enabled in production.
    dev_dir=Path(__file__).parent.parent/'devclient'
    if cfg.environment=='development' and cfg.dev_login and dev_dir.exists():app.mount('/dev',StaticFiles(directory=dev_dir,html=True),name='dev')
    return app
