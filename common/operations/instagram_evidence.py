"""Instagram 원본 전달 영수증과 실제 원격 관측의 순수 결속 검증.

서버가 저장한 영수증과 불변 콘텐츠가 입력이라는 신뢰 경계다. 전달 원본의 해시를
변환된 원격 파일 해시라고 주장하지 않는다. URL·토큰·개인 전달 주소는 영수증에 없다.
이 함수는 실제 로그인·업로드·공개 접근을 실행하거나 권한을 부여하지 않는다.
"""
from collections.abc import Mapping
import hashlib
import re
from urllib.parse import urlsplit,unquote
from .models import ContractError,thaw
from .runtime_models import PublicationContext,utc
from common.publishers.instagram_payloads import build_instagram_payload

UPLOAD_RECEIPT_KEYS=frozenset(('kind','context_hash','connection_id','target_id','remote_id',
    'owner_account_id','destination_account_id','content_id','content_revision','manifest_hash',
    'caption_sha256','media_format','assets','creation_id','child_creation_ids','published_children'))
_ASSET_KEYS=frozenset(('id','sha256','size','media_type'))
_CANDIDATE_KEYS=frozenset(('remote_id','target_id','destination_account_id','created_at','text',
    'body_sha256','media_sha256','media_format','media_type','media_product_type','media_status','children','visibility','url'))
_ID=re.compile(r'[0-9]{1,64}')

def _id(value):return type(value) is str and _ID.fullmatch(value) is not None

def safe_instagram_url(value):
    """게시물 경로 구문만 확인한다. 실제 공개 접근·게시물 소유권의 증명은 아니다."""
    try:
        if type(value) is not str or not value or len(value)>2000:return None
        value.encode('utf-8')
        if any(c.isspace() or ord(c)<=32 or 127<=ord(c)<=159 for c in value):return None
        decoded=unquote(value,encoding='utf-8',errors='strict')
        if any(ord(c)<32 or 127<=ord(c)<=159 for c in decoded):return None
        parsed=urlsplit(value)
        if (parsed.scheme!='https' or parsed.netloc not in ('instagram.com','www.instagram.com')
                or parsed.username is not None or parsed.password is not None or parsed.port is not None
                or parsed.query or parsed.fragment or re.fullmatch(r'/(?:p|reel)/[A-Za-z0-9_-]+/?',parsed.path) is None):return None
        return value
    except (ValueError,UnicodeError,TypeError):return None

def _sha(value):
    if type(value) is not str:raise ValueError()
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def _children(value,assets):
    if type(value) not in (list,tuple) or len(value)!=len(assets):return False
    ids=[]
    for child,asset in zip(value,assets):
        if (not isinstance(child,Mapping) or set(child)!={'id','media_type'} or not _id(child.get('id'))
                or child.get('media_type')!=('IMAGE' if asset['media_type']=='image/jpeg' else 'VIDEO')):return False
        ids.append(child['id'])
    return len(ids)==len(set(ids))

def _receipt(value,ctx,prepared,remote_id):
    if (not isinstance(value,Mapping) or set(value)!=UPLOAD_RECEIPT_KEYS
            or type(value['content_revision']) is not int or not _id(value['creation_id'])):return False
    expected=dict(kind='instagram_upload_receipt_v1',context_hash=ctx.context_hash,
        connection_id=ctx.connection_id,target_id=ctx.target_id,remote_id=remote_id,
        owner_account_id=ctx.owner_account_id,destination_account_id=ctx.destination_account_id,
        content_id=ctx.content_id,content_revision=ctx.content_revision,manifest_hash=ctx.manifest_hash,
        caption_sha256=prepared['caption_sha256'],media_format=prepared['media_format'])
    if any(value[k]!=v for k,v in expected.items()):return False
    assets=value['assets']
    if type(assets) not in (list,tuple) or len(assets)!=len(prepared['assets']):return False
    if any(not isinstance(a,Mapping) or set(a)!=_ASSET_KEYS or type(a.get('size')) is not int
           or dict(a)!=dict(b) for a,b in zip(assets,prepared['assets'])):return False
    children=value['child_creation_ids'];carousel=prepared['media_format']=='carousel'
    if type(children) not in (list,tuple) or len(children)!=(len(assets) if carousel else 0):return False
    if any(not _id(c) for c in children) or len(set(children))!=len(children) or value['creation_id'] in children:return False
    pin=value['published_children']
    if carousel:return pin is None or _children(pin,assets)
    return type(pin) in (list,tuple) and len(pin)==0

