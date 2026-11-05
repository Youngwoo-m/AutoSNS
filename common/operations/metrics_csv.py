"""UTF-8 수동 CSV의 순수 미리보기와 영속 receipt 기반 원자 가져오기."""
import csv
import hashlib
import io
import json
import re
import unicodedata
from .content_store import ConflictError, StoreError
from .metrics_models import MetricObservation, _text
from .metrics_normalization import normalize_metric_row

_REQUIRED = ('platform', 'target_id', 'remote_id', 'metric_name', 'value', 'observed_at', 'basis')
_OPTIONAL = ('period_start', 'period_end', 'timezone', 'title')


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def _parse(data):
    if not isinstance(data, bytes): raise StoreError('invalid')
    if len(data) > 256 * 1024: raise StoreError('too_large')
    try:
        text = data.decode('utf-8-sig')
        if '\x00' in text: raise StoreError('invalid')
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        header = next(reader)
        if len(set(header)) != len(header) or not set(_REQUIRED).issubset(header) or set(header) - set(_REQUIRED + _OPTIONAL):
            raise StoreError('invalid')
        rows = []
        for cells in reader:
            if len(rows) >= 1000: raise StoreError('too_large')
            if len(cells) != len(header): raise StoreError('invalid')
            row = dict(zip(header, cells))
            for key, cell in row.items():
                # A negative numeric value has a distinct normalization error.
                if key == 'value' and re.fullmatch(r'-[0-9]+', cell): continue
                stripped = cell
                while stripped and (stripped[0].isspace() or unicodedata.category(stripped[0]).startswith('C')):
                    stripped = stripped[1:]
                if stripped.startswith(('=', '+', '-', '@')): raise StoreError('invalid')
            rows.append(row)
        if not rows: raise StoreError('invalid')
        return rows
    except (UnicodeError, csv.Error, StopIteration, ValueError) as exc:
        raise StoreError('invalid') from exc


def build_csv_preview(csv_bytes: bytes, *, account_id: str, registry) -> dict:
    if account_id not in ('personal', 'dept') or account_id not in registry.accounts:
        raise StoreError('invalid')
    rows = []; entries = []; warnings = []; counts = dict(total=0, legacy_reported=0, error=0, unsupported=0, unassigned=0)
    for raw in _parse(csv_bytes):
        result = normalize_metric_row(raw)
        matches = [c for c in registry.connections.values() if c.platform == raw['platform'] and c.target_id == raw['target_id']]
        if any(c.account_id != account_id for c in matches): raise StoreError('invalid')
        connection = matches[0] if len(matches) == 1 else None
        uncertainty = ['manual_source', 'owner_unassigned']
        if connection is None:
            uncertainty.append('destination_unassigned'); counts['unassigned'] += 1
        status = 'legacy_reported' if result.status == 'ok' else result.status
        observation = MetricObservation('legacy_reported', None, connection.account_id if connection else None,
            raw['platform'], connection.id if connection else None, raw['target_id'], raw['remote_id'], None, None,
            raw.get('title', ''), status, result.values, result.observed_at, None, None, result.definition_id,
            result.basis, result.period, dict(kind='manual_csv', **dict(result.source)), tuple(uncertainty)).to_dict()
        rows.append(observation)
        entries.append(dict(observation_key='manual.csv:' + _hash(observation), observation=observation))
        counts['total'] += 1; counts[status] += 1
        if result.status != 'ok': warnings.append(dict(row=counts['total'], reason=result.source.get('reason')))
    digest = _hash(dict(bytes_sha256=hashlib.sha256(csv_bytes).hexdigest(), observations=entries,
                        account_id=account_id, registry_revision=registry.revision))
    return dict(preview_digest=digest, registry_revision=registry.revision, rows=rows, counts=counts,
                warnings=warnings, can_import=counts['error'] == 0,
                plan=dict(preview_digest=digest, observations=entries))


def import_csv(store, csv_bytes: bytes, *, account_id: str, registry, preview_digest: str, request_key: str) -> dict:
    _text(preview_digest, limit=1000); _text(request_key, limit=1000)
    preview = build_csv_preview(csv_bytes, account_id=account_id, registry=registry)
    if preview['preview_digest'] != preview_digest: raise ConflictError()
    previous = store.get_import_result(preview_digest, request_key)
    if previous is not None: return previous
    if not preview['can_import']: raise StoreError('invalid')
    return store.import_rows(preview['plan'], request_key=request_key)
