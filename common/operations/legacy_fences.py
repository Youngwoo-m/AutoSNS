"""기존 진입점의 서버 소유 등록표. import는 legacy 코드/프로필을 열지 않는다.

운영 owner/enabled를 수정하지 않는다. 아직 분해하지 않은 경로는 managed로
접수할 수 없으며, 기존에 확인한 미등록 수동 도구만 명시적으로 legacy 보존한다.
"""
from pathlib import Path
from types import MappingProxyType
import json
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.operations.content_store import StoreError
from common.operations.execution_catalog import ExecutionCatalog
from common.operations.registry import load_registry

ROOT = Path(__file__).resolve().parents[2]
_CONFIGURED_SERVICES = None


def _row(account, channel, action, jobs, source='console', *, unregistered=False, reason='leaf/caller별 관문 연결 수락 전'):
    return dict(job_ids=tuple(jobs), caller_id=f'legacy.{source}.{account}.{channel}.{action}',
                source=source, managed_eligible=False, inventory_complete=False,
                observed_unregistered=unregistered, reason=reason)


_routes = {}

def _register(account, channel, action, jobs, **kwargs):
    _routes[(account, channel, action)] = MappingProxyType(_row(account, channel, action, jobs, **kwargs))


# 기존 콘솔 ACTIONS의 모든 실제 실행 action. memo/test는 별도 무발행 허용목록이다.
for _account, _channel, _action, _job in (
    ('dept', 'youtube', 'shorts_weekly', 'ytshorts.weekly'),
    ('dept', 'youtube', 'career_publish', 'ytcareer.weekly'),
    ('dept', 'youtube', 'caption_backfill', 'captionbackfill.daily'),
    ('dept', 'instagram', 'cards_weekly', 'instacards.weekly'),
    ('dept', 'instagram', 'caption_autofix', 'captionautofix.daily'),
    ('dept', 'naver_blog', 'naver_weekly', 'naverblog.weekly'),
    ('dept', 'naver_blog', 'career_series', 'blogcareer.daily'),
    ('dept', 'naver_blog', 'naver_jobs', 'naverjobs.weekly'),
    ('dept', 'tiktok', 'tiktok_queue', 'tiktok.queue'),
    ('dept', 'x', 'x_promo', 'xpromo.daily'),
    ('personal', 'blogger', 'geoai_morning', 'geoai.daily'),
    ('personal', 'blogger', 'geoai_evening', 'geoai.evening'),
    ('personal', 'tistory', 'tistory', 'tistory'),
):
    _register(_account, _channel, _action, (_job,))

# 콘솔의 기존 콘텐츠별 직접 발행에는 operations job이 없었다. 명시된 이 ID만
# 미등록 legacy 관측으로 보존한다. 앞으로 이 ID를 등록하면 실제 owner를 따른다.
for _account, _channel in (('dept', 'blogger'), ('dept', 'naver_blog'), ('dept', 'x'), ('personal', 'blogger')):
    _jobs = (f'console.{_account}.{_channel}',)
    for _action in ('publish', 'publish-cli'):
        _register(_account, _channel, _action, _jobs, unregistered=True)

_CLAUDE_KEYS = ('survey-daily', 'survey-shorts', 'civil-daily', 'survey-friend', 'civil-friend',
                'building-daily', 'building-friend', 'safety-daily', 'safety-friend', 'safekorea', 'nordic')
for _key in _CLAUDE_KEYS:
    _register('personal', 'claude', _key, ('claude.' + _key,), source='launchd',
              reason='AX_HOUR별 모델/회차와 자율 발행 도구 미분해')
for _account, _channel, _action, _job in (
    ('personal', 'blogger', 'geoai.daily', 'geoai.daily'),
    ('personal', 'blogger', 'geoai.evening', 'geoai.evening'),
    ('dept', 'naver_blog', 'naverjobs.weekly', 'naverjobs.weekly'),
    ('dept', 'tiktok', 'tiktok.queue', 'tiktok.queue'),
    ('dept', 'youtube', 'disastershorts.crosspost', 'disastershorts.crosspost'),
):
    _register(_account, _channel, _action, (_job,), source='launchd', reason='다중 대상/큐 부수효과 미분해')

# 직접 leaf는 이들을 호출하는 작업 중 하나라도 관리로 바뀌면 전체 legacy 실행을 막는다.
_register('dept', 'youtube', 'youtube-upload-cli', ('ytshorts.weekly', 'ytshorts.trigger', 'ytcareer.weekly', 'disastershorts.weekly'),
          reason='일반 업로드의 숨은 TikTok add와 내부 caller 분해 필요')
_register('personal', 'youtube', 'youtube-upload-cli', ('geoai.daily', 'geoai.evening') + tuple('claude.' + k for k in _CLAUDE_KEYS),
          reason='일반 CLI edition으로 개인 업로드 가능; 개인 내부 caller 미분해')
for _action in ('upload', 'comment', 'delete', 'check'):
    _register('personal', 'youtube', 'geoai-short-' + _action,
              ('geoai.daily', 'geoai.evening') + tuple('claude.' + k for k in _CLAUDE_KEYS), reason='개인 업로드/댓글/삭제와 학과 큐 분해 필요')
_register('personal', 'tistory', 'tistory-post-cli', ('tistory',) + tuple('claude.' + k for k in _CLAUDE_KEYS),
          reason='Tistory dry도 브라우저 쓰기 가능; 모든 Claude 내부 caller fence 필요')
ACTION_ROUTES = MappingProxyType(_routes)
LOCAL_CHANNELS = MappingProxyType({
    'dept': frozenset(('youtube', 'instagram', 'naver_blog', 'tiktok', 'x', 'threads', 'blogger')),
    'personal': frozenset(('blogger', 'tistory', 'homepage', 'naver_blog', 'tiktok', 'youtube', 'instagram', 'kakao')),
})


def build_legacy_catalog():
    return ExecutionCatalog(callers={row['caller_id']: dict(job_ids=row['job_ids'],
        source=row['source'], legacy_allowed=True) for row in ACTION_ROUTES.values()})


def configure_legacy_services(services):
    """서버 bootstrap 전용. HTTP/환경변수에서 이 값을 받지 않는다."""
    global _CONFIGURED_SERVICES
    _CONFIGURED_SERVICES = services


def legacy_services():
    if _CONFIGURED_SERVICES is not None:
        return _CONFIGURED_SERVICES
    return dict(registry=load_registry(ROOT / 'ax-console/config/operations.json'), catalog=build_legacy_catalog())


def inventory_allows_managed(job_id, *, action_routes=ACTION_ROUTES):
    rows = [r for r in action_routes.values() if job_id in r['job_ids']]
    return bool(rows) and all(r.get('managed_eligible') is True and r.get('inventory_complete') is True for r in rows)


def guard_legacy_action(action_key, *, services=None):
    from common.operations.entrypoints import route_legacy_action
    result = route_legacy_action(action_key, services=services)
    if result.get('route') != 'legacy':
        raise StoreError('legacy_not_allowed')
    return result


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) != 3:
            raise StoreError('invalid_action')
        result = guard_legacy_action(tuple(args))
        print(json.dumps({'route': result['route']}, ensure_ascii=False))
        return 0
    except StoreError as error:
        print(json.dumps({'error': error.code}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
