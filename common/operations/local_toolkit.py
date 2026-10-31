"""서버 주입 로컬 정책 아래에서만 실행하는 도구. 발행·인증·원고 저장 없음."""
import base64
import re
from urllib.parse import urlsplit, urlunsplit
from .content_store import StoreError, ConflictError
from .tool_cost_policy import ToolkitPolicy, ToolActionContext, LOCAL_COST_EVIDENCE, evaluate_tool_action
from .provider_capabilities import capabilities_snapshot
from .packaging_rules import build_packaging_preview
from .research_context import build_research_preview
from .thumbnail_checks import inspect_thumbnail
from .thumbnail_layout import PRESETS, REGISTERED_FONT, PillowThumbnailRenderer, render_thumbnail
from .metrics_csv import build_csv_preview, import_csv


def _fields(body, names):
    if type(body) is not dict or set(body) != set(names):
        raise StoreError('invalid')


def _id(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}', value):
        raise StoreError('invalid')
    return value


def _account(value, *, all_allowed=False):
    if type(value) is not str or value not in (('all','personal','dept') if all_allowed else ('personal','dept')):
        raise StoreError('invalid')
    return value


def _revision(value):
    if type(value) is not int or value < 1:
        raise StoreError('invalid')


def _safe_rows(rows):
    # CSV 정규화기의 raw provenance와 내부 저장 계획은 공개하지 않는다.
    fields = ('source_kind','owner_account_id','destination_account_id','platform','connection_id',
              'target_id','remote_id','content_id','delivery_id','title','status','values',
              'observed_at','collected_at','definition_id','basis','period','uncertainties')
    return [{key: row[key] for key in fields if key in row} for row in rows]


def validate_registered_font(renderer):
    """임의 callable도 서버 등록 폰트의 exact bytes/hash가 없으면 실행하지 않는다."""
    expected = getattr(renderer, 'font_sha256', None)
    if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}', expected):
        return False
    try:
        PillowThumbnailRenderer(REGISTERED_FONT, font_sha256=expected)._font_bytes()
        return True
    except (OSError, ValueError):
        return False


_DEFAULT_DESTINATION = object()


