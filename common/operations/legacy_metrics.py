"""허용된 과거 통계 JSON만 읽고, 계정 추정 없이 별도 성과 원장에 가져온다.

load의 parts는 내부 전용 원본이다. HTTP에는 build_import_plan의 안전한 결과만
노출한다. 수집기·운영 원장·인증 자료는 이 모듈의 의존성이 아니다.
"""
from collections.abc import Mapping
from datetime import datetime, timezone
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit, unquote, parse_qs

from .content_store import StoreError
from .metrics_models import normalize_observation

_PARTS = {
    'blog': '블로그', 'blogger': 'Blogger', 'instagram': 'Instagram',
    'threads': 'Threads', 'x': 'X', 'youtube': 'YouTube', 'smds': '학과 소식',
    'searchconsole': '검색 성과', 'indexing': '색인 현황',
}
_PREFIX = 'common/analytics/snapshots/parts'
_METRICS = frozenset(('views', 'likes', 'comments', 'shares', 'saves', 'followers',
    'posts', 'subscribers', 'total_views', 'clicks', 'impressions', 'ctr', 'position',
    'queries', 'indexed_total', '검사', '색인확인', '미색인'))


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(value).hexdigest()


def _text(value):
    if not isinstance(value, str) or not 0 < len(value) <= 2000:
        return None
    try:
        value.encode('utf-8')
    except UnicodeError:
        return None
    return value


