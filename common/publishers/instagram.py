"""개인·학과 Instagram adapter. 원본 전달 영수증과 원격 변환 매체를 구분한다.

이 경계의 구조 검사는 실제 승인·권리·파일 공개 동의나 원본 전달의 독립 증명이 아니다.
최종 원본 정체성은 영속 attempt와 instagram_upload_identity가 함께 검증한다.
"""
from collections.abc import Mapping
from datetime import datetime,timezone
import hashlib
from common.operations.admission_context import AdmissionReadContext
from common.operations.models import ContractError,thaw
from common.operations.runtime_models import PublicationContext,SubmissionResult,LookupResult,VerificationResult,utc
from common.operations.instagram_evidence import UPLOAD_RECEIPT_KEYS,instagram_upload_identity,safe_instagram_url
from .credential_bindings import validate_publication_credential_binding
from .instagram_payloads import PREPARED_KEYS,NUMERIC_ID,SHA256,build_instagram_payload,select_instagram_assets,validate_instagram_caption

_BINDINGS={'personal.instagram':'instagram.personal','dept.instagram':'instagram.dept'}
OBSERVATION_KEYS=('remote_id','target_id','created_at','text','body_sha256','media_sha256',
    'media_format','media_type','media_product_type','media_status','children','visibility','url','upload_receipt')
_ASSET_KEYS=frozenset(('id','sha256','size','media_type'))
_TYPE={'image':'IMAGE','reels':'VIDEO','carousel':'CAROUSEL_ALBUM'}


def _id(value):return type(value) is str and NUMERIC_ID.fullmatch(value) is not None


def validate_instagram_prepared(ctx,prepared):
    if not isinstance(ctx,PublicationContext):raise ContractError('publication_context_required')
    if not isinstance(prepared,Mapping) or set(prepared)!=set(PREPARED_KEYS):raise ContractError('instagram_prepared_mismatch')
    source=dict(id=ctx.content_id,revision=ctx.content_revision,manifest_hash=ctx.manifest_hash,
        owner_account_id=ctx.owner_account_id,original=prepared.get('caption'),variants=[],assets=prepared.get('assets'))
    expected=build_instagram_payload(source,ctx)
    if expected!=thaw(prepared):raise ContractError('instagram_prepared_mismatch')
    return expected


def _children(value,assets=None):
    if not isinstance(value,(list,tuple)) or len(value)>10:raise ValueError()
    result=[]
    for row in value:
        if not isinstance(row,Mapping) or set(row)!={'id','media_type'} or not _id(row['id']) or row['media_type'] not in ('IMAGE','VIDEO'):raise ValueError()
        result.append(dict(id=row['id'],media_type=row['media_type']))
    if len({row['id'] for row in result})!=len(result):raise ValueError()
    if assets is not None and (len(result)!=len(assets) or any(row['media_type']!=('IMAGE' if asset['media_type']=='image/jpeg' else 'VIDEO') for row,asset in zip(result,assets))):raise ValueError()
    return result


def sanitize_instagram_upload_receipt(value,ctx,prepared=None,remote_id=None):
    """비밀 URL을 포함하지 않는 정확한 영수증 구조만 복사한다. 실제 전달 증명은 별도다."""
    try:
        if not isinstance(ctx,PublicationContext) or not isinstance(value,Mapping) or set(value)!=UPLOAD_RECEIPT_KEYS:return None
        if value['kind']!='instagram_upload_receipt_v1' or value['context_hash']!=ctx.context_hash:return None
        if any(value[k]!=getattr(ctx,k) for k in ('connection_id','target_id','owner_account_id','destination_account_id','content_id','content_revision','manifest_hash')) or type(value['content_revision']) is not int:return None
        if not _id(value['remote_id']) or remote_id is not None and value['remote_id']!=remote_id or not _id(value['creation_id']):return None
        if type(value['caption_sha256']) is not str or SHA256.fullmatch(value['caption_sha256']) is None:return None
        assets=value['assets']
        if not isinstance(assets,(list,tuple)) or any(not isinstance(asset,Mapping) or set(asset)!=_ASSET_KEYS for asset in assets):return None
        selected=select_instagram_assets(dict(assets=assets),ctx.options.get('instagram'))
        if thaw(assets)!=selected or value['media_format']!=ctx.options['instagram']['format']:return None
        if prepared is not None and (selected!=thaw(prepared['assets']) or value['caption_sha256']!=prepared['caption_sha256'] or value['media_format']!=prepared['media_format']):return None
        children=value['child_creation_ids'];carousel=value['media_format']=='carousel'
        if not isinstance(children,(list,tuple)) or len(children)!=(len(selected) if carousel else 0) or any(not _id(identifier) for identifier in children) or len(set(children))!=len(children) or value['creation_id'] in children:return None
        pin=value['published_children']
        if carousel:pin=None if pin is None else _children(pin,selected)
        elif not isinstance(pin,(list,tuple)) or len(pin):return None
        else:pin=[]
        result={key:value[key] for key in UPLOAD_RECEIPT_KEYS if key not in ('assets','child_creation_ids','published_children')}
        result.update(assets=selected,child_creation_ids=list(children),published_children=pin)
        return result
    except Exception:return None


