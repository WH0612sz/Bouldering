from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Text, Float, Integer, ForeignKey, UniqueConstraint
import time, uuid

def uid(): return uuid.uuid4().hex
class Base(DeclarativeBase): pass
class User(Base):
    __tablename__='users'
    id: Mapped[str]=mapped_column(String(32),primary_key=True,default=uid)
    identity: Mapped[str]=mapped_column(String(128),unique=True)
    nickname: Mapped[str]=mapped_column(String(24),default='攀岩爱好者')
    avatar: Mapped[str]=mapped_column(String(100),default='')
class Session(Base):
    __tablename__='sessions'
    token_hash: Mapped[str]=mapped_column(String(64),primary_key=True)
    user_id: Mapped[str]=mapped_column(ForeignKey('users.id'))
    expires: Mapped[float]=mapped_column(Float)
class Route(Base):
    __tablename__='routes'
    id: Mapped[str]=mapped_column(String(32),primary_key=True,default=uid)
    owner_id: Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    name: Mapped[str]=mapped_column(String(60))
class Upload(Base):
    __tablename__='uploads'
    __table_args__=(UniqueConstraint('owner_id','submission_id'),)
    id: Mapped[str]=mapped_column(String(32),primary_key=True,default=uid)
    owner_id: Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    submission_id: Mapped[str]=mapped_column(String(80))
    request_json: Mapped[str]=mapped_column(Text)
    state: Mapped[str]=mapped_column(String(20),default='CREATED')
    size: Mapped[int]=mapped_column(Integer,default=0)
    sha256: Mapped[str]=mapped_column(String(64),default='')
    created: Mapped[float]=mapped_column(Float,default=time.time)
    expires: Mapped[float]=mapped_column(Float,default=lambda:time.time()+86400)
    attempt_id: Mapped[str|None]=mapped_column(String(32),nullable=True)
class Attempt(Base):
    __tablename__='attempts'
    id: Mapped[str]=mapped_column(String(32),primary_key=True,default=uid)
    owner_id: Mapped[str]=mapped_column(ForeignKey('users.id'),index=True)
    upload_id: Mapped[str]=mapped_column(ForeignKey('uploads.id'),unique=True)
    name: Mapped[str]=mapped_column(String(80))
    climb_date: Mapped[str]=mapped_column(String(10))
    route_id: Mapped[str|None]=mapped_column(ForeignKey('routes.id'),nullable=True)
    completion: Mapped[str]=mapped_column(String(20),default='未标记')
    duration: Mapped[float]=mapped_column(Float)
    trim_start: Mapped[float]=mapped_column(Float)
    trim_end: Mapped[float]=mapped_column(Float)
    width: Mapped[int]=mapped_column(Integer)
    height: Mapped[int]=mapped_column(Integer)
    state: Mapped[str]=mapped_column(String(24),default='PREPARING')
    error: Mapped[str]=mapped_column(String(200),default='')
    revision: Mapped[int]=mapped_column(Integer,default=1)
    created: Mapped[float]=mapped_column(Float,default=time.time,index=True)
    deleted: Mapped[float|None]=mapped_column(Float,nullable=True)
class Job(Base):
    __tablename__='jobs'
    id: Mapped[str]=mapped_column(String(32),primary_key=True,default=uid)
    attempt_id: Mapped[str]=mapped_column(ForeignKey('attempts.id'),unique=True)
    state: Mapped[str]=mapped_column(String(20),default='QUEUED')
    attempts: Mapped[int]=mapped_column(Integer,default=0)
    lease: Mapped[float]=mapped_column(Float,default=0)
    error: Mapped[str]=mapped_column(String(200),default='')


class PoseJob(Base):
    __tablename__ = 'pose_jobs'
    attempt_id: Mapped[str] = mapped_column(ForeignKey('attempts.id'), primary_key=True)
    state: Mapped[str] = mapped_column(String(20), default='QUEUED')
    lease: Mapped[float] = mapped_column(Float, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