class LocalToolkitService:
    def __init__(self, *, registry, content_store=None, metrics_store=None, runtime_store=None,
                 policy=ToolkitPolicy(), thumbnail_renderer=None, thumbnail_authorizer=None, clock):
        if type(policy) is not ToolkitPolicy or not callable(clock):
            raise ValueError('invalid_service_configuration')
        self.registry=registry; self.content_store=content_store; self.metrics_store=metrics_store
        self.runtime_store=runtime_store; self.policy=policy; self.thumbnail_renderer=thumbnail_renderer
        self.thumbnail_authorizer=thumbnail_authorizer; self.clock=clock

    def capabilities(self, account_id):
        _account(account_id, all_allowed=True)
        if account_id != 'all':
            return capabilities_snapshot(account_id,self.registry,policy=self.policy)
        result=capabilities_snapshot('all',self.registry,policy=self.policy)
        result['connections']=[c for account in ('personal','dept')
            for c in capabilities_snapshot(account,self.registry,policy=self.policy)['connections']]
        return result

    def _gate(self, action, owner, destination=_DEFAULT_DESTINATION, connection=None, target=None):
        decision=evaluate_tool_action('local.'+action,ToolActionContext(
            owner,owner if destination is _DEFAULT_DESTINATION else destination,connection,target,self.policy,
            'local',LOCAL_COST_EVIDENCE,self.clock()))
        if not decision['allowed']:
            return dict(status='blocked',reason_codes=decision['reason_codes'])
        return None

    def _snapshot(self, body):
        _id(body['content_id']); _revision(body['revision'])
        if self.content_store is None: raise StoreError('storage_error')
        snapshot=self.content_store.get(body['content_id'])
        if snapshot is None: raise StoreError('not_found')
        if snapshot['revision'] != body['revision']: raise ConflictError()
        _account(snapshot['owner_account_id'])
        return snapshot

    def packaging_preview(self, body):
        _fields(body,('content_id','revision','connection_id','keywords'))
        _id(body['connection_id'])
        words=body['keywords']
        if type(words) is not list or len(words)>20 or any(type(w) is not str or not w.strip() or len(w)>50 for w in words) or len(set(words))!=len(words):
            raise StoreError('invalid')
        snapshot=self._snapshot(body)
        connection=self.registry.connections.get(body['connection_id'])
        if connection is None: raise StoreError('invalid')
        blocked=self._gate('packaging.preview',snapshot['owner_account_id'],connection.account_id,connection.id,connection.target_id)
        if blocked: return blocked
        if not any(v['destination_account_id']==connection.account_id and v['platform']==connection.platform for v in snapshot.get('variants',())):
            return dict(status='blocked',reason_codes=['destination_variant_missing'])
        result=build_packaging_preview(snapshot,platform=connection.platform,keywords=tuple(words))
        refs=[]
        for ref in result.get('evidence_refs',[]):
            try:
                parsed=urlsplit(ref['url'])
                if parsed.scheme in ('https','http') and parsed.hostname and not parsed.username and not parsed.password:
                    refs.append(dict(url=urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))))
            except (ValueError, KeyError, TypeError):
                continue
        result['evidence_refs']=refs
        return dict(result,status='completed',content_id=body['content_id'],revision=body['revision'],
            owner_account_id=snapshot['owner_account_id'],destination_account_id=connection.account_id,
            connection_id=connection.id,platform=connection.platform,target_id=connection.target_id,
            connection_confirmed=connection.target_id is not None,
            uncertainties=[] if connection.target_id is not None else ['connection_target_unconfirmed'])

    def research_preview(self, body):
        _fields(body,('account_id',)); account=_account(body['account_id'],all_allowed=True)
        for owner in (('personal','dept') if account=='all' else (account,)):
            blocked=self._gate('research.preview',owner)
            if blocked: return blocked
        if self.metrics_store is None: raise StoreError('storage_error')
        return dict(build_research_preview(account,self.registry,self.metrics_store,self.content_store,
                    runtime_store=self.runtime_store),status='completed')

    def thumbnail_inspect(self, body):
        _fields(body,('content_id','revision','asset_id')); _id(body['asset_id'])
        snapshot=self._snapshot(body)
        blocked=self._gate('thumbnail.inspect',snapshot['owner_account_id'])
        if blocked: return blocked
        metadata,data=self.content_store.read_asset(body['content_id'],body['revision'],body['asset_id'])
        return inspect_thumbnail(data,media_type=metadata.get('media_type'),expected_sha256=metadata.get('sha256'))

    def thumbnail_render(self, body):
        _fields(body,('content_id','revision','asset_id','preset_id','title'))
        if body['asset_id'] is not None: _id(body['asset_id'])
        if type(body['preset_id']) is not str or body['preset_id'] not in PRESETS or type(body['title']) is not str or not body['title'].strip() or len(body['title'])>2000:
            raise StoreError('invalid')
        snapshot=self._snapshot(body)
        blocked=self._gate('thumbnail.render',snapshot['owner_account_id'])
        if blocked: return blocked
        request=dict(preset_id=body['preset_id'],title=body['title'])
        if body['asset_id'] is not None:
            asset=next((a for a in snapshot.get('assets',()) if a['id']==body['asset_id']),None)
            if asset is None: raise StoreError('invalid')
            try:
                authorized=self.thumbnail_authorizer is not None and self.thumbnail_authorizer(snapshot,asset) is True
            except Exception:
                authorized=False
            if not authorized:
                return dict(status='blocked',reason_codes=['asset_reuse_unauthorized'])
            metadata,data=self.content_store.read_asset(body['content_id'],body['revision'],body['asset_id'])
            if metadata.get('sha256') != asset.get('sha256'):
                return dict(status='blocked',reason_codes=['asset_hash_mismatch'])
            request.update(image_bytes=data,image_sha256=asset.get('sha256'))
        if self.thumbnail_renderer is None:
            return dict(status='unavailable',reason_codes=['renderer_unavailable'])
        if not validate_registered_font(self.thumbnail_renderer):
            return dict(status='unavailable',reason_codes=['font_validation_failed'])
        result=render_thumbnail(request,renderer=self.thumbnail_renderer)
        if result['status']!='completed':
            # Runner details/findings may contain arbitrary paths; expose only known codes.
            known={'renderer_unavailable','decoder_unavailable','font_validation_failed','text_overflow','invalid_image','invalid_render_output','invalid_render_dimensions','render_failed'}
            code=result.get('reason_code')
            return dict(status='unavailable' if result['status']=='unavailable' else 'blocked',reason_codes=[code if code in known else 'render_failed'])
        asset=result['asset']
        return dict(status='completed',png_base64=base64.b64encode(asset['data']).decode('ascii'),
                    media_type='image/png',sha256=asset['sha256'],width=asset['width'],height=asset['height'])

    def _csv(self, body, importing=False):
        _fields(body,('account_id','csv_text','preview_digest','request_key') if importing else ('account_id','csv_text'))
        account=_account(body['account_id'])
        if type(body['csv_text']) is not str: raise StoreError('invalid')
        try: data=body['csv_text'].encode('utf-8')
        except UnicodeError as exc: raise StoreError('invalid') from exc
        if len(data)>256*1024: raise StoreError('too_large')
        if importing:
            _id(body['request_key'])
            if type(body['preview_digest']) is not str or not re.fullmatch('[0-9a-f]{64}',body['preview_digest']): raise StoreError('invalid')
        blocked=self._gate('metrics.csv.import' if importing else 'metrics.csv.preview',account)
        if blocked: return blocked
        if importing:
            if self.metrics_store is None: raise StoreError('storage_error')
            result=import_csv(self.metrics_store,data,account_id=account,registry=self.registry,
                              preview_digest=body['preview_digest'],request_key=body['request_key'])
            allowed=('preview_digest','request_key','imported','unchanged','skipped','duplicates','observation_ids','registry_revision')
            return dict({k:result[k] for k in allowed if k in result},status='completed')
        preview=build_csv_preview(data,account_id=account,registry=self.registry)
        return dict(status='completed',preview_digest=preview['preview_digest'],registry_revision=preview['registry_revision'],
                    rows=_safe_rows(preview['rows']),counts=preview['counts'],warnings=preview['warnings'],can_import=preview['can_import'])

    def csv_preview(self, body): return self._csv(body)
    def csv_import(self, body): return self._csv(body,True)

    def schedule_inspect(self, body):
        _fields(body,('delivery_id',)); _id(body['delivery_id'])
        if self.runtime_store is None: raise StoreError('storage_error')
        delivery=self.runtime_store.get_delivery(body['delivery_id'])
        if delivery is None: raise StoreError('not_found')
        context=delivery['context']
        blocked=self._gate('schedule.inspect',context.get('owner_account_id'),context.get('destination_account_id'),context.get('connection_id'),context.get('target_id'))
        reasons=list(blocked['reason_codes']) if blocked else []
        connection=self.registry.connections.get(context.get('connection_id'))
        if connection is None or connection.account_id!=context.get('destination_account_id') or connection.target_id!=context.get('target_id') or connection.platform!=context.get('platform'):
            reasons.append('connection_context_mismatch')
        if context.get('target_id') is None: reasons.append('connection_target_unconfirmed')
        return dict(delivery_id=body['delivery_id'],state=delivery['state'],target_id=context.get('target_id'),
            remote_id=delivery.get('remote_id'),scheduled_at=delivery.get('scheduled_at'),execution_enabled=False,
            reason_codes=list(dict.fromkeys(reasons+['execution_disabled'])))