def sanitize_instagram_observation(value,ctx,remote_id,prepared=None):
    """실 캡션을 재해시하되 원격 미디어 해시를 원본 자산 해시로 합성하지 않는다."""
    try:
        if (not isinstance(value,Mapping) or not _id(remote_id) or value.get('remote_id')!=remote_id
                or value.get('target_id')!=ctx.target_id or value.get('destination_account_id') not in (None,ctx.destination_account_id)
                or value.get('media_sha256') is not None or 'media_sha256' not in value
                or value.get('visibility') not in ('public','private','unknown') or value.get('media_status')!='readable'):return None
        caption=validate_instagram_caption(value.get('text'));digest=hashlib.sha256(caption.encode('utf-8')).hexdigest()
        if value.get('body_sha256')!=digest:return None
        fmt=ctx.options['instagram']['format']
        if value.get('media_format')!=fmt or value.get('media_type')!=_TYPE[fmt] or value.get('media_product_type')!=('REELS' if fmt=='reels' else 'FEED'):return None
        receipt=sanitize_instagram_upload_receipt(value.get('upload_receipt'),ctx,prepared,remote_id)
        assets=prepared['assets'] if prepared is not None else receipt['assets'] if receipt is not None else None
        children=_children(value.get('children'),assets if fmt=='carousel' else None)
        if fmt!='carousel' and children:return None
        if fmt=='carousel' and len(children)!=len(ctx.options['instagram']['asset_ids']):return None
        url=safe_instagram_url(value.get('url'))
        if url is None:return None
        result=dict(remote_id=remote_id,target_id=ctx.target_id,destination_account_id=ctx.destination_account_id,
            created_at=utc(value.get('created_at')).isoformat(),text=caption,body_sha256=digest,media_sha256=None,
            media_format=fmt,media_type=value['media_type'],media_product_type=value['media_product_type'],
            media_status='readable',children=children,visibility=value['visibility'],url=url,upload_receipt=receipt)
        return result
    except Exception:return None


def sanitize_instagram_submission(raw,ctx,prepared):
    if not isinstance(raw,Mapping) or raw.get('outcome') not in ('submitted','unknown','failed'):
        return SubmissionResult('unknown',evidence={'reason':'invalid_instagram_result'})
    remote=raw.get('remote_id') if _id(raw.get('remote_id')) else None
    evidence=raw.get('evidence');receipt=sanitize_instagram_upload_receipt(evidence.get('upload_receipt') if isinstance(evidence,Mapping) else None,ctx,prepared,remote)
    safe={'upload_receipt':receipt} if receipt is not None else {}
    outcome=raw['outcome']
    if outcome=='submitted' and remote is None:return SubmissionResult('unknown',evidence=dict(safe,reason='invalid_instagram_result'))
    if outcome=='failed' and (remote is not None or receipt is not None):outcome='unknown'
    if outcome!='submitted':safe['reason']='instagram_submission_uncertain' if outcome=='unknown' else 'instagram_submission_failed'
    if outcome=='failed' and isinstance(evidence,Mapping) and evidence.get('confirmed_not_submitted') is True:safe['confirmed_not_submitted']=True
    return SubmissionResult(outcome,remote_id=remote,url=safe_instagram_url(raw.get('url')),evidence=safe)


