"""승인 문맥에 결속한 Instagram 공개 미디어 전달의 서버 주입 경계.

기본 공급자와 최종 승인 guard는 없다. 영수증은 신뢰된 서버 공급자의 관측 계약이며
실제 URL 공개 접근·Instagram 수락·권리/최종 검토 완료의 증거를 대신하지 않는다.
InstagramHostedMedia를 직접 생성해도 승인이나 공개 수락이 생기지 않는다. DNS 조회·
파일 공개·실제 업로드는 구현하지 않으며 주소의 DNS 해석/재결속 정책은 공급자 책임이다.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime,timedelta
import hashlib
import ipaddress
import re
import unicodedata
from urllib.parse import urlsplit

from common.operations.content_store import MAX_ASSET_BYTES,MAX_CONTENT_ASSET_BYTES
from common.operations.models import ContractError,freeze,thaw
from common.operations.runtime_models import PublicationContext,utc
from .instagram_payloads import build_instagram_payload,PREPARED_KEYS

_PROOF_KEYS=frozenset(('url','asset_sha256','asset_size','expires_at','receipt_id'))
_ASSET_KEYS=frozenset(('id','sha256','size','media_type'))
_RECEIPT=re.compile(r'[A-Za-z0-9_-]{1,128}')
_LABEL=re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?')


def _error(code):raise ContractError(code) from None


def _host(value):
    if (type(value) is not str or not value or len(value)>253 or value!=value.lower()
            or value.endswith('.') or '.' not in value or any(not _LABEL.fullmatch(label) for label in value.split('.'))
            or value.rsplit('.',1)[-1].isdigit()
            or value.rsplit('.',1)[-1] in ('localhost','local','internal','test','invalid','example','onion')):
        _error('invalid_instagram_media_host')
    try:ipaddress.ip_address(value)
    except ValueError:return value
    _error('invalid_instagram_media_host')


@dataclass(frozen=True,repr=False)
class InstagramHostedMedia:
    context_hash:str
    owner_account_id:str
    destination_account_id:str
    connection_id:str
    target_id:str
    content_id:str
    content_revision:int
    manifest_hash:str
    position:int
    asset_id:str
    asset_sha256:str
    asset_size:int
    media_type:str
    url:str
    expires_at:datetime
    receipt_id:str
    def __repr__(self):return 'InstagramHostedMedia(<private>)'


def _binding(ctx,prepared):
    if not isinstance(ctx,PublicationContext):_error('publication_context_required')
    if not isinstance(prepared,Mapping) or set(prepared)!=set(PREPARED_KEYS):_error('instagram_media_binding_mismatch')
    # 같은 순수 변환기를 다시 거쳐 옵션 형식·자산 순서·캡션 해시·모든 문맥 필드를 확인한다.
    source=dict(id=ctx.content_id,revision=ctx.content_revision,manifest_hash=ctx.manifest_hash,
        owner_account_id=ctx.owner_account_id,original=prepared.get('caption'),variants=[],assets=prepared.get('assets'))
    expected=build_instagram_payload(source,ctx)
    if expected!=thaw(prepared):_error('instagram_media_binding_mismatch')
    return freeze(expected)


def _signature(raw,mime):
    if mime=='image/jpeg':
        return len(raw)>=6 and raw.startswith(b'\xff\xd8\xff') and raw.endswith(b'\xff\xd9')
    if mime=='video/mp4':
        if len(raw)<16 or raw[4:8]!=b'ftyp':return False
        box=int.from_bytes(raw[:4],'big')
        return 16<=box<=len(raw) and box%4==0
    return False


class InstagramMediaSourceFactory:
    def __init__(self,media_loader,*,stager=None,approval_guard=None,allowed_hosts=(),clock):
        if (not callable(media_loader) or not callable(clock) or stager is not None and not callable(stager)
                or approval_guard is not None and not callable(approval_guard)
                or type(allowed_hosts) not in (tuple,list)):_error('invalid_instagram_media_source')
        hosts=tuple(_host(host) for host in allowed_hosts)
        if len(hosts)!=len(set(hosts)):_error('invalid_instagram_media_host')
        self.media_loader=media_loader;self.stager=stager;self.approval_guard=approval_guard
        self.allowed_hosts=hosts;self.clock=clock

    def _approved(self,ctx,prepared):
        try:allowed=self.approval_guard(ctx,prepared)
        except Exception:_error('instagram_media_approval_required')
        if allowed is not True:_error('instagram_media_approval_required')

    def _load(self,ctx,asset):
        try:result=self.media_loader(ctx.content_id,ctx.content_revision,asset['id'])
        except Exception:_error('instagram_media_source_unavailable')
        if not isinstance(result,(tuple,list)) or len(result)!=2:_error('instagram_media_source_invalid')
        metadata,raw=result
        if (not isinstance(metadata,Mapping) or type(raw) is not bytes or not 0<len(raw)<=MAX_ASSET_BYTES
                or set(asset)!=_ASSET_KEYS or any(metadata.get(key)!=asset[key] for key in _ASSET_KEYS)
                or type(metadata.get('size')) is not int or type(asset['size']) is not int
                or asset['size']!=len(raw) or asset['sha256']!=hashlib.sha256(raw).hexdigest()
                or not _signature(raw,asset['media_type'])):
            _error('instagram_media_source_invalid')
        # 최소 파일 서명 검사다. 픽셀·코덱·길이·프로페셔널 계정 규격 수락을 뜻하지 않는다.
        return raw

    def _receipt(self,ctx,asset,position,proof):
        if (not isinstance(proof,Mapping) or set(proof)!=_PROOF_KEYS
                or proof.get('asset_sha256')!=asset['sha256'] or type(proof.get('asset_size')) is not int
                or proof['asset_size']!=asset['size'] or type(proof.get('receipt_id')) is not str
                or _RECEIPT.fullmatch(proof['receipt_id']) is None):_error('instagram_media_receipt_invalid')
        url=proof.get('url')
        if (type(url) is not str or not url or len(url)>2000 or any(ord(c)<=32 or unicodedata.category(c) in ('Cc','Cs') for c in url)
                or re.search(r'%(?:0[0-9a-f]|1[0-9a-f]|7f)',url,re.I) is not None):
            _error('instagram_media_receipt_invalid')
        try:
            parsed=urlsplit(url)
            if (parsed.scheme!='https' or parsed.hostname not in self.allowed_hosts or parsed.netloc!=parsed.hostname
                    or parsed.username is not None or parsed.password is not None or parsed.port is not None
                    or parsed.query or parsed.fragment):_error('instagram_media_receipt_invalid')
            _host(parsed.hostname)
            expires=utc(proof['expires_at']);now=utc(self.clock())
            if not now+timedelta(minutes=5)<expires<=now+timedelta(hours=24):_error('instagram_media_receipt_invalid')
        except Exception:_error('instagram_media_receipt_invalid')
        return InstagramHostedMedia(ctx.context_hash,ctx.owner_account_id,ctx.destination_account_id,
            ctx.connection_id,ctx.target_id,ctx.content_id,ctx.content_revision,ctx.manifest_hash,
            position,asset['id'],asset['sha256'],asset['size'],asset['media_type'],url,expires,proof['receipt_id'])

    def prepare(self,ctx,prepared):
        if self.stager is None or self.approval_guard is None or not self.allowed_hosts:
            _error('instagram_media_source_unconfigured')
        bound=_binding(ctx,prepared);self._approved(ctx,bound)
        # 뒤 자산이 잘못됐을 때 앞 자산까지 공개되는 일을 막기 위해 전체를 먼저 확인한다.
        loaded=[];total=0
        for asset in bound['assets']:
            raw=self._load(ctx,asset);total+=len(raw)
            if total>MAX_CONTENT_ASSET_BYTES:_error('instagram_media_source_invalid')
            loaded.append((asset,raw))
        receipts=[]
        for position,(asset,raw) in enumerate(loaded):
            self._approved(ctx,bound)
            request=freeze(dict(context_hash=ctx.context_hash,owner_account_id=ctx.owner_account_id,
                destination_account_id=ctx.destination_account_id,connection_id=ctx.connection_id,target_id=ctx.target_id,
                content_id=ctx.content_id,content_revision=ctx.content_revision,manifest_hash=ctx.manifest_hash,
                position=position,asset_id=asset['id'],asset_sha256=asset['sha256'],asset_size=asset['size'],media_type=asset['media_type']))
            try:proof=self.stager(request,raw)
            except Exception:_error('instagram_media_staging_failed')
            receipts.append(self._receipt(ctx,asset,position,proof))
        return tuple(receipts)
