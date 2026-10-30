"""검토 스냅샷의 순수 블로그 변환. 파일·설정·인증·네트워크를 읽지 않는다."""
from collections.abc import Mapping
import hashlib
import html
import re
from urllib.parse import quote, urlsplit

from common.operations.runtime_models import PublicationContext


PLATFORMS = frozenset(('blogger', 'naver', 'naver_blog', 'tistory'))


def _copy_json(value):
    if isinstance(value, Mapping):
        return {key: _copy_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy_json(item) for item in value]
    return value


def _strings(values):
    if not isinstance(values, (list, tuple)) or any(not isinstance(value, str) for value in values):
        raise ValueError('invalid_blog_labels')
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _labels(tags, category, options):
    """기존 Blogger 운영 상한(15개·200 UTF-8 bytes), 필수분류는 묵살하지 않는다."""
    cap = options.get('max_labels', 15)
    if type(cap) is not int or not 1 <= cap <= 15:
        raise ValueError('invalid_blog_labels')
    required = list(dict.fromkeys(([category] if category else []) + _strings(options.get('local_tags', ()))))
    if len(required) > cap or len(','.join(required).encode('utf-8')) > 200:
        raise ValueError('required_blog_labels_too_large')
    selected = []
    for tag in tags:
        if tag not in required and len(selected) + len(required) < cap:
            candidate = selected + [tag] + required
            if len(','.join(candidate).encode('utf-8')) <= 200:
                selected.append(tag)
    return selected + required


def _paragraphs(text):
    return '\n'.join('<p>' + html.escape(chunk).replace('\n', '<br>') + '</p>'
                     for chunk in re.split(r'\n\s*\n', text) if chunk)


def build_blog_payload(platform: str, snapshot: Mapping, context: PublicationContext) -> dict:
    """body_text는 승인 원문, body_html은 출처·AI 고지를 포함하는 발송 HTML이다.

    body_sha256는 승인 원문에 대한 로컬 준비값이다. 원격 관측 증거가 아니다.
    body_format=html도 승인 options에 명시한 경우에만 원문 마크업을 보존한다.
    자산은 참조만 복사하며 게시 가능한 URL 생성·업로드는 하지 않는다.
    """
    if platform not in PLATFORMS or context.platform != platform:
        raise ValueError('invalid_blog_platform')
    if not isinstance(snapshot, Mapping) or snapshot.get('revision') != context.content_revision or snapshot.get('manifest_hash') != context.manifest_hash:
        raise ValueError('content_changed')
    variants = snapshot.get('variants', ())
    if not isinstance(variants, (list, tuple)) or any(not isinstance(v, Mapping) for v in variants):
        raise ValueError('invalid_blog_content')
    selected = [v for v in variants if v.get('destination_account_id') == context.destination_account_id and v.get('platform') == platform]
    if len(selected) > 1:
        raise ValueError('ambiguous_blog_variant')
    text = selected[0].get('text') if selected else snapshot.get('original')
    title = snapshot.get('title')
    if not isinstance(text, str) or not text.strip() or not isinstance(title, str) or not title.strip():
        raise ValueError('invalid_blog_content')
    options = context.options
    category = options.get('category', snapshot.get('category', ''))
    notice = options.get('ai_notice', snapshot.get('ai_notice', ''))
    if not isinstance(category, str) or not isinstance(notice, str):
        raise ValueError('invalid_blog_content')
    body_format = options.get('body_format', 'text')
    if body_format not in ('text', 'html'):
        raise ValueError('invalid_blog_body_format')
    parts = [text if body_format == 'html' else _paragraphs(text)]
    sources = snapshot.get('sources', ())
    if not isinstance(sources, (list, tuple)):
        raise ValueError('invalid_blog_sources')
    for source in sources:
        if not isinstance(source, Mapping) or not isinstance(source.get('url'), str) or not isinstance(source.get('note', ''), str):
            raise ValueError('invalid_blog_sources')
        url = source['url']
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise ValueError('invalid_blog_sources')
        href = html.escape(quote(url, safe=":/?&=#%+@!$,;~*'()[]"), quote=True)
        parts.append(f'<p>출처: <a href="{href}" rel="noopener">{html.escape(source.get("note") or url)}</a></p>')
    if notice:
        parts.append('<p>' + html.escape(notice) + '</p>')
    assets = snapshot.get('assets', ())
    if not isinstance(assets, (list, tuple)) or any(not isinstance(a, Mapping) for a in assets):
        raise ValueError('invalid_blog_assets')
    tags = _strings(options.get('tags', snapshot.get('tags', ())))
    result = dict(platform=platform, title=title, body_text=text, body_html='\n'.join(parts),
                  body_format=body_format, body_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
                  sources=_copy_json(sources), assets=_copy_json(assets), category=category, ai_notice=notice,
                  tags=tags, owner_account_id=context.owner_account_id,
                  destination_account_id=context.destination_account_id,
                  connection_id=context.connection_id, target_id=context.target_id)
    if platform == 'blogger':
        label_options = dict(options)
        label_options.setdefault('max_labels', 6 if context.destination_account_id == 'dept' else 15)
        result['labels'] = _labels(tags, category, label_options)
    return result
