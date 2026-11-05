"""읽기 전용 전환 증거 분류. 운영 활성화·원격 접근·복원은 하지 않는다.

오프라인 판정은 시험 결과의 선언과 서버 기준선의 일치를 분류한다. 시험 실행의
진위나 실인증을 증명하지 않는다. 실원장과 live 증거를 결속하는 최종 수락 전에는
항상 production_ready=False이며, 이 결과는 발행 permit으로 사용할 수 없다.
"""
from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import re
import subprocess

from .models import Registry, thaw
from .content_store import StoreError

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / 'docs/runbooks/execution-entrypoint-inventory.json'
CROSSPOST_PATH = ROOT / 'ax-console/config/crossposts.json'
CONNECTION_EXECUTORS = {
    'dept.blogger': 'blogger.dept', 'personal.blogger': 'blogger.personal',
    'dept.naver_blog': 'naver.dept', 'personal.naver_blog': 'naver.personal',
    'personal.tistory': 'tistory.personal', 'dept.youtube': 'youtube.dept',
    'personal.youtube': 'youtube.personal',
}
MATRIX_COLUMNS = ('implementation', 'transport_fixture', 'pure_prepare', 'live_auth',
                  'live_publish', 'public_verify', 'content_verify', 'metrics', 'postprocessing')
STATUS_VALUES = frozenset(('passed', 'not_run', 'unsupported', 'failed'))


