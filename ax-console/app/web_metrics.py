"""성과 조회와 명시 저장 HTTP 경계. 수집·모델·원고 생성은 실행하지 않는다."""
import hashlib
from pathlib import PurePosixPath
import re

from common.operations.content_store import ConflictError, StoreError
from common.operations.metrics import build_metrics_snapshot

BASE = '/api/v2/metrics'
ROUTES = (BASE, BASE + '/import-preview', BASE + '/import', BASE + '/proposals')


def recognizes(path):
    return path in ROUTES


class _EmptyStore:
    def list_observations(self, account_id='all'): return []
    def list_proposals(self, account_id='all'): return []


def _fields(body, names):
    if not isinstance(body, dict) or set(body) != set(names):
        raise StoreError('invalid')
    return body


def _key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}', value):
        raise StoreError('invalid')


def _public_observation(row):
    # Store models permit provenance JSON; only server-owned provenance fields leave HTTP.
    source = row.get('source') or {}
    safe = {}
    for name in ('kind', 'label', 'note', 'section', 'row_key', 'manifest_hash', 'verified_at', 'collection_key'):
        value = source.get(name)
        if isinstance(value, str) and len(value) <= 2000:
            safe[name] = value
    path = source.get('path')
    if isinstance(path, str) and path.startswith('common/analytics/snapshots/parts/') and '..' not in PurePosixPath(path).parts and '\\' not in path and '?' not in path and '#' not in path:
        safe['path'] = path
    if type(source.get('content_revision')) is int:
        safe['content_revision'] = source['content_revision']
    return dict(row, source=safe)


def _plan(source_root, registry):
    # Raw snapshot.parts stays inside this function and is never serialized.
    from common.operations.legacy_metrics import load_legacy_metrics, build_import_plan
    return build_import_plan(load_legacy_metrics(source_root, registry), registry)


def handle(store, method, path, query, read_body, *, source_root, registry, collection_service=None):
    writable = store is not None and bool(getattr(store, '_initialized', False))
    if path == BASE and method == 'GET':
        if set(query) - {'account'} or any(len(v) != 1 for v in query.values()):
            raise StoreError('invalid')
        account = query.get('account', ['all'])[0]
        result = build_metrics_snapshot(account, registry, store or _EmptyStore(), writable=writable)
        result['observations'] = [_public_observation(row) for row in result['observations']]
        if collection_service is not None:
            result['collection_enabled']=collection_service.enabled is True
            registered={collection_service.registry.connections[key].platform for key in collection_service.collectors
                        if account=='all' or collection_service.registry.connections[key].account_id==account}
            for item in result['support']:
                if item['platform'] in registered:
                    item['implementation_status']='implemented'
                    item['collection_status']='collected' if any(row['platform']==item['platform'] and row['source_kind']=='verified_delivery' and row['status']=='ok' for row in result['observations']) else 'not_collected'
        return result
    if query:
        raise StoreError('invalid')
    if path == BASE + '/import-preview' and method == 'GET':
        plan = _plan(source_root, registry)
        return dict(preview_digest=plan['preview_digest'], files=plan['files'], counts=plan['counts'],
                    observations=[dict(_public_observation(entry['observation']),
                                       id='preview_' + hashlib.sha256(entry['observation_key'].encode()).hexdigest())
                                  for entry in plan['observations']],
                    warnings=plan['warnings'], writable=writable)
    if method == 'POST' and path in (BASE + '/import', BASE + '/proposals'):
        if not writable:
            raise StoreError('storage_error')
        body = read_body()
        if path.endswith('/import'):
            _fields(body, ('preview_digest', 'request_key'))
            _key(body['request_key'])
            if not isinstance(body['preview_digest'], str) or not re.fullmatch('[0-9a-f]{64}', body['preview_digest']):
                raise StoreError('invalid')
            previous = store.get_import_result(body['preview_digest'], body['request_key'])
            if previous is not None:
                return previous
            plan = _plan(source_root, registry)
            if body['preview_digest'] != plan['preview_digest']:
                raise ConflictError()
            return store.import_rows(plan, request_key=body['request_key'])
        _fields(body, ('account_id', 'observation_ids', 'title', 'note', 'request_key'))
        _key(body['request_key'])
        return dict(proposal=store.save_proposal(**body))
    return None
