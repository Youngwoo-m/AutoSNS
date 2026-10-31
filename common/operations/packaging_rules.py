"""입력 어휘만 사용하는 결정적 로컬 문구 규칙. 정책 게이트는 호출 서비스 소유."""
from collections.abc import Mapping
import hashlib
import json
import unicodedata

RULES_VERSION = 'local-packaging.v1'
UNAVAILABLE_FIELDS = ('search_volume', 'competition', 'ctr', 'predicted_ctr', 'vidiq_score')


def _normalize(value):
    return unicodedata.normalize('NFC', value).strip()


def _controls(value):
    return any(unicodedata.category(c) in ('Cc', 'Cf', 'Cs') for c in value)


def build_packaging_preview(snapshot: Mapping, *, platform: str, keywords: tuple[str, ...] = ()) -> dict:
    """원문을 바꾸지 않고 제목·태그 후보를 반환한다. 플랫폼 한도 검증은 아니다."""
    if not isinstance(snapshot, Mapping) or not isinstance(platform, str) or not platform.strip():
        raise ValueError('invalid_input')
    if not isinstance(keywords, tuple) or len(keywords) > 20:
        raise ValueError('keywords_limit')
    if any(not isinstance(k, str) or len(k) > 50 for k in keywords):
        raise ValueError('keyword_length')
    title = snapshot.get('title', '')
    if not isinstance(title, str):
        raise ValueError('title')
    title = _normalize(title)
    words = list(dict.fromkeys(_normalize(k) for k in keywords if _normalize(k)))
    findings = []
    if _controls(title) or any(_controls(k) for k in words):
        findings.append(dict(code='invisible_control', message='보이지 않는 제어문자가 있어 해당 문구를 후보에서 제외했습니다.'))
    if len(title) > 300:
        findings.append(dict(code='title_too_long', message='로컬 저장 제목 한도 300자를 초과합니다.'))
    if len(words) < len(keywords):
        findings.append(dict(code='duplicate_or_empty_keyword', message='정규화 후 중복·빈 키워드를 제외했습니다.'))
    if any(k not in title for k in words):
        findings.append(dict(code='keyword_missing', message='제목에 포함되지 않은 입력 키워드가 있습니다.'))
    safe_words = [k for k in words if not _controls(k)]
    # 공백·구두점을 임의 삭제해 새 단어를 만들지 않는다. 유효한 단일 어휘만 태그로 제안.
    hashtags = ['#' + k for k in safe_words if all(c.isalnum() or c == '_' for c in k)][:10]
    options = [title]
    if safe_words:
        options.extend((' '.join([title] + safe_words), ' '.join(safe_words + [title])))
    candidates = []
    for value in dict.fromkeys(options):
        value = value.strip()
        if not value or len(value) > 300 or _controls(value):
            continue
        candidates.append(dict(id='candidate-' + hashlib.sha256(value.encode()).hexdigest()[:16],
                               title=value, hashtags=list(hashtags), reasons=['입력 제목과 명시 키워드만 조합한 로컬 규칙 후보']))
    # 바인딩에는 원문·버전·대상도 포함하되, 응답으로 전체 snapshot이나 비밀을 돌려주지 않는다.
    binding = dict(snapshot=snapshot, platform=platform, keywords=keywords, rules_version=RULES_VERSION)
    input_hash = hashlib.sha256(json.dumps(binding, ensure_ascii=True, sort_keys=True,
                                          separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    refs = [dict(url=s['url']) for s in snapshot.get('sources', ())
            if isinstance(s, Mapping) and isinstance(s.get('url'), str)]
    return dict(input_hash=input_hash, rules_version=RULES_VERSION, candidates=candidates[:3],
                findings=findings, evidence_refs=refs, unavailable_fields=list(UNAVAILABLE_FIELDS))