def _canonical(value):
    return json.dumps(thaw(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _server_baseline():
    """고정 W 경로만 읽는다. evidence가 읽을 파일/명령을 지정하지 못한다."""
    inventory_bytes = INVENTORY_PATH.read_bytes()
    crosspost_bytes = CROSSPOST_PATH.read_bytes()
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, check=True,
                              capture_output=True, text=True, timeout=5).stdout.strip()
    if not re.fullmatch(r'[0-9a-f]{40,64}', revision):
        raise ValueError('revision')
    return dict(inventory=json.loads(inventory_bytes), crossposts=json.loads(crosspost_bytes),
                revision=revision, inventory_hash=hashlib.sha256(inventory_bytes).hexdigest(),
                crosspost_hash=hashlib.sha256(crosspost_bytes).hexdigest())


def _proof_section(value):
    return (isinstance(value, Mapping) and value.get('status') == 'passed'
            and isinstance(value.get('evidence_ref'), str)
            and re.fullmatch(r'[A-Za-z0-9_./:-]{1,200}', value['evidence_ref']) is not None)


def _tests_pass(value):
    return (isinstance(value, (list, tuple)) and bool(value)
            and all(_proof_section(row) and isinstance(row.get('command'), str) and row['command'].strip()
                    and type(row.get('total')) is int and row['total'] > 0
                    and all(type(row.get(key)) is int and row[key] == 0
                            for key in ('failures', 'errors', 'skipped')) for row in value))


def _contains_fixture(value):
    if isinstance(value, Mapping):
        return any(_contains_fixture(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return any(_contains_fixture(item) for item in value)
    return (isinstance(value, str) and re.search(
        r'fixture|placeholder|example\.(?:com|org|net)|\.invalid(?:/|$)|localhost|127\.0\.0\.1|'
        r'(?:^|[/_:\-])(?:test|demo|mock|sample)(?:$|[/_:\-])', value, re.I) is not None)


def _inventory_complete(job_id, inventory):
    if not isinstance(job_id, str) or not isinstance(inventory, Mapping):
        return False
    jobs = inventory.get('jobs')
    summary = jobs.get(job_id) if isinstance(jobs, Mapping) else None
    if (not isinstance(summary, Mapping) or summary.get('managed_eligible') is not True
            or summary.get('inventory_complete') is not True or summary.get('pending_paths') != []):
        return False
    rows = []
    for group in ('entrypoints', 'audit_rows', 'internal_callers'):
        items = inventory.get(group)
        if (not isinstance(items, (list, tuple))
                or any(not isinstance(row, Mapping) or not isinstance(row.get('job_ids'), (list, tuple))
                       or not all(isinstance(item, str) for item in row['job_ids']) for row in items)):
            return False
        rows.extend(row for row in items if job_id in row.get('job_ids', ()))
    entrypoints = [row for row in inventory['entrypoints'] if job_id in row.get('job_ids', ())]
    expected = summary.get('callers')
    if (not entrypoints or not isinstance(expected, (tuple, list)) or not expected
            or not all(isinstance(item, str) for item in expected)
            or set(expected) != {row.get('caller_id') for row in entrypoints}):
        return False
    return all(row.get('managed_eligible') is True and row.get('inventory_complete') is True
               and row.get('legacy_side_effects', False) is False for row in rows)


def _offline_evidence(evidence, *, registry, inventory, baseline):
    blockers = []
    if not isinstance(evidence, Mapping):
        evidence = {}
        blockers.append('offline:invalid_evidence')
    if evidence.get('code_revision') != baseline['revision']:
        blockers.append('offline:code_revision_mismatch')
    if not _tests_pass(evidence.get('test_results')):
        blockers.append('offline:test_results_incomplete')
    for field, expected in (('entrypoint_inventory_hash', baseline['inventory_hash']),
                            ('crosspost_baseline_hash', baseline['crosspost_hash'])):
        if evidence.get(field) != expected:
            blockers.append('offline:' + field + '_mismatch')
    if (not isinstance(inventory, Mapping) or _canonical(inventory) != _canonical(baseline['inventory'])):
        blockers.append('offline:server_inventory_mismatch')
    if (not isinstance(registry, Registry)
            or _canonical(list(thaw(registry.crossposts).values())) != _canonical(baseline['crossposts']['rules'])):
        blockers.append('offline:crosspost_baseline_changed')
    matrix = evidence.get('connection_matrix')
    if (not isinstance(matrix, Mapping) or set(matrix) != set(CONNECTION_EXECUTORS)
            or not all(isinstance(row, Mapping) and all(row.get(column) in STATUS_VALUES for column in MATRIX_COLUMNS)
                       and all(row.get(column) == 'passed' for column in MATRIX_COLUMNS[:3])
                       for row in matrix.values())):
        blockers.append('offline:connection_matrix_incomplete')
    for field in ('producer_policy_evidence', 'adapter_transport_evidence'):
        if not _proof_section(evidence.get(field)):
            blockers.append('offline:' + field + '_incomplete')
    rollback = evidence.get('rollback_evidence')
    if (not isinstance(rollback, Mapping) or rollback.get('strategy') != 'forward_preserving_ledger'
            or any(rollback.get(key) is not True for key in ('preserve_remote_ids', 'preserve_unknown', 'preserve_quota'))
            or rollback.get('resume_legacy') is not False):
        blockers.append('offline:unsafe_rollback')
    return blockers


def assess_cutover(store, job_id: str, evidence: Mapping, *, registry, inventory) -> dict:
    """신뢰된 서버가 주입한 Registry/inventory/store만 읽어 blocker를 반환한다.

    evidence의 trusted/ready/owner/legacy 플래그를 권한으로 쓰지 않는다. live 확인과
    백업 복구 수락은 후속 운영 checkpoint이며 여기서는 실행하거나 인정하지 않는다.
    """
    refs = {}
    try:
        baseline = _server_baseline()
        blockers = _offline_evidence(evidence, registry=registry, inventory=inventory, baseline=baseline)
        refs.update(code_revision=baseline['revision'], entrypoint_inventory_hash=baseline['inventory_hash'],
                    crosspost_baseline_hash=baseline['crosspost_hash'])
    except (OSError, ValueError, TypeError, subprocess.SubprocessError):
        blockers = ['offline:server_baseline_unavailable']
    proof = evidence if isinstance(evidence, Mapping) else {}
    job = registry.jobs.get(job_id) if isinstance(registry, Registry) and isinstance(job_id, str) else None
    if job is None:
        blockers.append('production:unknown_job')
    elif job.get('execution_owner') != 'managed':
        blockers.append('production:legacy_execution_owner')
    if not _inventory_complete(job_id, inventory):
        blockers.append('production:entrypoint_inventory_incomplete')
    for field in ('live_auth_evidence', 'live_publish_evidence'):
        if not proof.get(field):
            blockers.append('production:' + field + '_missing')
        elif _contains_fixture(proof[field]):
            blockers.append('production:fixture_live_evidence')
    # 실증거를 단순 JSON 선언으로 승격하지 않는 명시적인 사전구간 차단.
    blockers.append('production:live_ledger_verification_pending')
    rollback = proof.get('rollback_evidence')
    if not isinstance(rollback, Mapping) or rollback.get('restore_test') != 'passed':
        blockers.append('production:backup_restore_acceptance_pending')
    if store is None:
        blockers.append('production:runtime_store_unavailable')
    elif not isinstance(registry, Registry) or store.registry is not registry:
        blockers.append('production:runtime_registry_mismatch')
    else:
        try:
            operations = store.list_operations()
            buckets = store.quota_buckets()
            refs['ledger_snapshot_hash'] = _hash(dict(operations=operations, quota_buckets=buckets))
            if any(row.get('state') == 'unknown' or row.get('remote_uncertain') for row in operations):
                blockers.append('production:unresolved_remote_unknown')
        except (StoreError, OSError, ValueError, TypeError):
            blockers.append('production:runtime_store_unavailable')
    blockers = list(dict.fromkeys(blockers))
    return dict(offline_ready=not any(item.startswith('offline:') for item in blockers),
                production_ready=False, blockers=blockers, evidence_refs=refs)