def _stamp(value):
    try:
        if not isinstance(value, str):
            return None
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        return None


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _read(root, kind, limit):
    """각 경로 구성요소를 dir_fd + O_NOFOLLOW로 열어 심볼릭 링크 경쟁을 막는다."""
    descriptors = []
    try:
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(descriptor)
        for component in _PREFIX.split('/'):
            descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            descriptors.append(descriptor)
        fd = os.open(kind + '.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
        descriptors.append(fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            return 'unsafe', None, None, None
        if before.st_size > limit:
            return 'too_large', None, None, None
        chunks, size = [], 0
        while True:
            chunk = os.read(fd, min(65536, limit + 1 - size))
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                return 'too_large', None, None, None
            chunks.append(chunk)
        raw = b''.join(chunks)
        after = os.fstat(fd)
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            return 'changed', None, None, None
        mtime = datetime.fromtimestamp(after.st_mtime, timezone.utc).isoformat()
        return 'ok', raw, _digest(raw), mtime
    except OSError as exc:
        status = 'missing' if exc.errno == errno.ENOENT else 'unsafe' if exc.errno in (errno.ELOOP, errno.ENOTDIR) else 'unreadable'
        return status, None, None, None
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def _sections(kind, data):
    """지원 형식의 행을 원래 section과 함께 순서대로 반환한다."""
    if not isinstance(data, dict):
        raise ValueError('shape')
    output = []
    names = ('items', 'pages', 'per_site') if kind == 'searchconsole' else ('per_site', 'pending') if kind == 'indexing' else ('items',)
    if not any(name in data for name in names) and not (data.get('status') in ('error', 'unsupported') or 'error' in data):
        raise ValueError('shape')
    for name in names:
        values = data.get(name, [])
        if not isinstance(values, list):
            raise ValueError('shape')
        output.extend((name, row) for row in values)
    for name in (('profile',) if kind == 'instagram' else ('channel',) if kind == 'youtube' else ('totals',) if kind == 'searchconsole' else ()):
        if name in data:
            if not isinstance(data[name], dict):
                raise ValueError('shape')
            output.append((name, data[name]))
    if kind == 'indexing' and 'indexed_total' in data:
        output.append(('totals', {'indexed_total': data['indexed_total']}))
    if data.get('status') in ('error', 'unsupported') or 'error' in data:
        output.insert(0, ('report', {'status': 'unsupported' if data.get('status') == 'unsupported' else 'error'}))
    return output


def load_legacy_metrics(source_root, registry, *, max_file_bytes=4 * 1024 * 1024):
    """R의 9개 allowlist 파일만 제한 읽기. registry·W·네트워크에 접근하지 않는다.

    반환 {files:[안전 메타],parts:{kind:원본 객체}}. parts는 내부 전용이며
    반드시 build_import_plan을 거쳐 공개한다. registry 인자는 호출 계약용이다.
    """
    if type(max_file_bytes) is not int or not 1 <= max_file_bytes <= 16 * 1024 * 1024:
        raise StoreError('invalid')
    root = Path(source_root).absolute()
    files, parts = [], {}
    for kind, label in _PARTS.items():
        status, raw, digest, mtime = _read(root, kind, max_file_bytes)
        metadata = dict(path=f'{_PREFIX}/{kind}.json', kind=kind, label=label,
            status=status, digest=digest, file_mtime=mtime, row_count=0,
            missing_rows=0, unsupported=False, note='과거 보고이며 발행 검증 근거가 아닙니다.')
        if raw is not None:
            try:
                data = json.loads(raw, object_pairs_hook=_unique,
                                  parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
                sections = _sections(kind, data)
                metadata['row_count'] = len(sections)
                metadata['missing_rows'] = sum(not isinstance(row, dict) for _, row in sections)
                metadata['unsupported'] = data.get('status') == 'unsupported'
                parts[kind] = data
            except (ValueError, TypeError, UnicodeError, RecursionError):
                metadata['status'] = 'corrupt'
                # JSON이 유효하지만 알려진 section 형태가 틀린 경우를 구별한다.
                try:
                    json.loads(raw)
                    metadata['status'] = 'invalid_shape'
                except (ValueError, TypeError, UnicodeError, RecursionError):
                    pass
        files.append(metadata)
    return dict(files=files, parts=parts)


def _url(value):
    """비밀 query/fragment를 버린 host+path. 임의 host를 플랫폼으로 인정하지 않는다."""
    if not isinstance(value, str) or len(value) > 8000:
        return None
    try:
        value.encode('utf-8')
        p = urlsplit(value)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
            return None
        host = p.hostname.lower().rstrip('.')
        if not re.fullmatch(r'[a-z0-9.-]+', host):
            return None
        return host, unquote(p.path).rstrip('/')
    except (ValueError, UnicodeError):
        return None


def _platform(url):
    if url is None:
        return None
    host = url[0]
    for hosts, platform in ((('instagram.com', 'www.instagram.com'), 'instagram'),
          (('threads.net', 'www.threads.net', 'threads.com', 'www.threads.com'), 'threads'),
          (('x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'), 'x'),
          (('youtube.com', 'www.youtube.com', 'youtu.be'), 'youtube'),
          (('blog.naver.com', 'm.blog.naver.com'), 'naver')):
        if host in hosts:
            return platform
    if host.endswith('.tistory.com'):
        return 'tistory'
    if host.endswith('.blogspot.com'):
        return 'blogger'
    return None


def _canonical(value):
    parsed = _url(value)
    return parsed if parsed else _text(value)


def _youtube_video_id(value):
    """검증한 watch URL의 v 한 개만 사용하며 다른 query 값은 보존하지 않는다."""
    parsed = _url(value)
    if parsed is None or parsed[0] not in ('youtube.com', 'www.youtube.com') or parsed[1] != '/watch':
        return None
    try:
        values = parse_qs(urlsplit(value).query, keep_blank_values=True, max_num_fields=64).get('v', [])
    except ValueError:
        return None
    if len(values) == 1 and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', values[0]):
        return values[0]
    return None


def _source_row_key(kind, section, raw, observation, position):
    """정규화에서 사라지는 허용 차원을 hash하고 불명 행은 원본 위치로 구별한다.

    검색어 원문과 URL query/비밀 필드는 공개 source나 key 입력에 복사하지 않는다.
    강한 식별 차원이 없는 동일 내용 행도 같은 항목이라고 추정하지 않는다.
    """
    row = raw if isinstance(raw, dict) else {}
    dimensions = {}
    if observation['remote_id'] is not None:
        dimensions['remote_id'] = observation['remote_id']
    lossy_page_identity = False
    for field in ('site', 'page', 'url'):
        parsed = _url(row.get(field))
        if parsed is not None:
            dimensions[field] = parsed
            # 검색 페이지의 query를 버렸다면 같은 host/path만으로 중복을 확정하지 않는다.
            if kind == 'searchconsole' and urlsplit(row[field]).query:
                lossy_page_identity = True
    query = _text(row.get('query')) if kind == 'searchconsole' else None
    if query is not None:
        dimensions['query_hash'] = _digest(query.encode('utf-8'))
    if section in ('profile', 'channel', 'totals', 'report'):
        identified = True  # 각 파일에서 한 번만 생성하는 집계 section
    elif kind == 'searchconsole':
        identified = ('remote_id' in dimensions or query is not None or
                      'page' in dimensions or section == 'per_site' and 'site' in dimensions)
    elif kind == 'youtube':
        identified = 'remote_id' in dimensions
    else:
        identified = ('remote_id' in dimensions or
                      any(dimensions.get(field, ('', ''))[1] for field in ('page', 'url')) or
                      section == 'per_site' and 'site' in dimensions)
    if not identified or lossy_page_identity:
        dimensions['source_position'] = position
    return _digest(_json(dict(kind=kind, section=section, dimensions=dimensions)).encode('utf-8'))


def _identity(kind, data, row):
    fixed = kind if kind in ('instagram', 'threads', 'x', 'youtube', 'blogger') else None
    parsed = _url(row.get('url') or row.get('page') or row.get('site'))
    platform = fixed or _platform(parsed)
    targets = set()
    remote = _text(row.get('remote_id')) or _text(row.get('id'))
    if remote is None and kind == 'youtube':
        remote = _youtube_video_id(row.get('url'))
    if parsed:
        host, path = parsed
        pieces = [p for p in path.split('/') if p]
        if platform == 'tistory' or kind in ('searchconsole', 'indexing'):
            targets.add((host, ''))
        elif platform == 'naver' and pieces:
            targets.add(('blog.naver.com', '/' + pieces[0]))
        elif platform == 'blogger':
            targets.add((host, ''))
        elif platform in ('x', 'threads') and pieces:
            targets.update((pieces[0], pieces[0].lstrip('@'), '@' + pieces[0].lstrip('@'), (host, '/' + pieces[0])))
        if remote is None and pieces:
            if platform == 'tistory' and pieces[-1].isdigit():
                remote = pieces[-1]
            elif platform == 'instagram' and len(pieces) >= 2 and pieces[0] in ('p', 'reel'):
                remote = pieces[1]
            elif platform in ('x', 'threads') and len(pieces) >= 3 and pieces[-2] in ('status', 'post'):
                remote = pieces[-1]
            elif platform in ('blogger', 'naver') or kind == 'smds':
                remote = ('https://' + host + path)[:2000]
    # 출처 profile/channel은 소속의 강한 명시 식별자이며 제목은 사용하지 않는다.
    context = data.get('profile') if kind in ('instagram', 'threads') else data.get('account') if kind == 'x' else data.get('channel') if kind == 'youtube' else data.get('blog') if kind == 'blogger' else None
    # 글 URL 자체에 계정 경로/블로그 host가 있으면 컨테이너의 다른 계정으로 덮지 않는다.
    url_identifies_target = bool(parsed and targets and platform in ('x', 'threads', 'blogger', 'naver', 'tistory'))
    if isinstance(context, dict) and not url_identifies_target:
        for field in ('uid', 'username', 'handle'):
            value = _text(context.get(field))
            if value:
                targets.add(value)
                if field in ('username', 'handle'):
                    targets.update((value.lstrip('@'), '@' + value.lstrip('@')))
                    if platform in ('youtube', 'instagram', 'threads', 'x'):
                        host = {'youtube': 'youtube.com', 'instagram': 'instagram.com', 'threads': 'threads.net', 'x': 'x.com'}[platform]
                        targets.add((host, '/' + ('@' + value.lstrip('@') if platform in ('youtube', 'threads') else value.lstrip('@'))))
        if _url(context.get('url')):
            targets.add(_url(context['url']))
    return platform, targets, remote, parsed


def _connections(registry):
    return getattr(registry, 'connections', {}) if registry is not None else {}


def _assign(registry, platform, targets, row, parsed):
    matches = []
    for connection in _connections(registry).values():
        if connection.account_id not in ('personal', 'dept') or not connection.target_id:
            continue
        target = _canonical(connection.target_id)
        explicit = (row.get('connection_id') == connection.id and _canonical(row.get('target_id')) == target)
        if connection.platform != platform and not (platform is None and explicit and parsed is None):
            continue
        if target not in targets and not (explicit and parsed is None):
            continue
        # 원본의 임의 target_id/account_id는 독립 증거가 아니다. 명시 connection도 대조한다.
        if row.get('connection_id') is not None and row['connection_id'] != connection.id:
            continue
        if row.get('target_id') is not None and _canonical(row['target_id']) != target:
            continue
        # 다른 host의 글은 컨테이너 profile의 등록만으로 귀속하지 않는다.
        if parsed and _platform(parsed) != platform and platform in ('instagram', 'threads', 'x', 'youtube', 'blogger', 'naver', 'tistory'):
            continue
        matches.append(connection)
    return matches[0] if len(matches) == 1 else None


def _observation(kind, section, raw_row, data, file, registry):
    malformed = not isinstance(raw_row, dict)
    row = raw_row if not malformed else {}
    platform, targets, remote, parsed = _identity(kind, data, row)
    connection = _assign(registry, platform, targets, row, parsed)
    if connection is not None:
        platform = connection.platform
    uncertainties = ['legacy_unverified', 'owner_unknown']
    if connection is None:
        uncertainties.append('unassigned')
    if remote is None:
        uncertainties.append('remote_id_missing')
    if row.get('status') == 'running' or row.get('state') == 'running':
        uncertainties.append('recovery_pending')
    status = 'error' if malformed or row.get('status') == 'error' or 'error' in row else 'unsupported' if row.get('status') == 'unsupported' else 'legacy_reported'
    values = {key: value for key, value in row.items() if key in _METRICS and type(value) in (int, float) and (type(value) is int or math.isfinite(value))}
    if any(key in row and key not in values for key in _METRICS):
        uncertainties.append('invalid_metric_value')
    if not values:
        uncertainties.append('metric_values_missing')
    observed = _stamp(row.get('observed_at')) or _stamp(data.get('observed_at'))
    if observed is None and kind == 'blog':
        observed = _stamp(data.get('views_at'))
    collected = _stamp(row.get('collected_at')) or _stamp(data.get('collected_at'))
    if observed is None:
        uncertainties.append('observation_time_unknown')
    if collected is None:
        uncertainties.append('collection_time_unknown')
    return normalize_observation(dict(source_kind='legacy_reported',
        owner_account_id=None,
        destination_account_id=connection.account_id if connection else None,
        platform=platform, connection_id=connection.id if connection else None,
        target_id=connection.target_id if connection else None,
        remote_id=remote, delivery_id=None, content_id=None,
        title=(_text(row.get('title')) or _PARTS[kind])[:2000], status=status,
        values={} if status in ('error', 'unsupported') else values,
        observed_at=observed, collected_at=collected, file_mtime=file['file_mtime'],
        definition_id=f'legacy.{kind}.{section}.v1', basis='unknown', period=None,
        source=dict(path=file['path'], kind=kind, label=_PARTS[kind], section=section,
                    note='과거 보고이며 계정·발행 검증을 대신하지 않습니다.'), uncertainties=uncertainties))


def build_import_plan(snapshot, registry):
    """순수 변환: 안전한 preview와 import_rows용 nested 관측을 반환한다."""
    files = snapshot['files']
    observations, warnings, seen = [], [], set()
    errors = 0
    for file in files:
        kind = file['kind']
        if file['status'] != 'ok':
            if file['status'] != 'missing':
                errors += 1
            warnings.append(f"{_PARTS[kind]}: {file['status']}")
            continue
        data = snapshot['parts'][kind]
        positions = {}
        for section, raw in _sections(kind, data):
            position = positions.get(section, 0)
            positions[section] = position + 1
            observation = _observation(kind, section, raw, data, file, registry)
            observation['source']['row_key'] = _source_row_key(kind, section, raw, observation, position)
            row_hash = _digest(_json(observation).encode('utf-8'))
            key = f'legacy:{kind}:{row_hash}'
            if key in seen:
                continue
            seen.add(key)
            observations.append(dict(observation_key=key, observation=observation))
            errors += observation['status'] == 'error' or 'invalid_metric_value' in observation['uncertainties']
    counts = dict(rows=len(observations), unassigned=sum(e['observation']['destination_account_id'] is None for e in observations), errors=errors)
    public = dict(files=files, counts=counts, observations=observations, warnings=warnings)
    # 현재 시각·registry 비밀·절대경로는 digest에도 공개 결과에도 넣지 않는다.
    return dict(preview_digest=_digest(_json(public).encode('utf-8')), **json.loads(_json(public)))


def import_snapshot(store, plan):
    """호출자가 R의 digest를 재검증한 plan을 초기화된 W에 원자적으로 쓴다."""
    return store.import_rows(dict(preview_digest=plan['preview_digest'], observations=plan['observations']))