def instagram_upload_identity(context,snapshot,candidate,attempt,now,remote_id,*,require_public=True,allow_unknown=False):
    """소유 원본 결속과 원격 관측을 검증한다. unknown 조회는 별도 명시 옵션만 허용한다."""
    try:
        if type(require_public) is not bool or type(allow_unknown) is not bool:return False
        # bridge의 불변 tuple/mapping과 DB의 JSON list/dict는 같은 계약으로 비교한다.
        if isinstance(candidate,Mapping):candidate=thaw(candidate)
        if isinstance(attempt,Mapping):attempt=thaw(attempt)
        if isinstance(context,Mapping):context=PublicationContext(**dict(context))
        if not isinstance(context,PublicationContext) or context.platform!='instagram' or not _id(remote_id):return False
        if (not isinstance(snapshot,Mapping) or type(snapshot.get('revision')) is not int
                or any(snapshot.get(k)!=getattr(context,v) for k,v in (
                    ('id','content_id'),('revision','content_revision'),('manifest_hash','manifest_hash'),('owner_account_id','owner_account_id')))
                or not isinstance(candidate,Mapping) or not _CANDIDATE_KEYS<=set(candidate)
                or not isinstance(attempt,Mapping) or type(attempt.get('request_started')) not in (bool,int)
                or attempt['request_started']!=1 or attempt.get('context_hash')!=context.context_hash):return False
        result=attempt.get('result');outcome=attempt.get('outcome')
        if not isinstance(result,Mapping) or result.get('outcome')!=outcome:return False
        evidence=result.get('evidence')
        if not isinstance(evidence,Mapping):return False
        source=evidence.get('upload_receipt');prepared=build_instagram_payload(snapshot,context)
        if not _receipt(source,context,prepared,remote_id):return False
        resolution=result.get('resolution');linked=False
        if resolution is not None:
            if (outcome!='unknown' or not isinstance(resolution,Mapping) or resolution.get('kind')!='link_existing'
                    or not isinstance(resolution.get('evidence'),Mapping)):return False
            final=resolution['evidence'].get('upload_receipt')
            if not _receipt(final,context,prepared,remote_id):return False
            if any(final[k]!=source[k] for k in UPLOAD_RECEIPT_KEYS-{'published_children'}):return False
            if source['published_children'] is not None and final['published_children']!=source['published_children']:return False
            source=final;linked=True
        if outcome in ('submitted','scheduled'):
            if result.get('remote_id')!=remote_id:return False
        elif outcome=='unknown':
            if not linked and not (not require_public and allow_unknown):return False
            if result.get('remote_id') not in (None,remote_id):return False
        else:return False
        if 'upload_receipt' in candidate:
            observed_receipt=candidate['upload_receipt']
            if (not _receipt(observed_receipt,context,prepared,remote_id)
                    or any(observed_receipt[k]!=source[k] for k in UPLOAD_RECEIPT_KEYS-{'published_children'})
                    or source['published_children'] is not None and observed_receipt['published_children']!=source['published_children']):
                return False
        if (candidate['remote_id']!=remote_id or candidate['target_id']!=context.target_id
                or candidate['destination_account_id']!=context.destination_account_id
                or candidate['media_format']!=prepared['media_format'] or candidate['media_status']!='readable'
                or candidate['media_sha256'] is not None or safe_instagram_url(candidate['url']) is None
                or candidate['visibility'] not in ('public','unknown','private')
                or require_public and candidate['visibility']!='public'
                or _sha(candidate['text'])!=prepared['caption_sha256'] or candidate['body_sha256']!=_sha(candidate['text'])):return False
        fmt=prepared['media_format']
        if (candidate['media_type']!={'image':'IMAGE','reels':'VIDEO','carousel':'CAROUSEL_ALBUM'}[fmt]
                or candidate['media_product_type']!=('REELS' if fmt=='reels' else 'FEED')):return False
        children=candidate['children']
        if fmt=='carousel':
            if not _children(children,prepared['assets']):return False
            pin=source['published_children']
            if pin is None:
                final=candidate.get('upload_receipt')
                if (not _receipt(final,context,prepared,remote_id) or final['published_children'] is None
                        or any(final[k]!=source[k] for k in UPLOAD_RECEIPT_KEYS-{'published_children'})):return False
                pin=final['published_children']
            if list(pin)!=list(children):return False
        elif type(children) not in (list,tuple) or len(children)!=0:return False
        return utc(attempt['created_at'])<=utc(candidate['created_at'])<=utc(now)
    except (ContractError,ValueError,TypeError,KeyError,UnicodeError,OverflowError):return False
