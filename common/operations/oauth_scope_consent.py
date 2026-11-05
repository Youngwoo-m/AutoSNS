"""서버가 명시 등록한 발행 scope 동의 경계. 실제 앱·비용·발행 권한을 증명하지 않는다."""
from dataclasses import dataclass
from .content_store import StoreError


def _blocked():raise StoreError('oauth_scope_blocked')
def _string(value):return type(value) is str and bool(value.strip()) and len(value)<=512 and not any(ord(c)<32 for c in value)
def _scopes(value):
    if type(value) not in (tuple,list) or len(value)>100 or any(not _string(x) for x in value) or len(set(value))!=len(value):_blocked()
    return tuple(value)


@dataclass(frozen=True)
class PublicationConsentRegistration:
    provider_id:str
    client_revision:int
    cost_evidence_revision:str
    approved_scopes:tuple
    def __post_init__(self):
        if not _string(self.provider_id) or type(self.client_revision) is not int or self.client_revision<1 or not _string(self.cost_evidence_revision):_blocked()
        object.__setattr__(self,'approved_scopes',_scopes(self.approved_scopes))


@dataclass(frozen=True)
class PublicationScopeConsentPolicy:
    revision:str=''
    registrations:tuple=()
    def __post_init__(self):
        if type(self.revision) is not str or self.revision and not _string(self.revision) or type(self.registrations) not in (tuple,list):_blocked()
        rows=tuple(self.registrations)
        if any(type(row) is not PublicationConsentRegistration for row in rows) or len({row.provider_id for row in rows})!=len(rows) or rows and not self.revision:_blocked()
        object.__setattr__(self,'registrations',rows)

    def validate(self,definition,client,requested_scopes):
        requested=set(_scopes(requested_scopes))
        if not requested<=set(client.approved_scopes):_blocked()
        if requested<=set(definition.read_scopes):return None
        if definition.id in ('tiktok','naver','tistory') or not definition.publication_scopes:_blocked()
        registration=next((r for r in self.registrations if r.provider_id==definition.id),None)
        if (registration is None or client.provider_id!=definition.id
                or registration.client_revision!=client.client_revision
                or registration.cost_evidence_revision!=client.cost_evidence_revision
                or set(registration.approved_scopes)!=set(client.approved_scopes)
                or requested!=set(definition.read_scopes)|set(definition.publication_scopes)):_blocked()
        return None
