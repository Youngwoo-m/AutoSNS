"""실행 HTTP facade. 인증·Host·Origin 검사는 호출하는 웹 서버의 책임이다.

서비스·정책·actor·조회 메타데이터는 서버만 주입한다. 이 모듈은 서비스나
worker를 생성하지 않으며 요청에서 받은 정책으로 실행을 활성화하지 않는다.
"""
from collections.abc import Mapping
from datetime import datetime
import re

from common.operations.content_store import StoreError
from common.operations.runtime_models import ExecutionPolicy


BASE = '/api/v2/execution'
IDENTIFIER = r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}'
RUN_ROUTE = re.compile(BASE + '/runs/(' + IDENTIFIER + ')')
DELIVERY_ROUTE = re.compile(BASE + '/deliveries/(' + IDENTIFIER + ')/(observe|admit|approve)')
TRIGGER_FIELDS = frozenset(('job_id', 'scheduled_at_utc', 'phase', 'source', 'request_kind', 'mode'))
STATES = frozenset(('queued', 'waiting', 'running', 'preparing', 'prepared', 'submitting', 'submitted',
    'verifying', 'verified', 'completed', 'partial', 'failed', 'cancelled', 'unknown', 'needs_auth',
    'needs_review', 'retry_wait', 'blocked_quota', 'blocked', 'unsupported', 'scheduled', 'dry', 'shadow',
    'pending', 'reserved', 'consumed', 'released', 'producing', 'approved', 'draft', 'planned'))
REASONS = frozenset(('execution_disabled', 'execution_service_unavailable', 'adapter_unavailable',
    'producer_unavailable', 'probe_unavailable', 'media_evidence_required', 'insufficient_evidence',
    'identity_mismatch', 'auth_required', 'needs_auth', 'needs_review', 'unsupported', 'quota_exceeded',
    'quota_unavailable', 'quota_unknown', 'quota_limit', 'limit_reached', 'job_disabled',
    'connection_disabled', 'legacy_owner', 'managed_paused', 'global_stop', 'stopped', 'context_changed',
    'cutover_required', 'provider_policy_violation', 'production_policy_unavailable', 'unknown_job',
    'invalid_registry', 'invalid_catalog', 'production_unavailable', 'review_required',
    'independent_review_required', 'content_changed', 'target_unconfirmed', 'not_public',
    'scheduled_future', 'adapter_error', 'invalid_adapter_result'))
ID_FIELDS = ('id', 'run_id', 'delivery_id', 'planned_delivery_id', 'observation_id', 'binding_id',
    'base_job_id', 'execution_job_id', 'job_id', 'content_id', 'registry_revision', 'connection_id')
INT_FIELDS = ('version', 'plan_version', 'content_revision', 'expected_revision')
HASH_FIELDS = ('context_hash', 'manifest_hash')
TIME_FIELDS = ('scheduled_at_utc', 'created_at', 'checked_at', 'completed_at')


class ExecutionBlocked(StoreError):
    status = 409


class ExecutionUnavailable(StoreError):
    status = 503

    def __init__(self):
        super().__init__('execution_service_unavailable')


def recognizes(path):
    return isinstance(path, str) and (path in (BASE + '/requests', BASE + '/status') or
        RUN_ROUTE.fullmatch(path) is not None or DELIVERY_ROUTE.fullmatch(path) is not None)


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(IDENTIFIER, value) is not None


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.isoformat() if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    except (ValueError, OverflowError):
        return None


def _fields(body, fields):
    if not isinstance(body, dict) or set(body) != set(fields):
        raise StoreError('invalid')
    return body


def _version(value):
    if type(value) is not int or value < 0:
        raise StoreError('invalid')


def _request(body):
    _fields(body, ('trigger', 'content_id', 'expected_revision'))
    request = _fields(body['trigger'], TRIGGER_FIELDS)
    if (not _identifier(request['job_id']) or _timestamp(request['scheduled_at_utc']) is None or
        request['source'] != 'console' or request['phase'] not in ('prepare', 'submit', 'verify') or
        request['mode'] not in ('live', 'dry', 'shadow') or
        request['request_kind'] not in ('new_publication', 'resume')):
        raise StoreError('invalid')
    if request['phase'] == 'prepare':
        if (not _identifier(body['content_id']) or type(body['expected_revision']) is not int or
            body['expected_revision'] < 1):
            raise StoreError('invalid')
    elif body['content_id'] is not None or body['expected_revision'] is not None:
        raise StoreError('invalid')
    # 호출자가 보낸 dict를 서비스가 변경해도 HTTP body의 소유권을 공유하지 않는다.
    return dict(request)


def public_result(raw):
    """등록 서비스의 결과도 공개 필드만 복사한다. 자유 오류·context·result는 제외한다."""
    if not isinstance(raw, Mapping):
        raise StoreError('execution_result_invalid')
    result = {}
    for name in ID_FIELDS:
        if _identifier(raw.get(name)):
            result[name] = raw[name]
    for name in INT_FIELDS:
        value = raw.get(name)
        if type(value) is int and value >= 0:
            result[name] = value
    for name in HASH_FIELDS:
        value = raw.get(name)
        if isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value):
            result[name] = value
    for name in ('state', 'execution_state'):
        value = raw.get(name)
        if isinstance(value, str) and value in STATES:
            result[name] = value
    if raw.get('decision') in ('approved', 'rejected'):
        result['decision'] = raw['decision']
    if isinstance(raw.get('reason'), str) and raw['reason'] in REASONS:
        result['reason'] = raw['reason']
    if type(raw.get('remote_uncertain')) is bool:
        result['remote_uncertain'] = raw['remote_uncertain']
    for name in TIME_FIELDS:
        value = _timestamp(raw.get(name))
        if value:
            result[name] = value
    for name in ('runtime',):
        if isinstance(raw.get(name), Mapping):
            result[name] = public_result(raw[name])
    for name in ('deliveries', 'production'):
        if isinstance(raw.get(name), (list, tuple)):
            result[name] = [public_result(row) for row in raw[name][:1000] if isinstance(row, Mapping)]
    return result


