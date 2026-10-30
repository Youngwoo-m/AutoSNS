"""관리 콘텐츠의 HTTP 독립 검증·응답 조합. 디스크 경로는 노출하지 않는다."""
from copy import deepcopy

from common.operations.content_store import StoreError

CONTENT_ID = r'managed_[a-zA-Z0-9_-]{1,100}'
ASSET_ID = r'[a-zA-Z0-9_-]{1,120}'
EDIT_FIELDS = frozenset(('title', 'kind', 'series', 'status', 'original', 'variants', 'sources'))
MEDIA_TYPES = frozenset(('image/jpeg', 'image/png', 'image/webp', 'video/mp4', 'audio/mpeg', 'audio/wav'))
ERROR_STATUS = {'invalid': 400, 'not_found': 404, 'conflict': 409, 'too_large': 413,
                'unsupported_media': 415, 'storage_error': 503}
ERROR_MESSAGES = {'invalid': '올바르지 않은 요청입니다', 'not_found': '자료를 찾을 수 없습니다',
    'conflict': '다른 변경이 저장되었습니다. 최신 버전을 확인하세요', 'too_large': '요청이 너무 큽니다',
    'unsupported_media': '지원하지 않는 미디어 형식입니다', 'storage_error': '저장소를 사용할 수 없습니다'}


def positive_revision(value):
    if type(value) is not int or value < 1:
        raise StoreError('invalid')
    return value


def content_body(body, *, create=False):
    extra = 'owner_account_id' if create else 'expected_revision'
    if not isinstance(body, dict) or set(body) - (EDIT_FIELDS | {extra}) or not {'title', 'kind', extra} <= set(body):
        raise StoreError('invalid')
    if create:
        if body[extra] not in ('personal', 'dept'):
            raise StoreError('invalid')
    else:
        positive_revision(body[extra])
    return body[extra], {key: value for key, value in body.items() if key != extra}


def review_body(body):
    fields = ('revision', 'manifest_hash', 'kind', 'decision', 'notes')
    if not isinstance(body, dict) or set(body) != set(fields):
        raise StoreError('invalid')
    positive_revision(body['revision'])
    return tuple(body[field] for field in fields)


def serialize_content(content):
    result = deepcopy(content)
    for asset in result.get('assets', []):
        asset['url'] = (f"/api/v2/contents/{result['id']}/revisions/"
                        f"{result['revision']}/assets/{asset['id']}")
    return result


def content_summary(content):
    fields = ('id', 'title', 'owner_account_id', 'kind', 'series', 'status', 'revision', 'created_at', 'updated_at')
    return {**{key: content[key] for key in fields}, 'source': 'managed',
            'summary': content['original'][:300],
            'channels': list(dict.fromkeys(v['platform'] for v in content['variants'])),
            'target_accounts': list(dict.fromkeys(v['destination_account_id'] for v in content['variants']))}
