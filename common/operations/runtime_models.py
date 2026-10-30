"""외부 I/O 없는 실제 실행 계약. 계획 컨텍스트와 별개인 불변 스냅샷."""
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from collections.abc import Mapping
import hashlib
import json
from .models import ContractError, _freeze_json, thaw


def utc(value):
    if isinstance(value,str):
        try: value=datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError as exc: raise ContractError('invalid_time') from exc
    if not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ContractError('invalid_time')
    return value.astimezone(timezone.utc)


def serial(value):
    if isinstance(value,datetime): return utc(value).isoformat()
    if isinstance(value,Mapping): return {k:serial(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [serial(v) for v in value]
    return value


class RuntimeModel:
    def to_dict(self,**kwargs):return {f.name:serial(getattr(self,f.name)) for f in fields(self)}


def strings(obj,names):
    for name in names:
        if not isinstance(getattr(obj,name),str) or not getattr(obj,name):raise ContractError('invalid_runtime',name)


def time_fields(obj,names):
    for name in names:object.__setattr__(obj,name,utc(getattr(obj,name)))


@dataclass(frozen=True)
class PublicationContext(RuntimeModel):
    content_id:str
    content_revision:int
    manifest_hash:str
    owner_account_id:str
    destination_account_id:str
    connection_id:str
    target_id:str
    publication_purpose:str
    schedule_slot:str
    options:Mapping
    schedule_condition:Mapping
    registry_revision:str
    policy_revision:str
    auth_checked_at:datetime
    auth_expires_at:datetime
    review_report_hashes:tuple
    run_id:str=''
    platform:str=''
    scope:str='publication'
    def __post_init__(self):
        strings(self,('content_id','manifest_hash','owner_account_id','destination_account_id','connection_id','target_id','publication_purpose','schedule_slot','registry_revision','policy_revision'))
        if type(self.content_revision) is not int or self.content_revision<1 or self.scope!='publication':raise ContractError('invalid_runtime')
        if not isinstance(self.run_id,str) or not isinstance(self.platform,str):raise ContractError('invalid_runtime')
        for name in ('options','schedule_condition'):
            if not isinstance(getattr(self,name),Mapping):raise ContractError('invalid_runtime')
            object.__setattr__(self,name,_freeze_json(getattr(self,name)))
        if not isinstance(self.review_report_hashes,(tuple,list)) or len(self.review_report_hashes)<1 or not all(isinstance(x,str) and x for x in self.review_report_hashes) or len(set(self.review_report_hashes))!=len(self.review_report_hashes):raise ContractError('independent_review_required')
        object.__setattr__(self,'review_report_hashes',tuple(self.review_report_hashes))
        time_fields(self,('auth_checked_at','auth_expires_at'))
        if self.auth_checked_at>=self.auth_expires_at:raise ContractError('invalid_time')
    @property
    def context_hash(self):return hashlib.sha256(json.dumps(self.to_dict(),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class RunLease(RuntimeModel):
    run_id:str
    worker_id:str
    generation:int
    expires_at:datetime
    def __post_init__(self):
        strings(self,('run_id','worker_id'))
        if type(self.generation) is not int or self.generation<1:raise ContractError('invalid_runtime')
        time_fields(self,('expires_at',))


@dataclass(frozen=True)
class SubmissionPermit(RuntimeModel):
    attempt_id:str
    nonce:str
    run_id:str
    generation:int
    expires_at:datetime
    context_hash:str
    approval_hash:str
    def __post_init__(self):
        strings(self,('attempt_id','nonce','run_id','context_hash','approval_hash'))
        if type(self.generation) is not int or self.generation<1:raise ContractError('invalid_runtime')
        time_fields(self,('expires_at',))
    def __repr__(self):return 'SubmissionPermit(<redacted>)'
    def to_dict(self,**kwargs):
        result=super().to_dict();result.pop('nonce');return result


@dataclass(frozen=True)
class SubmissionResult(RuntimeModel):
    outcome:str
    remote_id:str|None=None
    url:str|None=None
    scheduled_at:datetime|None=None
    evidence:Mapping=field(default_factory=dict)
    def __post_init__(self):
        if self.outcome not in ('submitted','scheduled','unknown','failed'):raise ContractError('invalid_runtime')
        for name in ('remote_id','url'):
            if getattr(self,name) is not None and not isinstance(getattr(self,name),str):raise ContractError('invalid_runtime')
        if self.scheduled_at is not None:time_fields(self,('scheduled_at',))
        if not isinstance(self.evidence,Mapping):raise ContractError('invalid_runtime')
        object.__setattr__(self,'evidence',_freeze_json(self.evidence))


@dataclass(frozen=True)
class LookupResult(RuntimeModel):
    outcome:str
    candidates:tuple=()
    evidence:Mapping=field(default_factory=dict)
    def __post_init__(self):
        if self.outcome not in ('matched','ambiguous','not_found','unsupported','error'):raise ContractError('invalid_runtime')
        if not isinstance(self.candidates,(tuple,list)):raise ContractError('invalid_runtime')
        object.__setattr__(self,'candidates',_freeze_json(self.candidates))
        if not isinstance(self.evidence,Mapping):raise ContractError('invalid_runtime')
        object.__setattr__(self,'evidence',_freeze_json(self.evidence))


@dataclass(frozen=True)
class VerificationResult(RuntimeModel):
    outcome:str
    checked_at:datetime
    evidence:Mapping=field(default_factory=dict)
    def __post_init__(self):
        if self.outcome not in ('verified','pending','failed','unsupported','error'):raise ContractError('invalid_runtime')
        time_fields(self,('checked_at',))
        if not isinstance(self.evidence,Mapping):raise ContractError('invalid_runtime')
        object.__setattr__(self,'evidence',_freeze_json(self.evidence))


@dataclass(frozen=True)
class ExecutionPolicy(RuntimeModel):
    enabled:bool=False
    allowed_connection_ids:tuple=()
    cutover_revision:str=''
    provider_policy:Mapping=field(default_factory=dict)
    def __post_init__(self):
        if type(self.enabled) is not bool or not isinstance(self.cutover_revision,str) or not isinstance(self.allowed_connection_ids,(list,tuple)) or not all(isinstance(x,str) and x for x in self.allowed_connection_ids):raise ContractError('invalid_runtime')
        if self.enabled and not self.cutover_revision:raise ContractError('cutover_required')
        if not isinstance(self.provider_policy,Mapping):raise ContractError('invalid_runtime')
        object.__setattr__(self,'allowed_connection_ids',tuple(self.allowed_connection_ids));object.__setattr__(self,'provider_policy',_freeze_json(self.provider_policy))
