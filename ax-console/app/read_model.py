"""운영 파일을 수정하지 않는 제한된 조회 모델.

외부 실행기, 인증 저장소, 기존 서버를 import하지 않는다. 로컬 완료 기록은
게시 보고일 뿐이며 이 모듈은 공개·내용 검증 완료 상태를 만들지 않는다.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
from itertools import islice
import json
from pathlib import Path
import plistlib
import re
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')
MAX_BYTES = 2 * 1024 * 1024
MAX_TAIL_BYTES = 256 * 1024
MAX_SCAN = 4000
MAX_FILES = 200
MAX_ROWS = 200
MAX_JSONL_ROWS = 100
ACCOUNTS = {'dept': '학과', 'personal': '개인'}
LABELS = {'youtube': '유튜브', 'tiktok': '틱톡', 'instagram': '인스타그램',
          'naver_blog': '네이버 블로그', 'tistory': '티스토리', 'blogger': '블로거',
          'threads': '스레드', 'x': 'X', 'facebook': '페이스북', 'homepage': '홈페이지', 'kakao': '카카오'}
CHANNEL_ALIASES = {'naver': 'naver_blog', 'yt': 'youtube', 'insta': 'instagram'}
CONTENT_STATUSES = {'idea', 'drafting', 'review', 'scheduled', 'reported_published', 'failed', 'unknown'}
DELIVERY_STATUSES = {'draft', 'queued', 'scheduled_recorded', 'reported_published', 'failed', 'unknown', 'paused'}


def _text(value, limit=300):
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return None
    value = str(value).strip()
    # Display prose only: paths and common credential forms are never useful here.
    value = re.sub(r'(?<![:\w])(?:/(?:Users|Volumes|private|tmp|home|var)/|~/)[^\s<>"\']+', '[경로 숨김]', value)
    value = re.sub(r'\b(?:sk-[\w-]{12,}|gh[pousr]_[\w]{12,}|Bearer\s+[\w.\-]+)', '[비밀값 숨김]', value, flags=re.I)
    return value[:limit] or None


def _account(value):
    return value if isinstance(value, str) and value in ACCOUNTS else None


def _channel(value):
    if not isinstance(value, str):
        return None
    value = CHANNEL_ALIASES.get(value, value)
    return value if re.fullmatch(r'[a-z][a-z0-9_\-]{0,39}', value) else None


def _time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST).isoformat(timespec='seconds')
    except (ValueError, OverflowError):
        return None


def _url(value):
    if not isinstance(value, str) or any(ord(c) < 32 for c in value) or '\\' in value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
            return None
        parsed.port  # reject malformed ports
        if any(re.search(r'token|secret|password|api.?key|authorization|credential|signature|^code$', key, re.I)
               for key, _ in parse_qsl(parsed.query, keep_blank_values=True)):
            return None
        return value if len(value) <= 2000 else None
    except ValueError:
        return None


def _status(value, *, content=False):
    if not isinstance(value, str):
        return 'unknown'
    aliases = {'done': 'reported_published', 'published': 'reported_published',
               'posted': 'reported_published', 'success': 'reported_published',
               'error': 'failed', 'scheduled': 'scheduled' if content else 'queued',
               'pending': 'unknown' if content else 'queued', 'waiting': 'unknown' if content else 'queued',
               'stopped': 'unknown' if content else 'paused'}
    result = aliases.get(value, value)
    return result if result in (CONTENT_STATUSES if content else DELIVERY_STATUSES) else 'unknown'


def _id(prefix, *parts):
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str).encode()
    return prefix + '_' + hashlib.sha256(raw).hexdigest()[:20]


def _integration_catalog(local_platforms):
    """연동 후보 목록이다. 설치·인증·실행 상태를 검사하거나 추정하지 않는다."""
    candidates = [
        ('metricool', 'Metricool', 'external_plugin', ('instagram', 'threads', 'x', 'facebook'),
         '외부 채널 관리 연동 후보. 계정 연결과 웹 실행 권한을 별도로 확인해야 합니다.'),
        ('vidiq', 'vidIQ', 'external_plugin', ('youtube', 'tiktok', 'instagram'),
         '콘텐츠 분석·기획 보조 연동 후보. 발행 연결과 별개입니다.')]
    if local_platforms:
        candidates.append(('local_publishers', '기존 발행기', 'local_adapter', sorted(local_platforms),
                           '자동 작업 설정에 선언된 채널 목록입니다. 실제 연결·실행 가능 여부는 별도 확인이 필요합니다.'))
    return [{'id': key, 'label': label, 'kind': kind,
             'platforms': [{'id': platform, 'label': LABELS.get(platform, platform)} for platform in platforms],
             'availability': 'unknown', 'connection_status': 'unknown', 'execution_status': 'not_connected',
             'description': description}
            for key, label, kind, platforms, description in candidates]


class _Reader:
    def __init__(self, root, now):
        self.root = root.resolve()
        self.now = now
        self.warnings = []

    def warn(self, message):
        if message not in self.warnings:
            self.warnings.append(message)

    def allowed(self, path, *, external=False):
        try:
            if path.resolve() != path.absolute():
                self.warn('조회 자료: 심볼릭 링크는 읽지 않았습니다.')
                return False
            # Explicit LaunchAgents directories are the sole additional read scope.
            return external or path.resolve().is_relative_to(self.root)
        except (OSError, RuntimeError):
            return False

    def read(self, path, label, expected, *, external=False):
        if not self.allowed(path, external=external):
            self.warn(f'{label}: 원본 범위 밖 링크는 읽지 않았습니다.')
            return None
        try:
            with path.open('rb') as stream:
                data = stream.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                self.warn(f'{label}: 파일 크기 제한으로 조회하지 못했습니다.')
                return None
            value = plistlib.loads(data) if path.suffix == '.plist' else json.loads(data)
            if not isinstance(value, expected):
                self.warn(f'{label}: 자료 구조가 올바르지 않습니다.')
                return None
            return value
        except FileNotFoundError:
            self.warn(f'{label}: 자료가 없습니다.')
        except (OSError, ValueError, TypeError, OverflowError, RecursionError, plistlib.InvalidFileException):
            self.warn(f'{label}: 자료가 손상되었거나 읽을 수 없습니다.')
        return None

    def files(self, base, pattern, label, *, limit=MAX_FILES, external=False):
        if not base.exists() or not self.allowed(base, external=external):
            self.warn(f'{label}: 자료가 없습니다.')
            return []
        try:
            candidates = list(islice(base.glob(pattern), MAX_SCAN + 1))
            if len(candidates) > MAX_SCAN:
                self.warn(f'{label}: 탐색 제한 범위의 최근 자료만 표시합니다.')
                candidates = candidates[:MAX_SCAN]
            scored = []
            for path in candidates:
                if 'archive' in path.relative_to(base).parts or not self.allowed(path, external=external):
                    continue
                try:
                    if path.is_file():
                        scored.append((path.stat().st_mtime_ns, str(path), path))
                except OSError:
                    self.warn(f'{label}: 일부 자료를 읽을 수 없습니다.')
            if len(scored) > limit:
                self.warn(f'{label}: 최근 파일 수 제한으로 일부 자료만 표시합니다.')
            result = [p for _, _, p in sorted(scored, reverse=True)[:limit]]
            if not result:
                self.warn(f'{label}: 자료가 없습니다.')
            return result
        except OSError:
            self.warn(f'{label}: 자료 목록을 읽을 수 없습니다.')
            return []

    def key(self, path):
        return str(path.relative_to(self.root))

    def rows(self, values, label):
        valid = [x for x in values if isinstance(x, dict)]
        if len(valid) != len(values):
            self.warn(f'{label}: 올바르지 않은 항목은 제외했습니다.')
        # Timestamps are normalized before ordering; hashes make ties stable on queue reorder.
        def rank(row):
            stamp = next((_time(row.get(k)) for k in ('updated', 'updated_at', 'added', 'created', 'at', 'schedule')
                          if _time(row.get(k))), '')
            return stamp, _id('row', row)
        if len(valid) > MAX_ROWS:
            self.warn(f'{label}: 최근 항목 수 제한으로 일부 자료만 표시합니다.')
        return sorted(valid, key=rank, reverse=True)[:MAX_ROWS]

    def jsonl(self, path):
        label = '개인 작업 JSONL'
        if not self.allowed(path):
            self.warn(f'{label}: 원본 범위 밖 링크는 읽지 않았습니다.')
            return []
        try:
            with path.open('rb') as stream:
                stream.seek(0, 2)
                size = stream.tell()
                start = max(0, size - MAX_TAIL_BYTES)
                stream.seek(start)
                if start:
                    stream.readline()  # the leading fragment has no complete record
                    self.warn(f'{label}: 최근 바이트 제한으로 일부 자료만 표시합니다.')
                offset = stream.tell()
                data = stream.read(MAX_TAIL_BYTES)
            lines = data.splitlines(keepends=True)
            if len(lines) > MAX_JSONL_ROWS:
                discarded = lines[:-MAX_JSONL_ROWS]
                offset += sum(map(len, discarded))
                lines = lines[-MAX_JSONL_ROWS:]
                self.warn(f'{label}: 최근 줄 수 제한으로 일부 자료만 표시합니다.')
            result = []
            for line in lines:
                position = offset
                offset += len(line)
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError('shape')
                    result.append((position, row))
                except (ValueError, TypeError, RecursionError):
                    self.warn(f'{label}: 손상된 줄을 제외했습니다.')
            return result
        except OSError:
            self.warn(f'{label}: 자료를 읽을 수 없습니다.')
            return []


def _content(cid, row, owner, *, kind=None):
    category = kind or row.get('kind')
    return {'id': cid, 'title': _text(row.get('title') or row.get('topic')) or '제목 미기록',
            'owner_account_id': owner, 'kind': category if category in ('article', 'card', 'short', 'video') else 'unknown',
            'series': _text(row.get('series')), 'status': _status(row.get('status'), content=True),
            'revision': _text(row.get('revision')) if isinstance(row.get('revision'), str) else row.get('revision') if isinstance(row.get('revision'), int) and not isinstance(row.get('revision'), bool) else None,
            'summary': _text(row.get('summary'), 500), 'created_at': _time(row.get('created_at') or row.get('created') or row.get('at')),
            'updated_at': _time(row.get('updated_at') or row.get('updated') or row.get('at')), 'channels': []}


def _delivery(did, content, destination, channel, status, *, when=None, kind='unknown', url=None, evidence):
    return {'id': did, 'content_id': content['id'], 'owner_account_id': content['owner_account_id'],
            'destination_account_id': destination, 'channel': channel,
            'target_label': f"{ACCOUNTS.get(destination, '계정 미확인')} · {LABELS.get(channel, channel or '채널 미확인')}",
            'status': status, 'schedule_kind': kind, 'scheduled_at': _time(when), 'url': _url(url),
            'checked_at': None, 'evidence': evidence}


def _next_calendar(intervals, now):
    """Calendar metadata only; no launchctl state or exact interval-time guesses."""
    if isinstance(intervals, dict):
        intervals = [intervals]
    if not isinstance(intervals, list):
        return None
    candidates = []
    for iv in intervals[:100]:
        if not isinstance(iv, dict) or any(k not in ('Month', 'Day', 'Weekday', 'Hour', 'Minute') for k in iv):
            continue
        if any(not isinstance(v, int) or isinstance(v, bool) for v in iv.values()):
            continue
        found = False
        for day_offset in range(367):
            day = (now + timedelta(days=day_offset)).date()
            if 'Month' in iv and day.month != iv['Month']:
                continue
            if 'Day' in iv and day.day != iv['Day']:
                continue
            if 'Weekday' in iv and day.isoweekday() % 7 != iv['Weekday'] % 7:
                continue
            hours = [iv['Hour']] if 'Hour' in iv else range(24)
            minutes = [iv['Minute']] if 'Minute' in iv else range(60)
            for hour in hours:
                for minute in minutes:
                    try:
                        when = datetime(day.year, day.month, day.day, hour, minute, tzinfo=KST)
                    except ValueError:
                        continue
                    if when > now:
                        candidates.append(when)
                        found = True
                        break
                if found:
                    break
            if found:
                break
    return min(candidates).isoformat(timespec='seconds') if candidates else None


def build_snapshot(source_root: Path, account: str = 'all', *, now: datetime | None = None,
                   launchagents_dir: Path | None = None) -> dict:
    """Return allowlisted metadata from explicit local roots, without writing files.

    Missing timestamps/owners/enablement remain null. LaunchAgents metadata is only
    read when its directory is supplied explicitly; no implicit home lookup occurs.
    """
    if account not in ('all', 'dept', 'personal'):
        raise ValueError('올바르지 않은 계정 범위입니다.')
    now = now or datetime.now(KST)
    now = now.replace(tzinfo=KST) if now.tzinfo is None else now.astimezone(KST)
    reader = _Reader(Path(source_root), now)
    root = reader.root
    data = root / 'ax-console/data'
    snapshot = {'schema_version': 1, 'read_only': True, 'generated_at': now.isoformat(timespec='seconds'),
                'scope': account, 'warnings': reader.warnings,
                'accounts': [{'id': k, 'label': v} for k, v in ACCOUNTS.items()],
                'contents': [], 'deliveries': [], 'channels': [], 'schedule': [], 'incidents': [],
                'crossposts': [], 'proposals': [], 'metrics': {'status': 'unavailable', 'items': []}}
    contents, deliveries = snapshot['contents'], snapshot['deliveries']
    reader.warn('성과는 아직 수집하지 않아 표시할 수 없습니다.')
    reader.warn('별도 교차 발행 규칙 등록부가 없습니다. 자동 작업의 대상 목록만 표시하며 실제 트리거·세부 조건은 미확인입니다.')
    reader.warn('로컬 완료·업로드 기록은 현재 공개 여부나 내용 검증 완료를 증명하지 않습니다.')
    if launchagents_dir is None:
        reader.warn('launchd 일정 메타데이터 경로가 지정되지 않아 자동 실행 시각은 미확인입니다.')

    def config(name):
        primary = root / 'ax-console/config' / name
        return reader.read(primary if primary.exists() else root / 'config' / name, name, dict) or {}

    cfg = config('accounts.json').get('accounts', {})
    if not isinstance(cfg, dict):
        reader.warn('accounts.json: 계정 자료 구조가 올바르지 않습니다.')
        cfg = {}
    for acc, label in ACCOUNTS.items():
        item = cfg.get(acc)
        if not isinstance(item, dict):
            reader.warn(f'{label} 계정 설정이 없습니다.')
            continue
        snapshot['accounts'][list(ACCOUNTS).index(acc)]['label'] = _text(item.get('label')) or label
        channels = item.get('channels', {})
        if not isinstance(channels, dict):
            reader.warn(f'{label} 채널 설정 구조가 올바르지 않습니다.')
            continue
        for raw_channel, info in list(channels.items())[:MAX_ROWS]:
            channel = _channel(raw_channel)
            if not channel or not isinstance(info, dict):
                reader.warn(f'{label} 채널 설정에 올바르지 않은 항목이 있습니다.')
                continue
            snapshot['channels'].append({'id': f'{acc}:{channel}', 'account_id': acc,
                'platform': channel, 'label': LABELS.get(channel, channel),
                'target_label': _text(info.get('target_label') or info.get('blog') or info.get('site')),
                'configured_status': _text(info.get('status')) or 'registered', 'auth_status': 'unknown',
                'enabled': info.get('enabled') if isinstance(info.get('enabled'), bool) else None})

    automation_cfg = config('automations.json')
    raw_jobs = automation_cfg.get('jobs', [])
    if not isinstance(raw_jobs, list):
        reader.warn('automations.json: 작업 목록 구조가 올바르지 않습니다.')
        raw_jobs = []
    jobs = {}
    for job in reader.rows(raw_jobs, '자동 작업 설정'):
        job_key = job.get('job')
        if not isinstance(job_key, str):
            continue
        if job_key in jobs:
            reader.warn('자동 작업 설정: 중복 작업 키는 연결하지 않았습니다.')
            jobs[job_key] = None
        else:
            jobs[job_key] = job
    local_platforms = set()
    for job_key, job in jobs.items():
        if job is None:
            continue
        owner = _account(job.get('account'))
        targets = job.get('channels', [])
        targets = [(p[0], _channel(p[1])) for p in targets if isinstance(p, list) and len(p) == 2
                   and _account(p[0]) and _channel(p[1])] if isinstance(targets, list) else []
        local_platforms.update(channel for _, channel in targets)
        source = next((channel for acc, channel in targets if acc == owner), None)
        for dest, channel in targets:
            if dest == owner and channel == source:
                continue
            snapshot['crossposts'].append({'id': _id('route', job_key, owner, source, dest, channel),
                'owner_account_id': owner, 'destination_account_id': dest, 'source_channel': source,
                'destination_channel': channel, 'title': _text(job.get('name')) or '자동 작업 대상 경로',
                'condition': '자동 작업 대상 목록에서 확인 · 트리거·변환·간격은 미등록',
                'enabled': job.get('enabled') if isinstance(job.get('enabled'), bool) else None})
    snapshot['integrations'] = _integration_catalog(local_platforms)

    raw_contents = defaultdict(list)
    task_links = defaultdict(list)
    for path in reader.files(data / 'content', '*/*/*/meta.json', '콘텐츠 메타데이터'):
        row = reader.read(path, '콘텐츠 메타데이터', dict)
        if row is None:
            continue
        item = _content(_id('content', reader.key(path)), row, _account(row.get('owner_account_id') or row.get('account')))
        item['channels'] = sorted({_channel(c) for c in row.get('channels', []) if _channel(c)}) if isinstance(row.get('channels'), list) else []
        contents.append(item)
        raw_id = row.get('id')
        if isinstance(raw_id, str):
            raw_contents[raw_id].append(item)
        links = row.get('tasks', {})
        if isinstance(links, dict):
            for ch, task_id in links.items():
                if isinstance(task_id, str) and _channel(ch):
                    task_links[task_id].append((item, _channel(ch)))
    if any(len(v) > 1 for v in raw_contents.values()):
        reader.warn('콘텐츠: 중복 원본 키가 있어 자동 연결하지 않았습니다.')

    tasks = reader.read(data / 'tasks.json', '콘솔 작업 목록', list)
    task_occurrences = defaultdict(int)
    task_rows = reader.rows(tasks or [], '콘솔 작업 목록')
    task_keys = defaultdict(int)
    for row in task_rows:
        if isinstance(row.get('id'), str):
            task_keys[row['id']] += 1
    for row in task_rows:
        dest = _account(row.get('destination_account_id') or row.get('account'))
        channel = _channel(row.get('channel'))
        raw_task_id = row.get('id')
        links = task_links.get(raw_task_id, []) if isinstance(raw_task_id, str) and task_keys[raw_task_id] == 1 else []
        links = [c for c, ch in links if ch == channel]
        reference = row.get('content_id') or row.get('content')
        possible = raw_contents.get(reference, []) if isinstance(reference, str) else []
        content = links[0] if len(links) == 1 else possible[0] if not links and len(possible) == 1 else None
        if isinstance(raw_task_id, str) and task_keys[raw_task_id] == 1:
            stable = _id('task', raw_task_id)
        else:
            stable = _id('task', raw_task_id, row)
            if isinstance(raw_task_id, str):
                reader.warn('콘솔 작업: 중복 작업 키는 항목별 별도 기록으로 표시합니다.')
        task_occurrences[stable] += 1
        did = _id('delivery', stable, task_occurrences[stable])
        if content is None:
            content = _content(_id('task_content', stable, task_occurrences[stable]), row,
                               _account(row.get('owner_account_id') or row.get('source_account_id')) or dest)
            contents.append(content)
            if links or len(possible) > 1:
                reader.warn('콘솔 작업: 중복 원본 참조로 별도 기록을 표시합니다.')
        if channel and channel not in content['channels']:
            content['channels'].append(channel)
        deliveries.append(_delivery(did, content, dest, channel, _status(row.get('status')),
            when=row.get('scheduled_at') or row.get('schedule'), kind='local_request', url=row.get('url'),
            evidence='콘솔 작업의 저장된 상태 · 실제 공개·내용은 미검증'))

    for path in reader.files(root / 'personal/claude-jobs/state', '*.jsonl', '개인 작업 기록', limit=20):
        for offset, row in reader.jsonl(path):
            # Skips/dry runs describe a run, not a fabricated content or delivery.
            if row.get('status') in ('skipped', 'dry', 'dry_run'):
                continue
            content = _content(_id('state_content', reader.key(path), offset), row, 'personal')
            contents.append(content)
            urls = row.get('urls', {})
            if not isinstance(urls, dict):
                reader.warn('개인 작업 JSONL: 채널 주소 구조가 올바르지 않습니다.')
                continue
            for raw_channel, url in list(urls.items())[:30]:
                channel = _channel(raw_channel)
                if not channel:
                    continue
                content['channels'].append(channel)
                deliveries.append(_delivery(_id('state_delivery', reader.key(path), offset, channel), content,
                    'personal', channel, _status(row.get('status')), url=url,
                    evidence='개인 작업 JSONL의 게시 보고 · 실제 공개·내용은 미검증'))

    for path in reader.files(root / 'dept/disaster-shorts', '*/upload.json', '학과 숏츠 업로드 기록'):
        row = reader.read(path, '학과 숏츠 업로드 기록', dict)
        if row is None:
            continue
        content = _content(_id('upload_content', reader.key(path)), row, 'dept', kind='short')
        content.update(title=_text(row.get('title')) or '재난안전 숏츠 업로드 기록', channels=['youtube'],
                       created_at=_time(row.get('uploaded_at')), updated_at=_time(row.get('uploaded_at')))
        scheduled = row.get('publish_at_kst') or row.get('publish_at')
        content['status'] = 'scheduled' if _time(scheduled) else 'unknown'
        contents.append(content)
        deliveries.append(_delivery(_id('upload_delivery', reader.key(path)), content, 'dept', 'youtube',
            'scheduled_recorded' if _time(scheduled) else 'unknown', when=scheduled,
            kind='remote_recorded', url=row.get('url'), evidence='저장된 업로드·원격 예약 기록 · 현재 원격 상태는 미조회'))

    queue_path = root / 'dept/youtube-shorts-auto/posts/tiktok_queue.json'
    queue = reader.read(queue_path, '틱톡 대기열', list)
    queue_occurrences = defaultdict(int)
    for row in reader.rows(queue or [], '틱톡 대기열'):
        owner = _account(row.get('owner_account_id') or row.get('source_account_id'))
        source = row.get('source')
        if owner is None:
            owner = {'geoai': 'personal', 'geoai_short': 'personal', 'shorts-disaster': 'dept',
                     'youtube_upload': 'dept', 'career': 'dept'}.get(source) if isinstance(source, str) else None
        if owner is None:
            reader.warn('틱톡 대기열: 일부 원본 소유 계정은 미확인입니다.')
        # Video identity is hashed only: paths are never read or returned.
        identity = (row.get('id') or row.get('video'), row.get('added'), source)
        if not identity[0]:
            identity = (row.get('title'), row.get('added'), source)
        key = _id('queue', identity)
        queue_occurrences[key] += 1
        key = _id('queue_record', key, queue_occurrences[key])
        content = _content(_id('queue_content', key), row, owner, kind='short')
        posted = row.get('posted')
        state = _status(posted.get('status')) if isinstance(posted, dict) else 'unknown' if posted else 'queued'
        if state == 'queued' and isinstance(row.get('tries'), (int, float)) and row.get('tries', 0) > 0:
            reader.warn('틱톡 대기열: 재시도 이력이 있으며 현재 외부 결과는 미확인입니다.')
        content.update(channels=['tiktok'], created_at=_time(row.get('added')),
                       status='reported_published' if state == 'reported_published' else 'failed' if state == 'failed' else 'scheduled' if state == 'queued' else 'unknown')
        contents.append(content)
        deliveries.append(_delivery(_id('queue_delivery', key), content, 'dept', 'tiktok', state,
            when=row.get('not_before'), kind='local_request', url=posted.get('url') if isinstance(posted, dict) else row.get('url'),
            evidence='틱톡 대기열의 저장된 결과 · not_before는 가장 이른 요청 시각이며 실제 게시 시각은 미확인'))

    for path in reader.files(data / 'incidents', '*/*.json', '장애 기록'):
        row = reader.read(path, '장애 기록', dict)
        if row is None:
            continue
        snapshot['incidents'].append({'id': _id('incident', reader.key(path)),
            'title': _text(row.get('title') or row.get('name')) or '장애 기록',
            'account_id': _account(row.get('account_id') or row.get('account')),
            'severity': _text(row.get('severity')) or 'unknown', 'status': _text(row.get('status')) or 'unknown',
            'summary': _text(row.get('summary')) or '저장된 장애 기록 · 원문 로그는 이 조회에 포함하지 않습니다.',
            'last_at': _time(row.get('last_at') or row.get('last'))})

    for path in reader.files(data / 'proposals', '*-W*_*.json', '기획 제안', limit=8):
        row = reader.read(path, '기획 제안', dict)
        if row is None:
            continue
        items = row.get('items', [])
        if not isinstance(items, list):
            reader.warn('기획 제안: 항목 구조가 올바르지 않습니다.')
            continue
        proposal_keys = defaultdict(int)
        proposal_rows = reader.rows(items, '기획 제안')
        for item in proposal_rows:
            if isinstance(item.get('id'), str):
                proposal_keys[item['id']] += 1
        occurrences = defaultdict(int)
        for item in proposal_rows:
            raw_id = item.get('id')
            identity = raw_id if isinstance(raw_id, str) and proposal_keys[raw_id] == 1 else item
            key = _id('proposal', reader.key(path), identity)
            occurrences[key] += 1
            snapshot['proposals'].append({'id': _id('proposal_item', key, occurrences[key]),
                'owner_account_id': _account(item.get('owner_account_id') or row.get('account')),
                'title': _text(item.get('title') or item.get('topic')) or '제목 미기록',
                'summary': _text(item.get('summary') or item.get('why'), 500),
                'status': _text(item.get('status')) or 'unknown'})

    for delivery in deliveries:
        if delivery['scheduled_at'] is not None or delivery['status'] in ('queued', 'scheduled_recorded', 'paused'):
            content = next(c for c in contents if c['id'] == delivery['content_id'])
            snapshot['schedule'].append({'id': _id('schedule', delivery['id']), 'title': content['title'],
                'owner_account_id': delivery['owner_account_id'], 'destination_account_id': delivery['destination_account_id'],
                'channel': delivery['channel'], 'scheduled_at': delivery['scheduled_at'], 'kind': delivery['schedule_kind'],
                'status': delivery['status'], 'content_id': content['id']})

    if launchagents_dir is not None:
        agent_dir = Path(launchagents_dir).resolve()
        for path in reader.files(agent_dir, 'com.smuds.*.plist', 'launchd 일정 메타데이터', external=True):
            row = reader.read(path, 'launchd 일정 메타데이터', dict, external=True)
            if row is None:
                continue
            job_key = path.stem.removeprefix('com.smuds.')
            job = jobs.get(job_key) or {}
            owner = _account(job.get('account'))
            when = _next_calendar(row.get('StartCalendarInterval'), now)
            if row.get('StartInterval'):
                reader.warn('launchd 간격 작업의 정확한 다음 시각은 추측하지 않습니다.')
                when = None
            targets = job.get('channels', [])
            targets = [(p[0], _channel(p[1])) for p in targets if isinstance(p, list) and len(p) == 2 and _account(p[0]) and _channel(p[1])] if isinstance(targets, list) else []
            for dest, channel in targets or [(None, None)]:
                snapshot['schedule'].append({'id': _id('launchd', path.name, dest, channel),
                    'title': _text(job.get('name')) or '자동 실행 메타데이터', 'owner_account_id': owner,
                    'destination_account_id': dest, 'channel': channel, 'scheduled_at': when, 'kind': 'local_request',
                    'status': 'paused' if row.get('Disabled') is True else 'unknown', 'content_id': None})
        reader.warn('launchd plist는 로컬 실행 계획이며 현재 로드·활성 여부와 실제 채널 공개 시각은 미확인입니다.')

    if account != 'all':
        def related(item):
            return item.get('owner_account_id') == account or item.get('destination_account_id') == account
        snapshot['deliveries'] = [d for d in deliveries if related(d)]
        snapshot['crossposts'] = [r for r in snapshot['crossposts'] if related(r)]
        retained = {d['content_id'] for d in snapshot['deliveries']}
        # Target-only planned sources are also discoverable through catalog routes.
        route_sources = {(r['owner_account_id'], r['source_channel']) for r in snapshot['crossposts']}
        snapshot['contents'] = [c for c in contents if c['owner_account_id'] == account or c['id'] in retained
            or any((c['owner_account_id'], ch) in route_sources for ch in c['channels'])]
        snapshot['schedule'] = [s for s in snapshot['schedule'] if related(s)]
        snapshot['channels'] = [c for c in snapshot['channels'] if c['account_id'] == account]
        snapshot['incidents'] = [i for i in snapshot['incidents'] if i['account_id'] == account]
        snapshot['proposals'] = [p for p in snapshot['proposals'] if p['owner_account_id'] == account]
    snapshot['contents'].sort(key=lambda c: (c['updated_at'] or c['created_at'] or '', c['id']), reverse=True)
    snapshot['schedule'].sort(key=lambda s: (s['scheduled_at'] is None, s['scheduled_at'] or '', s['id']))
    return snapshot
