"""수동 count 지표의 순수 정규화. 입력은 인증·게시 검증 근거가 아니다."""
from collections.abc import Mapping
import re
from .content_store import StoreError
from .metrics_models import MetricResult, _text, _time

COUNT_METRICS = frozenset(('views', 'likes', 'comments', 'shares', 'saves', 'clicks', 'impressions'))


def normalize_metric_row(row: Mapping) -> MetricResult:
    if not isinstance(row, Mapping):
        raise StoreError('invalid')
    platform = row.get('platform')
    metric = row.get('metric_name')
    try:
        _text(platform); _text(metric)
        if not re.fullmatch(r'[a-z][a-z0-9_]*', platform) or not re.fullmatch(r'[a-z][a-z0-9_]*', metric):
            raise StoreError('invalid')
        _text(row.get('remote_id')); _text(row.get('target_id'))
    except StoreError:
        return MetricResult('error', {}, None, None, None, 'manual.csv.invalid.v1', source={'reason': 'invalid_identity'})
    definition = f'manual.csv.{platform}.{metric}.v1'
    def failure(reason, status='error'):
        return MetricResult(status, {}, None, row['remote_id'], row['target_id'], definition, source={'reason': reason})
    if metric not in COUNT_METRICS:
        return failure('unsupported_definition', 'unsupported')
    value = row.get('value')
    if value is None or value == '':
        return failure('missing_value')
    if type(value) is int:
        number = value
    elif isinstance(value, str) and re.fullmatch(r'-?[0-9]+', value):
        try: number = int(value)
        except ValueError: return failure('invalid_number')
    else:
        return failure('invalid_number')
    if number < 0:
        return failure('negative_value')
    basis = row.get('basis')
    period = None
    if basis not in ('lifetime', 'interval'):
        return failure('invalid_basis')
    if basis == 'interval':
        period = dict(start=row.get('period_start'), end=row.get('period_end'), timezone=row.get('timezone'))
    elif any(row.get(k) for k in ('period_start', 'period_end', 'timezone')):
        return failure('unexpected_period')
    try:
        observed = _time(row.get('observed_at'))
        return MetricResult('ok', {metric: number}, observed, row['remote_id'], row['target_id'], definition, basis, period)
    except StoreError:
        return failure('invalid_period_or_time')
