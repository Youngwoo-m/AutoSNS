"""명시 등록 전 비활성인 Facebook Login 전용 HTTPS 전송.

Meta 공식 컬렉션의 Facebook Login 호스트와 Bearer 인증:
https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
허용 media/media_publish 및 children list<string> 계약:
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/iguser.py
SDK의 list를 JSON 폼 값으로 직렬화하는 _top_level_param_json_encode:
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/api.py
버전 문법 검증은 해당 버전의 지원·권한·실제 API 수락을 보증하지 않는다.
"""
import http.client
import json
import re
from urllib.parse import parse_qs, urlencode, urlsplit
from common.operations.models import ContractError
from common.publishers.instagram_client import _url, _text

_MAX_BYTES = 1024 * 1024
_ID = re.compile(r'[0-9]{1,64}')
_ROUTE = re.compile(r'/v[1-9][0-9]*\.0/([0-9]{1,64})(/children|/media|/media_publish)?')
_TOKEN = re.compile(r'Bearer ([A-Za-z0-9._~+/=-]{1,16384})')
_FIELDS = frozenset(('id,username', 'id,status_code',
                     'id,owner,caption,media_type,media_product_type,timestamp,permalink'))


def _invalid():
    raise ContractError('instagram_invalid_request') from None


def _pairs(raw):
    try:
        values = parse_qs(raw, keep_blank_values=True, strict_parsing=True,
                          encoding='utf-8', errors='strict', max_num_fields=10)
    except (ValueError, UnicodeError):
        _invalid()
    if not all(len(items) == 1 for items in values.values()):
        _invalid()
    result = {key: items[0] for key, items in values.items()}
    # Accept the exact URL encoding emitted by InstagramApiClient only.
    if urlencode(result, encoding='utf-8', errors='strict') != raw:
        _invalid()
    return result


def _check(method, path, headers, body):
    if (method not in ('GET', 'POST') or type(path) is not str or len(path) > 4096
            or any(not 0x21 <= ord(c) <= 0x7e for c in path) or '#' in path
            or type(headers) is not dict):
        _invalid()
    allowed = {'Accept', 'Authorization'} | ({'Content-Type'} if method == 'POST' else set())
    if set(headers) != allowed or headers.get('Accept') != 'application/json':
        _invalid()
    auth = headers.get('Authorization')
    match = _TOKEN.fullmatch(auth) if type(auth) is str else None
    if match is None:
        _invalid()
    token = match.group(1)
    try:
        parsed = urlsplit(path)
    except ValueError:
        _invalid()
    route = _ROUTE.fullmatch(parsed.path)
    if parsed.scheme or parsed.netloc or not route:
        _invalid()
    suffix = route.group(2)
    if method == 'GET':
        if body is not None:
            _invalid()
        query = _pairs(parsed.query)
        if set(query) != {'fields'}:
            _invalid()
        if suffix == '/children':
            if query['fields'] != 'id,media_type':
                _invalid()
        elif suffix is not None or query['fields'] not in _FIELDS:
            _invalid()
    else:
        if parsed.query or headers.get('Content-Type') != 'application/x-www-form-urlencoded':
            _invalid()
        if type(body) is not bytes or not 0 < len(body) <= 65536:
            _invalid()
        try:
            form = _pairs(body.decode('ascii'))
        except UnicodeError:
            _invalid()
        # Long secrets embedded in captions are rejected without treating an
        # ordinary word/character matching a short test token as a substring leak.
        if any(value == token or len(token) >= 16 and token in value for value in form.values()):
            _invalid()
        if suffix == '/media_publish':
            if set(form) != {'creation_id'} or not _ID.fullmatch(form['creation_id']):
                _invalid()
        elif suffix == '/media':
            keys = set(form)
            if keys == {'image_url', 'caption'}:
                _url(form['image_url'])
            elif keys == {'media_type', 'video_url', 'caption'} and form['media_type'] == 'REELS':
                _url(form['video_url'])
            elif keys == {'image_url', 'is_carousel_item'} and form['is_carousel_item'] == 'true':
                _url(form['image_url'])
            elif (keys == {'media_type', 'video_url', 'is_carousel_item'}
                  and form['media_type'] == 'VIDEO' and form['is_carousel_item'] == 'true'):
                _url(form['video_url'])
            elif keys == {'media_type', 'children', 'caption'} and form['media_type'] == 'CAROUSEL':
                try:
                    children = json.loads(form['children'])
                except (ValueError, RecursionError):
                    _invalid()
                if (type(children) is not list or not 2 <= len(children) <= 10
                        or any(type(child) is not str or not _ID.fullmatch(child) for child in children)
                        or len(set(children)) != len(children)):
                    _invalid()
            else:
                _invalid()
            if 'caption' in form:
                _text(form['caption'], 'instagram_invalid_request', caption=True)
        else:
            _invalid()
    return dict(headers)


class InstagramHttpsTransport:
    __slots__ = ('_active', '_connection_factory')

    def __init__(self, *, activate=False, connection_factory=http.client.HTTPSConnection):
        if type(activate) is not bool or not callable(connection_factory):
            _invalid()
        self._active, self._connection_factory = activate, connection_factory

    def __repr__(self):
        return '<InstagramHttpsTransport private>'

    def __call__(self, method, path, headers, body):
        if not self._active:
            raise ContractError('instagram_transport_unregistered')
        safe_headers = _check(method, path, headers, body)
        connection = None
        failure = None
        result = None
        try:
            # Default certificate/hostname validation. No env proxy, redirects,
            # retry, custom TLS context, or secondary host is consulted.
            connection = self._connection_factory('graph.facebook.com', port=443, timeout=30)
            connection.debuglevel = 0
            connection.request(method, path, body=body, headers=safe_headers)
            response = connection.getresponse()
            if type(response.status) is not int or not 200 <= response.status < 300:
                failure = 'instagram_api_unavailable'
            else:
                raw = response.read(_MAX_BYTES + 1)
                if type(raw) is not bytes or len(raw) > _MAX_BYTES:
                    failure = 'instagram_invalid_response'
                else:
                    result = (response.status, raw)
        except Exception:
            failure = 'instagram_api_unavailable'
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
        if failure:
            raise ContractError(failure) from None
        return result
