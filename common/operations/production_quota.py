"""관리 텍스트 제작 횟수의 계정별 일일 quota bucket 준비. 명시 startup 전용.

이 metric(managed_text_generations)은 이 관리 저장소가 요청한 텍스트 제작 횟수만 센다.
Claude 구독의 잔여량이나 기존 발행 quota와는 무관하다.

observed_usage=0 의미: 외부 관측값이 아니라 "로컬 일일 창 시작 시점의 기준선 0"이다.
새 bucket은 observed_at=창 시작으로 만들어 RuntimeStore._buckets가 그 창의 모든
held/settled quota_productions·예약을 reserved에 더하게 한다. 따라서 창 중간에 처음
준비해도 이미 쓴 횟수가 빠지지 않는다. 이미 있는 bucket의 사용량·시각은 절대 건드리지
않고(observe_bucket은 reset하므로 호출 금지) 입력 limit이 달라졌을 때 capacity만 바꾼다.

자체 initialize·CLI·worker·모델 호출은 없다. 호출자가 초기화한 RuntimeStore를 넘긴다.
"""
from collections.abc import Mapping
from datetime import datetime
import math
import json

from .content_store import StoreError
from .models import ContractError, Registry
from .production_settings import MAX_DAILY_LIMIT, METRIC
from .quota import bucket_id, quota_window
from .runtime_models import utc
from .runtime_store import RuntimeStore, stamp

ACCOUNTS = ('personal', 'dept')
TIMEZONE = 'Asia/Seoul'
REQUIREMENT_KEYS = {'scope_kind', 'scope_id', 'metric', 'window_kind', 'timezone', 'amount', 'limit'}


def _invalid():
    raise StoreError('invalid_quota_policy')


def _plan(registry, now):
    """DB를 열기 전에 enabled production job마다 (owner, bucket, 창, limit)을 확정한다."""
    jobs = registry.jobs
    if not isinstance(jobs, Mapping) or not isinstance(registry.policies, Mapping):
        _invalid()
    plans = {}
    for job in jobs.values():
        if not isinstance(job, Mapping):
            _invalid()
        if job.get('enabled') is not True:
            continue  # 꺼진 job은 정책이 어떻든 무시한다.
        owner = job.get('owner_account_id')
        outputs = job.get('required_outputs')
        if (job.get('kind') != 'production' or owner not in ACCOUNTS or job.get('subscription_only') is not True
                or not isinstance(outputs, (list, tuple)) or tuple(outputs) != ('text',) or owner in plans):
            _invalid()
        policy = registry.policies.get(job.get('policy_revision'))
        rows = policy.get('quota_requirements') if isinstance(policy, Mapping) else None
        if not isinstance(rows, (list, tuple)) or len(rows) != 1 or not isinstance(rows[0], Mapping):
            _invalid()
        row = rows[0]
        limit, amount = row.get('limit'), row.get('amount')
        if (set(row) != REQUIREMENT_KEYS or row['scope_kind'] != 'owner' or row['scope_id'] != owner
                or row['metric'] != METRIC or row['window_kind'] != 'day' or row['timezone'] != TIMEZONE
                or type(amount) is not int or amount != 1
                or type(limit) is not int or not 1 <= limit <= MAX_DAILY_LIMIT):
            _invalid()
        start, end = quota_window(row, now)
        plans[owner] = dict(owner_account_id=owner, metric=METRIC, bucket_id=bucket_id('owner', owner, METRIC, start, end),
                            start=start, end=end, limit=limit)
    return [plans[owner] for owner in sorted(plans)]


def _number(value):
    return int(value) if isinstance(value, float) and value.is_integer() else value


def _check_existing(row, plan):
    """기존 bucket이 이 창의 것인지 확인한다. 의심스러우면 fail closed."""
    usage = row['observed_usage']
    if type(usage) not in (int, float) or not math.isfinite(usage) or usage < 0:
        raise StoreError('invalid_quota_observation')
    try:
        observed_at, expires_at = utc(row['observed_at']), utc(row['expires_at'])
    except ContractError as exc:
        raise StoreError('invalid_quota_observation') from exc
    if expires_at != plan['end'] or not plan['start'] <= observed_at < plan['end']:
        raise StoreError('invalid_quota_observation')


def _public(plan, bucket):
    used = bucket['observed_usage'] + bucket['reserved']
    return dict(owner_account_id=plan['owner_account_id'], metric=plan['metric'], bucket_id=plan['bucket_id'],
                capacity=_number(bucket['capacity']), observed_usage=_number(bucket['observed_usage']),
                reserved=_number(bucket['reserved']), used=_number(used),
                remaining=_number(max(bucket['capacity'] - used, 0)),
                observed_at=bucket['observed_at'], expires_at=bucket['expires_at'])


def prepare_managed_text_quota(store, registry, now):
    """컴파일된 정책의 계정별 일일 bucket을 한 transaction으로 준비하고 현재 상태를 돌려준다."""
    if not isinstance(store, RuntimeStore) or not isinstance(registry, Registry):
        raise StoreError('invalid')
    if not isinstance(now, datetime):
        raise StoreError('invalid')
    try:
        now = utc(now)
    except ContractError as exc:
        raise StoreError('invalid') from exc
    plans = _plan(registry, now)
    if not plans:
        return []  # DB를 열지 않으므로 어떤 변경도 없다.
    with store._db(True) as c:  # 초기화된 store 필요. 예외 시 전체 rollback.
        try:
            for plan in plans:
                row = c.execute('SELECT * FROM quota_buckets WHERE id=?', (plan['bucket_id'],)).fetchone()
                if row is None:
                    c.execute('INSERT INTO quota_buckets VALUES(?,?,?,?,?)',
                              (plan['bucket_id'], plan['limit'], 0, stamp(plan['start']), stamp(plan['end'])))
                    continue
                _check_existing(row, plan)
                if row['capacity'] != plan['limit']:
                    c.execute('UPDATE quota_buckets SET capacity=? WHERE id=?', (plan['limit'], plan['bucket_id']))
            active_ids = {plan['bucket_id'] for plan in plans}
            for record in c.execute("SELECT requirements FROM quota_productions WHERE state IN ('held','settled') UNION ALL SELECT requirements FROM quota_reservations WHERE state IN ('held','settled')"):
                requirements = json.loads(record[0])
                if not isinstance(requirements, list):raise ValueError('invalid requirements')
                for item in requirements:
                    if not isinstance(item, dict):raise ValueError('invalid requirement')
                    if item['bucket_id'] in active_ids:
                        amount = item['amount']
                        if type(amount) not in (int,float) or not math.isfinite(amount) or amount <= 0:
                            raise ValueError('invalid local count')
            buckets = store._buckets(c)
            return [_public(plan, buckets[plan['bucket_id']]) for plan in plans]
        except (ValueError, KeyError, TypeError) as exc:  # 손상된 JSON·예약 기록 (ContractError 포함)
            raise StoreError('storage_error') from exc
