"""실행·쓰기 없이 등록 교차 규칙을 허용 목록 기반의 표시 자료로 바꾼다."""
from collections.abc import Mapping
import re

_UNKNOWN = '추가 실행기 조건 확인 필요'
_FIELDS = {
    'phase': '원본 단계', 'caller': '호출 작업', 'upload_response': '업로드 응답',
    'channel_ok': '채널 확인', 'video_id_present': '영상 ID 존재', 'visibility': '공개 범위',
    'description': '설명', 'blogger_status': '블로거 상태', 'dry_run': '모의 실행',
    'no_video': '영상 생략', 'threads': '스레드 요청', 'naver_success': '네이버 성공',
    'draft_age_seconds': '초안 경과(초)', 'naver_posted_job_count': '네이버 게시 채용 수',
    'valid_job_count': '유효 채용 수', 'public_verified': '공개 확인', 'subject_area': '주제 분야',
    'shorts_only': '숏츠 전용', 'department_round': '학과 순회',
    'tistory_explicit_disabled': '티스토리 명시 중지', 'youtube_success': '유튜브 성공',
    'made_anchor': '앵커 생성', 'tiktok_enabled': '틱톡 설정', 'no_ig': '인스타 생략',
    'no_threads': '스레드 생략', 'target_previous_state': '대상 이전 상태',
}
_VALUES = dict(uploaded='업로드', scheduled='예약', published='게시', public='전체 공개',
    shared_unconfirmed='공유 확인 전', geoai_short='GeoAI 숏츠', youtube_upload='유튜브 업로드',
    jobs='채용', naver_weekly='네이버 주간', weekly_news='주간 뉴스', publish_career='진로 발행',
    disaster_publish='재난 발행', disaster='재난', survey='측량', civil='토목', building='건축',
    safety='안전', nordic='노르딕워킹', safekorea='안전한국훈련', morning='오전', evening='저녁')
_OPS = {'eq': '=', 'lte': '이하', 'gte': '이상', 'in': '중 하나', 'not_in': '제외', 'not_contains': '미포함'}


def _value(value):
    if type(value) is bool: return '예' if value else '아니오'
    if type(value) is int and 0 <= value <= 10000000: return str(value)
    if isinstance(value, str): return _VALUES.get(value, '쿠팡' if value == '쿠팡' else None)
    if isinstance(value, (tuple, list)):
        items = [_value(item) for item in value]
        if items and all(item is not None for item in items): return '·'.join(items)
    return None


def _condition(node, depth=0):
    if not isinstance(node, Mapping) or depth > 8: return _UNKNOWN
    if not node: return '별도 조건 미기재'
    for group, joiner in [('all', ' 그리고 '), ('any', ' 또는 ')]:
        if set(node) == {group} and isinstance(node[group], (tuple, list)):
            return '(' + joiner.join(_condition(item, depth + 1) for item in node[group]) + ')'
    if set(node) == {'phase'}: return _condition({'field': 'phase', 'value': node['phase']}, depth + 1)
    if not set(node) <= {'field', 'op', 'value'}: return _UNKNOWN
    field, op, value = _FIELDS.get(node.get('field')), _OPS.get(node.get('op', 'eq')), _value(node.get('value'))
    return f'{field} {op} {value}' if field and op and value is not None else _UNKNOWN


def _evidence(items):
    summaries = []
    kinds = {'config': '설정', 'installed_plist': '설치 일정', 'automation_note': '자동 작업 메모',
             'code': '코드', 'comment': '주석', 'user_stop_note': '사용자 중지 기록',
             'installed_schedule': '설치 일정', 'stale_comment': '오래된 주석', 'instruction': '운영 지침'}
    if not isinstance(items, (list, tuple)): return '근거 미수집'
    for item in items:
        if not isinstance(item, Mapping): continue
        parts = [kinds.get(item.get('kind'), '기타 근거')]
        if item.get('kind') == 'config' and type(item.get('value')) is bool:
            parts.append('설정상 켜짐' if item['value'] else '설정상 꺼짐')
        if item.get('stale') is True: parts.append('오래된 근거')
        if item.get('kind') == 'installed_plist':
            parts.append('설치됨' if item.get('present') is True else '설치 없음' if item.get('present') is False else '설치 미확인')
            parts.append('로드됨' if item.get('loaded') is True else '로드 안 됨' if item.get('loaded') is False else '로드 상태 미확인')
        summaries.append(' · '.join(parts))
    return ' / '.join(dict.fromkeys(summaries)) or '근거 미수집'


def crosspost_catalog(registry, account='all'):
    rows = []
    for identifier, rule in registry.crossposts.items():
        source = registry.connections[rule['source_connection_id']]
        destination = registry.connections[rule['destination_connection_id']]
        if account != 'all' and account not in (source.account_id, destination.account_id): continue
        parts = ['시점: ' + _condition(rule.get('trigger', {})), '조건: ' + _condition(rule.get('conditions', {}))]
        for key, label in [('delay_seconds', '지연'), ('min_gap_seconds', '최소 간격')]:
            value = rule.get(key)
            if type(value) is int and 0 <= value <= 10000000: parts.append(f'{label} {value}초')
        slots = rule.get('allowed_slots', ())
        if slots: parts.append('시간대: ' + '·'.join(_VALUES.get(slot, '추가 시간대 확인 필요') for slot in slots))
        window = rule.get('window')
        if isinstance(window, Mapping):
            start, end = window.get('start'), window.get('end')
            if all(isinstance(v, str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', v) for v in (start, end)):
                parts.append(f'허용 시간 {start}–{end}' + (' (한국시간)' if window.get('timezone') == 'Asia/Seoul' else ' (시간대 확인 필요)'))
        owner = rule.get('delivery_owner')
        activation = '기존 실행기 담당·가동 상태 미확인' if owner == 'legacy' else '계획 전용·가동 상태 미확인'
        rows.append(dict(id=identifier, owner_account_id=source.account_id, destination_account_id=destination.account_id,
            source_channel=source.platform, destination_channel=destination.platform,
            title=f'{source.platform} → {destination.platform}', condition=' / '.join(parts),
            enabled=rule.get('enabled') if type(rule.get('enabled')) is bool else None,
            delivery_owner=owner if owner in ('legacy', 'managed') else 'unknown',
            activation_summary=activation, evidence_summary=_evidence(rule.get('activation_evidence', ())),
            source='registered_rule', execution_enabled=False))
    return rows
