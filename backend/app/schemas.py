from pydantic import BaseModel, Field, model_validator
from typing import Literal
from datetime import date
import math
class Login(BaseModel): code:str=Field(min_length=1,max_length=256)
class DevLogin(BaseModel): identity:str=Field(min_length=1,max_length=40,pattern=r'^[a-zA-Z0-9_-]+$')
class Profile(BaseModel): nickname:str=Field(min_length=1,max_length=24)
class UploadCreate(BaseModel):
    submission_id:str=Field(min_length=8,max_length=80)
    name:str=Field(min_length=1,max_length=80)
    climb_date:date
    trim_start:float=Field(ge=0)
    trim_end:float=Field(gt=0)
    route_id:str|None=None
    route_name:str|None=Field(default=None,max_length=60)
    @model_validator(mode='after')
    def valid_range(self):
        if not math.isfinite(self.trim_start) or not math.isfinite(self.trim_end) or self.trim_end<=self.trim_start: raise ValueError('无效裁剪范围')
        if self.route_id and self.route_name: raise ValueError('线路ID和新线路名称不能同时传入')
        return self
class AttemptPatch(BaseModel):
    revision:int
    name:str|None=Field(default=None,min_length=1,max_length=80)
    climb_date:date|None=None
    completion:Literal['未标记','未完成','已完成']|None=None
    route_id:str|None=None
    route_name:str|None=Field(default=None,max_length=60)
class RouteCreate(BaseModel): name:str=Field(min_length=1,max_length=60)