class InstagramAdapter:
    platform='instagram'
    def __init__(self,registry,bridge):self.registry,self.bridge=registry,bridge
    def _binding(self,ctx,*,inspection=False):
        if not isinstance(ctx,PublicationContext) and not (inspection and isinstance(ctx,AdmissionReadContext)):
            raise ContractError('publication_context_required')
        conn=self.registry.connections.get(ctx.connection_id);executor=_BINDINGS.get(ctx.connection_id)
        if (not executor or not conn or conn.enabled is not True or ctx.platform!='instagram' or conn.platform!='instagram'
                or conn.account_id!=ctx.destination_account_id or conn.account_id!=ctx.connection_id.split('.')[0]
                or conn.target_id!=ctx.target_id or not _id(ctx.target_id) or ctx.registry_revision!=self.registry.revision
                or ctx.owner_account_id not in ('personal','dept')):raise ContractError('instagram_context_mismatch')
        try:validate_publication_credential_binding(self.registry,conn)
        except ContractError:raise ContractError('instagram_context_mismatch') from None
        return executor
    def inspect_target(self,ctx):return self.bridge.read(self._binding(ctx,inspection=True),'inspect_target',ctx,{})
    def prepare(self,ctx,snapshot):self._binding(ctx);return build_instagram_payload(snapshot,ctx)
    def submit(self,ctx,prepared,permit):
        executor=self._binding(ctx);checked=validate_instagram_prepared(ctx,prepared)
        if self.registry.connections[ctx.connection_id].credential_ref.startswith('oauth:'):
            return SubmissionResult('failed',evidence={'reason':'managed_publication_unverified','confirmed_not_submitted':True})
        try:return sanitize_instagram_submission(self.bridge.submit(executor,ctx,checked,permit),ctx,checked)
        except Exception:return SubmissionResult('unknown',evidence={'reason':'instagram_submission_uncertain'})
    def lookup(self,ctx,attempt):
        executor=self._binding(ctx)
        if not isinstance(attempt,Mapping):return LookupResult('unsupported',evidence={'reason':'attempt_required'})
        prior=attempt.get('result');known=attempt.get('remote_id') or (prior.get('remote_id') if isinstance(prior,Mapping) else None)
        if not _id(known):return LookupResult('unsupported',evidence={'reason':'known_remote_id_required'})
        source=(prior.get('evidence') or {}).get('upload_receipt') if isinstance(prior,Mapping) and isinstance(prior.get('evidence'),Mapping) else None
        if sanitize_instagram_upload_receipt(source,ctx,remote_id=known) is None:
            return LookupResult('unsupported',evidence={'reason':'source_receipt_required'})
        store=getattr(getattr(self.bridge,'store',None),'content_store',None)
        if store is None:return LookupResult('unsupported',evidence={'reason':'approved_snapshot_unavailable'})
        try:
            snapshot=store.get(ctx.content_id,ctx.content_revision);prepared=build_instagram_payload(snapshot,ctx)
            raw=self.bridge.read(executor,'lookup',ctx,{'attempt':{'remote_id':known,'created_at':attempt.get('created_at')}})
            values=raw.get('candidates')
            if not isinstance(values,(list,tuple)):raise ValueError()
            candidates=[sanitize_instagram_observation(value,ctx,known,prepared) for value in values]
            if any(value is None for value in candidates):return LookupResult('unsupported',evidence={'reason':'remote_evidence_incomplete'})
            matched=[value for value in candidates if instagram_upload_identity(ctx,snapshot,value,attempt,raw['checked_at'],known,require_public=False,allow_unknown=True)]
            if len(candidates)==1 and len(matched)==1:return LookupResult('matched',matched)
            return LookupResult('ambiguous' if len(matched)>1 else 'unsupported',candidates,{'reason':'remote_evidence_incomplete' if candidates else 'remote_absence_unproven'})
        except Exception:return LookupResult('error',evidence={'reason':'instagram_lookup_error'})
    def verify(self,ctx,remote_id,snapshot):
        executor=self._binding(ctx);now=datetime.now(timezone.utc)
        try:
            expected=build_instagram_payload(snapshot,ctx)
            if not _id(remote_id):return VerificationResult('failed',now,{'reason':'remote_identity_mismatch'})
            raw=self.bridge.read(executor,'verify',ctx,{'remote_id':remote_id});checked=utc(raw['checked_at']);item=sanitize_instagram_observation(raw.get('observation'),ctx,remote_id,expected)
            if item is None:return VerificationResult('pending',checked,{'reason':'remote_observation_unavailable'})
            if item['body_sha256']!=expected['caption_sha256']:return VerificationResult('failed',checked,dict(item,reason='remote_identity_mismatch'))
            if utc(item['created_at'])>checked or item['upload_receipt'] is None:return VerificationResult('pending',checked,dict(item,reason='source_receipt_required'))
            return VerificationResult('verified' if item['visibility']=='public' else 'pending',checked,item)
        except Exception:return VerificationResult('error',now,{'reason':'instagram_verification_error'})


def build_adapter(registry,bridge):return InstagramAdapter(registry,bridge)

def bridge_bootstrap():
    from .instagram_runtime import bridge_bootstrap as bootstrap
    return bootstrap()

if __name__=='__main__':
    from .bridge_host import main
    raise SystemExit(main(bootstrap=bridge_bootstrap,bootstrap_module=__spec__.name))
