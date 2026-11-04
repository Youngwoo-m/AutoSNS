"""저장 계획의 로컬 영상·캡션 준비. 원격 요청·게시 승인·대기열 변경은 없다."""
from collections.abc import Mapping
from datetime import datetime,timezone
import hashlib
import json
from urllib.parse import quote

from .content_store import StoreError,ConflictError
from .models import ContractError,Registry,thaw
from .runtime_models import utc
from common.publishers.tiktok_payloads import TikTokPreparationContext,build_tiktok_payload


def _hash(value):
    raw=json.dumps(thaw(value),sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


class TikTokPreparationService:
    def __init__(self,content_store,plan_supplier,registry_supplier,*,probe=None,clock=None):
        if (not callable(plan_supplier) or not callable(registry_supplier)
                or probe is not None and not callable(getattr(probe,'inspect',None))
                or clock is not None and not callable(clock)):
            raise ContractError('invalid_tiktok_preparation_service')
        self.contents=content_store;self.plans=plan_supplier;self.registry=registry_supplier
        self.probe=probe;self.clock=clock or (lambda:datetime.now(timezone.utc))

    def _derive(self,plan_id):
        plan=self.plans(plan_id)
        if (not isinstance(plan,Mapping) or plan.get('id')!=plan_id or plan.get('source')!='managed'
                or plan.get('platform')!='tiktok' or plan.get('status')=='cancelled'):
            raise StoreError('not_found')
        registry=self.registry()
        if not isinstance(registry,Registry):raise StoreError('storage_error')
        connection=registry.connections.get(plan.get('connection_id'))
        if (connection is None or connection.platform!='tiktok' or not connection.planning_enabled
                or connection.account_id!=plan.get('destination_account_id')):
            raise StoreError('not_found')
        ctx=TikTokPreparationContext(platform='tiktok',connection_id=connection.id,target_id=connection.target_id,
            owner_account_id=plan.get('owner_account_id'),destination_account_id=connection.account_id,
            content_id=plan.get('content_id'),content_revision=plan.get('revision'),manifest_hash=plan.get('manifest_hash'),
            publication_purpose=plan.get('publication_purpose'),schedule_slot=plan.get('schedule_slot'),options=plan.get('options'))
        snapshot=self.contents.get(ctx.content_id,ctx.content_revision)
        head=self.contents.get(ctx.content_id)
        if any(head.get(key)!=snapshot.get(key) for key in ('revision','manifest_hash','owner_account_id')):
            raise ConflictError()
        prepared=build_tiktok_payload(snapshot,ctx)
        asset=prepared['asset']
        metadata,raw=self.contents.read_asset(ctx.content_id,ctx.content_revision,asset['id'])
        if (not isinstance(metadata,Mapping) or type(raw) is not bytes or len(raw)!=asset['size']
                or any(metadata.get(k)!=asset[k] for k in ('id','sha256','size','media_type'))
                or hashlib.sha256(raw).hexdigest()!=asset['sha256']
                or len(raw)<16 or raw[4:8]!=b'ftyp'
                or not 16<=int.from_bytes(raw[:4],'big')<=len(raw) or int.from_bytes(raw[:4],'big')%4):
            raise StoreError('storage_error')
        identity=dict(plan_id=plan_id,plan_version=plan.get('version'),registry_revision=registry.revision,prepared=prepared)
        return prepared,raw,_hash(identity)

    def _public(self,plan_id,prepared,subject,technical=None):
        asset=dict(prepared['asset'])
        return dict(plan_id=plan_id,**{k:prepared[k] for k in ('owner_account_id','destination_account_id','connection_id',
            'content_id','content_revision','manifest_hash','caption','caption_sha256')},asset=asset,
            asset_url='/api/v2/contents/'+quote(prepared['content_id'],safe='')+'/revisions/'+str(prepared['content_revision'])+'/assets/'+quote(asset['id'],safe=''),
            preparation_hash=subject,status='local_preparation_only',publication_enabled=False,
            technical_check_available=self.probe is not None,technical_check=technical)

    def get(self,plan_id):
        try:prepared,_,subject=self._derive(plan_id)
        except ContractError:raise StoreError('invalid') from None
        return self._public(plan_id,prepared,subject)

    def check(self,plan_id,body):
        if type(body) is not dict or set(body)!={'preparation_hash'}:raise StoreError('invalid')
        try:prepared,raw,subject=self._derive(plan_id)
        except ContractError:raise StoreError('invalid') from None
        if type(body['preparation_hash']) is not str or body['preparation_hash']!=subject:raise ConflictError()
        if self.probe is None:raise StoreError('storage_error')
        try:
            from .tiktok_media_probe import validate_tiktok_video_metadata
            technical=validate_tiktok_video_metadata(self.probe.inspect(raw))
            checked=utc(self.clock()).isoformat()
        except Exception:raise StoreError('storage_error') from None
        # 검사 중 원고·계획·대상이 바뀌면 이전 결과를 새 구성에 붙이지 않는다.
        try:current,_,fresh=self._derive(plan_id)
        except ContractError:raise StoreError('invalid') from None
        if fresh!=subject:raise ConflictError()
        return self._public(plan_id,current,subject,{**technical,'checked_at':checked})
