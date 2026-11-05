"""개인·학과 Facebook Pages 텍스트 adapter. 외부 I/O는 서버 등록 bridge에서만 실행한다."""
from collections.abc import Mapping
from datetime import datetime,timezone
import hashlib
from urllib.parse import urlsplit
import re
from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext,SubmissionResult,LookupResult,VerificationResult,utc
from common.operations.verification import strong_identity
from .credential_bindings import validate_publication_credential_binding
from .facebook_payloads import build_facebook_payload,validate_facebook_text,PREPARED_KEYS,NUMERIC_ID

_BINDINGS={'personal.facebook':'facebook.personal','dept.facebook':'facebook.dept'}
_POST=re.compile(r'([0-9]{1,64})_([0-9]{1,64})')
_CORE=('remote_id','target_id','destination_account_id','created_at','body_sha256','media_sha256','visibility')


def _numeric(value):return type(value) is str and NUMERIC_ID.fullmatch(value) is not None

def _post(value,target):
    if type(value) is not str:return False
    match=_POST.fullmatch(value)
    return match is not None and match.group(1)==target

def _safe_url(value):
    if type(value) is not str or len(value)>2000 or any(ord(c)<=32 or ord(c)==127 for c in value):return None
    try:
        parsed=urlsplit(value)
        if (parsed.scheme=='https' and parsed.netloc in ('facebook.com','www.facebook.com')
                and parsed.hostname in ('facebook.com','www.facebook.com') and parsed.username is None
                and parsed.password is None and parsed.port is None and not parsed.query and not parsed.fragment
                and parsed.path.startswith('/') and bool(parsed.path.strip('/'))):
            return value
    except ValueError:pass
    return None


def _observation(value):
    if not isinstance(value,Mapping):return None
    if (not _numeric(value.get('target_id')) or not _post(value.get('remote_id'),value.get('target_id'))
            or value.get('destination_account_id') not in ('personal','dept')
            or type(value.get('body_sha256')) is not str or len(value['body_sha256'])!=64
            or any(c not in '0123456789abcdef' for c in value['body_sha256'])
            or not isinstance(value.get('media_sha256'),(list,tuple)) or list(value['media_sha256'])!=[]
            or value.get('visibility') not in ('public','private','unlisted','unknown')):
        return None
    try:
        text=validate_facebook_text(value.get('text'))
        if hashlib.sha256(text.encode('utf-8')).hexdigest()!=value['body_sha256']:return None
        utc(value.get('created_at'))
    except Exception:return None
    result={key:value.get(key) for key in _CORE}
    result['created_at']=utc(value['created_at']).isoformat()
    result['media_sha256']=[]
    url=_safe_url(value.get('url'))
    if value.get('visibility')=='public' and url is None:return None
    if url is not None:result['url']=url
    return result