def _jobs(raw_jobs, available, enabled, phases):
    jobs = []
    for raw in raw_jobs[:1000] if isinstance(raw_jobs, (list, tuple)) else ():
        if not isinstance(raw, Mapping) or not _identifier(raw.get('id')):
            continue
        row = {'id': raw['id']}
        label = raw.get('label')
        if isinstance(label, str):
            row['label'] = ''.join(c for c in label[:300] if ord(c) >= 32 and ord(c) != 127)
        if type(raw.get('enabled')) is bool:
            row['enabled'] = raw['enabled']
        row['available'] = available and enabled and raw.get('enabled') is True and raw.get('available') is True
        if isinstance(raw.get('reason'), str) and raw['reason'] in REASONS:
            row['reason'] = raw['reason']
        if raw.get('owner_account_id') in ('personal', 'dept'):
            row['owner_account_id'] = raw['owner_account_id']
        if isinstance(raw.get('phases'), (list, tuple)):
            row['phases'] = [phase for phase in phases if phase in raw['phases']]
        if isinstance(raw.get('connection_ids'), (list, tuple)):
            row['connection_ids'] = [value for value in raw['connection_ids'][:100] if _identifier(value)]
        jobs.append(row)
    return jobs


def _status(service, policy, info):
    info = info if isinstance(info, Mapping) else {}
    available = service is not None
    enabled = isinstance(policy, ExecutionPolicy) and policy.enabled
    blockers = []
    if not enabled:
        blockers.append('execution_disabled')
    if not available:
        blockers.append('execution_service_unavailable')
    raw_blockers = info.get('blockers', ())
    for reason in raw_blockers if isinstance(raw_blockers, (list, tuple)) else ():
        if isinstance(reason, str) and reason in REASONS and reason not in blockers:
            blockers.append(reason)
    raw_caps = info.get('capabilities', {})
    raw_caps = raw_caps if isinstance(raw_caps, Mapping) else {}
    capabilities = {name: available and enabled and raw_caps.get(name) is True
                    for name in ('request', 'observe', 'admit', 'approve')}
    return dict(service_available=available, execution_enabled=enabled, blockers=blockers,
                production_jobs=_jobs(info.get('production_jobs'), available, enabled, ('prepare',)),
                publication_jobs=_jobs(info.get('publication_jobs'), available, enabled, ('submit', 'verify')),
                capabilities=capabilities)


def handle_request(method, path, query, body, service, *, policy=None, actor=None, status_info=None):
    """상위 서버가 검증한 요청을 A8 서비스에 위임한다. 미지원 method는 None이다.

    policy 기본값은 disabled이다. actor는 인증된 서버 신원이며 HTTP body에서
    받을 수 없다. GET status는 서버 등록 메타데이터만 읽고 service를 호출하지 않는다.
    """
    if not recognizes(path):
        raise StoreError('not_found')
    if not isinstance(query, Mapping) or query:
        raise StoreError('invalid')
    read_route = path == BASE + '/status' or RUN_ROUTE.fullmatch(path) is not None
    if method != ('GET' if read_route else 'POST'):
        return None
    if method == 'GET':
        if body is not None:
            raise StoreError('invalid')
        if path == BASE + '/status':
            return _status(service, policy, status_info)
        if service is None:
            raise ExecutionUnavailable()
        raw = service.status(RUN_ROUTE.fullmatch(path).group(1))
        if raw is None:
            raise StoreError('not_found')
        return public_result(raw)

    action = None
    if path == BASE + '/requests':
        request = _request(body)
    else:
        delivery_id, action = DELIVERY_ROUTE.fullmatch(path).groups()
        fields = ('expected_version', 'context_hash', 'request_key') if action == 'approve' else (
            ('run_id', 'expected_version', 'observation_id') if action == 'admit' else ('run_id', 'expected_version'))
        _fields(body, fields)
        _version(body['expected_version'])
        if action == 'approve':
            if (not isinstance(body['context_hash'], str) or not re.fullmatch(r'[0-9a-f]{64}', body['context_hash']) or
                not _identifier(body['request_key']) or not _identifier(actor)):
                raise StoreError('invalid')
        elif not _identifier(body['run_id']) or action == 'admit' and not _identifier(body['observation_id']):
            raise StoreError('invalid')
    if service is None:
        raise ExecutionUnavailable()
    if not isinstance(policy, ExecutionPolicy) or not policy.enabled:
        raise ExecutionBlocked('execution_disabled')
    if action is None:
        raw = service.submit(request, 'console', content_id=body['content_id'], expected_revision=body['expected_revision'])
    elif action == 'observe':
        raw = service.observe(delivery_id, body['run_id'], body['expected_version'])
    elif action == 'admit':
        raw = service.admit(delivery_id, body['run_id'], body['expected_version'], body['observation_id'])
    else:
        # 서비스가 request_key별 원본 결과를 보존한다. facade는 키를 생성/교체하지 않는다.
        raw = service.approve(delivery_id, body['expected_version'], body['context_hash'], body['request_key'], actor)
    return public_result(raw)
