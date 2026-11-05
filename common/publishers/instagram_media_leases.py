"""고정된 발행 문맥으로만 전달용 임대 URL을 만든다.

write_guard는 현재 실행 허가·최종 검토·STOP을 검증하는 서버 함수다. 저장소 자체는
발행 권한이 아니며 이 모듈은 공급자를 등록하거나 외부 서버를 기동하지 않는다.
fetch guard는 이미 고정된 바이트의 현재 검토/대상 유효성을 확인하며 소비된 발행
permit을 다시 요구하지 않는다. 원격 수신본은 회수할 수 없다.
"""
from collections.abc import Mapping
from datetime import timedelta
import hashlib
import json

from common.operations.models import ContractError,freeze,thaw
from common.operations.runtime_models import PublicationContext,utc
from .instagram_media_sources import _binding,_host,_signature


def _error(code):raise ContractError(code) from None


def _json(value):
    return json.dumps(thaw(value),sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def _request(ctx,prepared,position):
    if type(position) is not int or not 0<=position<len(prepared['assets']):
        _error('instagram_lease_binding_invalid')
    asset=prepared['assets'][position]
    return dict(context_hash=ctx.context_hash,owner_account_id=ctx.owner_account_id,
        destination_account_id=ctx.destination_account_id,connection_id=ctx.connection_id,
        target_id=ctx.target_id,content_id=ctx.content_id,content_revision=ctx.content_revision,
        manifest_hash=ctx.manifest_hash,position=position,asset_id=asset['id'],
        asset_sha256=asset['sha256'],asset_size=asset['size'],media_type=asset['media_type'])


def _matches(ctx,prepared,request):
    if not isinstance(request,Mapping):return False
    try:return _json(request)==_json(_request(ctx,prepared,request.get('position')))
    except Exception:return False


class BoundInstagramMediaStager:
    """신뢰된 서버만 생성한다. ctx/prepared는 실제 실행 snapshot으로 고정한다."""
    def __init__(self,ctx,prepared,store,*,public_host,clock,write_guard=None,ttl=timedelta(hours=1)):
        self._prepared=_binding(ctx,prepared);self._ctx=ctx;self._store=store
        self._host=_host(public_host)
        if (not callable(clock) or write_guard is not None and not callable(write_guard)
                or not isinstance(ttl,timedelta) or not timedelta(minutes=5)<ttl<=timedelta(hours=24)):
            _error('instagram_lease_configuration_invalid')
        self._clock=clock;self._guard=write_guard;self._ttl=ttl

    def __repr__(self):return 'BoundInstagramMediaStager(<private>)'

    def _allowed(self):
        try:
            return self._guard is not None and self._guard(self._ctx,self._prepared) is True
        except Exception:return False

    def __call__(self,request,raw):
        if not _matches(self._ctx,self._prepared,request):_error('instagram_lease_binding_invalid')
        if (type(raw) is not bytes or len(raw)!=request['asset_size']
                or hashlib.sha256(raw).hexdigest()!=request['asset_sha256']
                or not _signature(raw,request['media_type'])):_error('instagram_lease_binding_invalid')
        if not self._allowed():_error('instagram_lease_approval_required')
        now=utc(self._clock())
        if not self._ctx.auth_checked_at<=now<self._ctx.auth_expires_at:
            _error('instagram_lease_approval_required')
        authority=dict(context=self._ctx.to_dict(),prepared=thaw(self._prepared))
        try:
            receipt=self._store.issue(request=thaw(request),raw=raw,expires_at=now+self._ttl,
                now=now,authority=authority)
        except Exception:_error('instagram_lease_storage_error')
        # URL을 반환하기 전 허가가 사라졌으면 저장된 임대도 닫는다.
        if not self._allowed():
            try:self._store.revoke(receipt['lease_id'],now=utc(self._clock()))
            except Exception:pass
            _error('instagram_lease_approval_required')
        try:
            if (receipt['asset_sha256']!=request['asset_sha256']
                    or type(receipt['asset_size']) is not int or receipt['asset_size']!=len(raw)
                    or receipt['media_type']!=request['media_type']):
                _error('instagram_lease_storage_error')
            token=receipt['token']
            if type(token) is not str or len(token)!=64 or any(c not in '0123456789abcdef' for c in token):
                _error('instagram_lease_storage_error')
            return dict(url='https://'+self._host+'/media/v1/'+token,
                asset_sha256=receipt['asset_sha256'],asset_size=receipt['asset_size'],
                expires_at=receipt['expires_at'],receipt_id=receipt['receipt_id'])
        except Exception:_error('instagram_lease_storage_error')


class InstagramLeaseAuthorityGuard:
    """전달 요청마다 현재 대상·원고·최종 검토를 다시 확인한다. 기본은 거부다."""
    def __init__(self,review_guard=None):
        if review_guard is not None and not callable(review_guard):
            _error('instagram_lease_configuration_invalid')
        self._guard=review_guard

    def __repr__(self):return 'InstagramLeaseAuthorityGuard(<private>)'

    def __call__(self,metadata):
        if self._guard is None:return False
        try:
            authority=metadata['authority']
            if not isinstance(authority,Mapping) or set(authority)!={'context','prepared'}:return False
            ctx=PublicationContext(**thaw(authority['context']))
            prepared=_binding(ctx,authority['prepared'])
            if not _matches(ctx,prepared,metadata['request']):return False
            request=metadata['request']
            if metadata['asset_size']!=request['asset_size'] or metadata['media_type']!=request['media_type']:return False
            return self._guard(ctx,freeze(prepared)) is True
        except Exception:return False