class FacebookAdapter:
    platform='facebook'
    def __init__(self,registry,bridge):self.registry,self.bridge=registry,bridge
    def _binding(self,ctx):
        if not isinstance(ctx,PublicationContext):raise ContractError('publication_context_required')
        connection=self.registry.connections.get(ctx.connection_id);executor=_BINDINGS.get(ctx.connection_id)
        if (not executor or not connection or ctx.platform!='facebook' or connection.platform!='facebook'
                or connection.account_id!=ctx.destination_account_id or connection.target_id!=ctx.target_id
                or ctx.registry_revision!=self.registry.revision or not _numeric(ctx.target_id)):
            raise ContractError('facebook_context_mismatch')
        try:validate_publication_credential_binding(self.registry,connection)
        except ContractError:raise ContractError('facebook_context_mismatch') from None
        return executor
    def inspect_target(self,ctx):return self.bridge.read(self._binding(ctx),'inspect_target',ctx,{})
    def prepare(self,ctx,snapshot):
        self._binding(ctx);return build_facebook_payload(snapshot,ctx)
    def submit(self,ctx,prepared,permit):
        executor=self._binding(ctx)
        if (not isinstance(prepared,Mapping) or set(prepared)!=set(PREPARED_KEYS)
                or set(ctx.options)-{'text_only','visibility'} or ctx.options.get('text_only') is not True or ctx.options.get('visibility','public')!='public'
                or any(prepared.get(name)!=getattr(ctx,name) for name in PREPARED_KEYS if name not in ('text','body_sha256','media_sha256'))
                or not isinstance(prepared.get('media_sha256'),(list,tuple)) or list(prepared['media_sha256'])!=[]):
            raise ContractError('facebook_prepared_mismatch')
        text=validate_facebook_text(prepared.get('text'))
        if prepared.get('body_sha256')!=hashlib.sha256(text.encode('utf-8')).hexdigest():raise ContractError('facebook_prepared_mismatch')
        if self.registry.connections[ctx.connection_id].credential_ref.startswith('oauth:'):
            return SubmissionResult('failed',evidence={'reason':'managed_publication_unverified','confirmed_not_submitted':True})
        try:
            raw=self.bridge.submit(executor,ctx,prepared,permit)
            if not isinstance(raw,Mapping) or raw.get('outcome') not in ('submitted','unknown','failed'):
                return SubmissionResult('unknown',evidence={'reason':'invalid_facebook_result'})
            if raw['outcome']=='submitted':
                url=_safe_url(raw.get('url'))
                if not _post(raw.get('remote_id'),ctx.target_id):return SubmissionResult('unknown',evidence={'reason':'invalid_facebook_result'})
                return SubmissionResult('submitted',remote_id=raw['remote_id'],url=url)
            evidence={'reason':'facebook_submission_failed' if raw['outcome']=='failed' else 'facebook_submission_uncertain'}
            if raw['outcome']=='failed' and isinstance(raw.get('evidence'),Mapping) and raw['evidence'].get('confirmed_not_submitted') is True:evidence['confirmed_not_submitted']=True
            known=raw.get('remote_id') if raw['outcome']=='unknown' and _post(raw.get('remote_id'),ctx.target_id) else None
            return SubmissionResult(raw['outcome'],remote_id=known,evidence=evidence)
        except Exception:return SubmissionResult('unknown',evidence={'reason':'facebook_submission_uncertain'})
    def lookup(self,ctx,attempt):
        executor=self._binding(ctx)
        if not isinstance(attempt,Mapping):return LookupResult('unsupported',evidence={'reason':'attempt_required'})
        prior=attempt.get('result');known=attempt.get('remote_id') or (prior.get('remote_id') if isinstance(prior,Mapping) else None)
        if not _post(known,ctx.target_id):return LookupResult('unsupported',evidence={'reason':'known_remote_id_required'})
        try:
            raw=self.bridge.read(executor,'lookup',ctx,{'attempt':{'remote_id':known,'created_at':attempt.get('created_at')}})
            candidates=raw.get('candidates')
            if not isinstance(candidates,list):raise ValueError()
            safe=[_observation(item) for item in candidates]
            if any(item is None for item in safe):return LookupResult('unsupported',evidence={'reason':'remote_evidence_incomplete'})
            store=getattr(getattr(self.bridge,'store',None),'content_store',None)
            if store is None:return LookupResult('unsupported',safe,{'reason':'approved_snapshot_unavailable'})
            snapshot=store.get(ctx.content_id,ctx.content_revision);build_facebook_payload(snapshot,ctx)
            matched=[item for item in safe if strong_identity(ctx.to_dict(),snapshot,item,attempt,raw['checked_at'],remote_id=known)]
            if len(safe)==1 and len(matched)==1:return LookupResult('matched',matched)
            return LookupResult('ambiguous' if safe else 'unsupported',safe,{'reason':'remote_evidence_incomplete' if safe else 'remote_absence_unproven'})
        except Exception:return LookupResult('error',evidence={'reason':'facebook_lookup_error'})
    def verify(self,ctx,remote_id,snapshot):
        executor=self._binding(ctx);now=datetime.now(timezone.utc)
        try:
            expected=build_facebook_payload(snapshot,ctx)
            if not _post(remote_id,ctx.target_id):return VerificationResult('failed',now,{'reason':'remote_identity_mismatch'})
            raw=self.bridge.read(executor,'verify',ctx,{'remote_id':remote_id});checked=utc(raw['checked_at'])
            original=raw.get('observation')
            if not isinstance(original,Mapping):return VerificationResult('pending',checked,{'reason':'remote_observation_unavailable'})
            if (original.get('remote_id')!=remote_id or original.get('target_id')!=ctx.target_id
                    or original.get('destination_account_id')!=ctx.destination_account_id):
                return VerificationResult('failed',checked,{'reason':'remote_identity_mismatch'})
            if original.get('body_sha256')!=expected['body_sha256'] or not isinstance(original.get('media_sha256'),(list,tuple)) or list(original['media_sha256'])!=[]:
                return VerificationResult('failed',checked,{'reason':'remote_identity_mismatch'})
            item=_observation(original)
            if item is None:return VerificationResult('pending',checked,{'reason':'remote_observation_unavailable'})
            if item['body_sha256']!=expected['body_sha256'] or list(item['media_sha256'])!=[]:
                return VerificationResult('failed',checked,item)
            if utc(item['created_at'])>checked:return VerificationResult('pending',checked,{'reason':'remote_evidence_incomplete'})
            if original.get('processing_status') in ('failed','rejected','terminated'):
                return VerificationResult('failed',checked,dict(item,reason='remote_processing_failed'))
            return VerificationResult('verified' if item['visibility']=='public' else 'pending',checked,item)
        except Exception:return VerificationResult('error',now,{'reason':'facebook_verification_error'})


def build_adapter(registry,bridge):return FacebookAdapter(registry,bridge)

def bridge_bootstrap():
    from .facebook_runtime import bridge_bootstrap as bootstrap
    return bootstrap()

if __name__=='__main__':
    from .bridge_host import main
    raise SystemExit(main(bootstrap=bridge_bootstrap,bootstrap_module=__spec__.name))
