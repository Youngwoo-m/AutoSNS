"""외부 수집을 수행하지 않는 불변 성과 결과·관측 계약."""
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
import json
import math
from types import MappingProxyType
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .content_store import StoreError
from .models import thaw


def _invalid():
    raise StoreError('invalid')


def _text(value, *, nullable=False, empty=False, limit=2000):
    if nullable and value is None:
        return value
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        _invalid()
    try:
        value.encode('utf-8')
    except UnicodeError:
        _invalid()
    return value


def _time(value, *, nullable=False):
    if nullable and value is None:
        return None
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            _invalid()
        return value.astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError) as exc:
        raise StoreError('invalid') from exc


def _freeze(value):
    if isinstance(value, Mapping):
        if not all(isinstance(k, str) for k in value):
            _invalid()
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(v) for v in value)
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    _invalid()


def _metric_fields(obj):
    if not isinstance(obj.values, Mapping) or not isinstance(obj.source, Mapping):
        _invalid()
    for key, value in obj.values.items():
        _text(key)
        if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
            _invalid()
    if obj.basis not in ('lifetime', 'interval', 'unknown'):
        _invalid()
    _text(obj.definition_id)
    observed = _time(obj.observed_at, nullable=True)
    period = obj.period
    if obj.basis == 'interval':
        if not isinstance(period, Mapping) or set(period) != {'start', 'end', 'timezone'}:
            _invalid()
        _text(period['timezone'])
        try:
            ZoneInfo(period['timezone'])
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise StoreError('invalid') from exc
        period = {'start': _time(period['start']), 'end': _time(period['end']), 'timezone': period['timezone']}
        if datetime.fromisoformat(period['start']) >= datetime.fromisoformat(period['end']):
            _invalid()
    elif period is not None:
        _invalid()
    object.__setattr__(obj, 'observed_at', observed)
    object.__setattr__(obj, 'period', _freeze(period))
    object.__setattr__(obj, 'values', _freeze({} if obj.status in ('error', 'unsupported') else obj.values))
    object.__setattr__(obj, 'source', _freeze(obj.source))
    try:
        if len(json.dumps(obj.to_dict(), ensure_ascii=False, allow_nan=False).encode('utf-8')) > 1024 * 1024:
            raise StoreError('too_large')
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise StoreError('invalid') from exc


class _Model:
    def to_dict(self):
        return {f.name: thaw(getattr(self, f.name)) for f in fields(self)}


@dataclass(frozen=True)
class MetricResult(_Model):
    status: str
    values: Mapping
    observed_at: str | None
    remote_id: str | None
    target_id: str | None
    definition_id: str
    basis: str = 'unknown'
    period: Mapping | None = None
    source: Mapping = field(default_factory=dict)
    # 서버 수집 경계가 발급한다. 값/관측시각과 독립인 시도 ID와 완료시각.
    collection_id: str | None = None
    collected_at: str | None = None

    def __post_init__(self):
        if (self.collection_id is None) != (self.collected_at is None):
            _invalid()
        _text(self.collection_id, nullable=True, limit=1000)
        object.__setattr__(self, 'collected_at', _time(self.collected_at, nullable=True))
        if self.status not in ('ok', 'unsupported', 'error'):
            _invalid()
        for name in ('remote_id', 'target_id'):
            _text(getattr(self, name), nullable=self.status != 'ok')
        if self.status == 'ok' and self.observed_at is None:
            _invalid()
        _metric_fields(self)


@dataclass(frozen=True)
class MetricObservation(_Model):
    source_kind: str
    owner_account_id: str | None
    destination_account_id: str | None
    platform: str | None
    connection_id: str | None
    target_id: str | None
    remote_id: str | None
    delivery_id: str | None
    content_id: str | None
    title: str
    status: str
    values: Mapping
    observed_at: str | None
    collected_at: str | None
    file_mtime: str | None
    definition_id: str
    basis: str = 'unknown'
    period: Mapping | None = None
    source: Mapping = field(default_factory=dict)
    uncertainties: tuple = ()

    def __post_init__(self):
        if self.source_kind not in ('verified_delivery', 'legacy_reported'):
            _invalid()
        if self.status not in ('ok', 'unsupported', 'error', 'legacy_reported'):
            _invalid()
        if self.source_kind == 'verified_delivery' and self.status == 'legacy_reported':
            _invalid()
        if self.source_kind == 'legacy_reported' and self.status == 'ok':
            _invalid()
        if self.source_kind == 'verified_delivery' and self.status == 'ok' and self.observed_at is None:
            _invalid()
        identities = ('owner_account_id', 'destination_account_id', 'platform', 'connection_id',
                      'target_id', 'remote_id', 'delivery_id', 'content_id')
        for name in identities:
            _text(getattr(self, name), nullable=self.source_kind == 'legacy_reported')
        for name in ('owner_account_id', 'destination_account_id'):
            if getattr(self, name) not in (None, 'personal', 'dept'):
                _invalid()
        _text(self.title, empty=True, limit=2000)
        if not isinstance(self.uncertainties, (tuple, list)):
            _invalid()
        for item in self.uncertainties:
            _text(item)
        if self.source_kind == 'legacy_reported' and any(getattr(self, n) is None for n in identities) and not self.uncertainties:
            _invalid()
        object.__setattr__(self, 'uncertainties', tuple(self.uncertainties))
        object.__setattr__(self, 'collected_at', _time(self.collected_at, nullable=self.source_kind == 'legacy_reported'))
        object.__setattr__(self, 'file_mtime', _time(self.file_mtime, nullable=True))
        _metric_fields(self)


Observation = MetricObservation


def normalize_observation(value):
    if isinstance(value, MetricObservation):
        return value.to_dict()
    if not isinstance(value, Mapping):
        _invalid()
    try:
        return MetricObservation(**value).to_dict()
    except (TypeError, ValueError, RecursionError) as exc:
        raise StoreError('invalid') from exc
