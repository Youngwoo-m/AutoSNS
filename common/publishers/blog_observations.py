"""원격 읽기 결과만 정규화한다. 로컬 승인 hash·대상·매체로 빈 증거를 보충하지 않는다."""
from collections.abc import Mapping
import hashlib
from html.parser import HTMLParser

from common.operations.runtime_models import utc
from .blog_payloads import PLATFORMS


class _MediaMarkup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.present = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in ('img', 'video', 'audio', 'source', 'iframe', 'object', 'embed') or (tag == 'a' and 'download' in attributes):
            self.present = True

    handle_startendtag = handle_starttag


def _string(value):
    return value if isinstance(value, str) and value else None


def _media_hashes(raw, body, body_format):
    media = raw.get('media')
    markup = _MediaMarkup()
    if body_format == 'html' and body is not None:
        markup.feed(body)
    if isinstance(media, (list, tuple)):
        if not media:
            return None if markup.present else []
        if any(not isinstance(item, Mapping) or not isinstance(item.get('content_bytes'), bytes) for item in media):
            return None
        return [hashlib.sha256(item['content_bytes']).hexdigest() for item in media]
    # Blogger가 반환한 비어 있는 images와 HTML 양쪽에서 매체 부재가 관측돼야 한다.
    if body is not None and body_format == 'html' and raw.get('images') == [] and not markup.present:
        return []
    return None


def normalize_blog_observation(platform: str, raw: Mapping, *, context: Mapping, checked_at) -> dict:
    """raw.body_text는 읽기 transport가 추출한 원격 본문이다.

    Blogger raw.content는 HTML 원문 자체를 hash한다. HTML을 승인 text와 같다고
    간주하지 않는다. raw의 사전 계산 body_sha256/media_sha256는 사용하지 않는다.
    media는 원격에서 읽은 content_bytes가 있어야 hash를 만들 수 있다.
    destination_account_id는 호출 배포 계정이며 원격 대상 인증의 근거가 아니다.
    """
    if platform not in PLATFORMS or not isinstance(raw, Mapping) or not isinstance(context, Mapping):
        raise ValueError('invalid_blog_observation')
    body = raw.get('body_text')
    body_format = 'text'
    if not isinstance(body, str):
        body = raw.get('content') if platform == 'blogger' else raw.get('body_html')
        body_format = 'html'
    if not isinstance(body, str):
        body, body_format = None, None
    blog = raw.get('blog')
    target = blog.get('id') if platform == 'blogger' and isinstance(blog, Mapping) else raw.get('target_id')
    visibility = raw.get('visibility')
    if visibility not in ('public', 'private', 'draft', 'scheduled'):
        visibility = {'DRAFT': 'draft', 'SCHEDULED': 'scheduled'}.get(raw.get('status'), 'unknown') if platform == 'blogger' else 'unknown'
        if platform == 'blogger' and raw.get('status') == 'LIVE' and raw.get('publicly_readable') is True:
            visibility = 'public'
    created = raw.get('created_at', raw.get('published'))
    try:
        created = utc(created).isoformat()
    except (ValueError, TypeError):
        created = None
    return dict(platform=platform, remote_id=_string(raw.get('remote_id', raw.get('id'))),
                url=_string(raw.get('url')), target_id=_string(target),
                destination_account_id=_string(context.get('destination_account_id')),
                title=_string(raw.get('title')), created_at=created,
                checked_at=utc(checked_at).isoformat(), visibility=visibility,
                body_sha256=hashlib.sha256(body.encode('utf-8')).hexdigest() if body is not None else None,
                body_format=body_format, media_sha256=_media_hashes(raw, body, body_format))
