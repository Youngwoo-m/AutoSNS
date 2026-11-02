"""서버가 명시 등록하는 Threads HTTPS 전송. 기본 비활성·고정 호스트·재시도 없음.

Bearer 헤더는 RFC 6750 §2.1 표준에서 도출했다:
https://www.rfc-editor.org/rfc/rfc6750#section-2.1
Meta Postman의 token_type=bearer 및 graph.threads.net 계약:
https://github.com/fbsamples/threads_api/blob/main/postman/threads-api.postman_collection.json
샘플 src/index.js의 graph.threads.com과 컬렉션의 .net 차이는 별도 수락 확인이 남아 있다.
이 구현은 Threads가 실제 Bearer 헤더를 수용함을 검증한 증거가 아니다. 앱의
자격·발행 정책이나 ThreadsApiClient 기본 transport 차단을 해제하지 않는다.
"""
import http.client
import re
from urllib.parse import parse_qs,urlsplit

from common.operations.models import ContractError

_MAX_BYTES=1024*1024
_ID=re.compile(r'[0-9]{1,64}')
_TOKEN=re.compile(r'Bearer ([A-Za-z0-9._~+/-]{1,16384}=*)')
_FIELDS=frozenset(('id,status,error_message','id,owner,text,timestamp,media_type,permalink'))


def _invalid():raise ContractError('threads_invalid_request') from None


def _form(body):
    if not isinstance(body,bytes) or not 0<len(body)<=32768:_invalid()
    try:
        fields=parse_qs(body.decode('ascii'),keep_blank_values=True,strict_parsing=True,encoding='utf-8',errors='strict')
    except (ValueError,UnicodeError):_invalid()
    if not all(len(values)==1 for values in fields.values()):_invalid()
    return {key:values[0] for key,values in fields.items()}


def _check(method,path,headers,body):
    if (method not in ('GET','POST') or not isinstance(path,str) or len(path)>4096
            or not path.startswith('/') or '#' in path or any(not 0x21<=ord(char)<=0x7e for char in path)
            or type(headers) is not dict):_invalid()
    allowed={'Accept','Authorization'}|({'Content-Type'} if method=='POST' else set())
    if set(headers)!=allowed or headers.get('Accept')!='application/json':_invalid()
    authorization=headers.get('Authorization')
    match=_TOKEN.fullmatch(authorization) if isinstance(authorization,str) and len(authorization)<=16391 else None
    if match is None:_invalid()
    token=match.group(1)
    # URL과 요청 본문에 토큰을 중복 전달하지 않는다. 별도의 query 인증 fallback도 없다.
    if token in path:_invalid()
    try:parsed=urlsplit(path)
    except ValueError:_invalid()
    if parsed.scheme or parsed.netloc or parsed.fragment:_invalid()
    if method=='GET':
        if body is not None:_invalid()
        try:query=parse_qs(parsed.query,keep_blank_values=True,strict_parsing=True,encoding='ascii',errors='strict')
        except (ValueError,UnicodeError):_invalid()
        if set(query)!={'fields'} or len(query['fields'])!=1:_invalid()
        fields=query['fields'][0]
        if parsed.path=='/me':
            if fields!='id,username':_invalid()
        elif not _ID.fullmatch(parsed.path[1:]) or fields not in _FIELDS:_invalid()
    else:
        if parsed.query or headers.get('Content-Type')!='application/x-www-form-urlencoded':_invalid()
        form=_form(body)
        if any(token in value for value in form.values()):_invalid()
        if re.fullmatch(r'/[0-9]{1,64}/threads',parsed.path):
            if (set(form)!={'media_type','text','auto_publish_text'} or form['media_type']!='TEXT'
                    or form['auto_publish_text']!='false' or not form['text'].strip()
                    or len(form['text'])>500 or '\x00' in form['text']):_invalid()
        elif re.fullmatch(r'/[0-9]{1,64}/threads_publish',parsed.path):
            if set(form)!={'creation_id'} or _ID.fullmatch(form['creation_id']) is None:_invalid()
        else:_invalid()
    return dict(headers)


class ThreadsHttpsTransport:
    __slots__=('_active','_connection_factory')

    def __init__(self,*,activate=False,connection_factory=http.client.HTTPSConnection):
        if type(activate) is not bool or not callable(connection_factory):_invalid()
        self._active,self._connection_factory=activate,connection_factory

    def __repr__(self):return '<ThreadsHttpsTransport private>'

    def __call__(self,method,path,headers,body):
        if not self._active:raise ContractError('threads_transport_unregistered')
        safe_headers=_check(method,path,headers,body)
        connection=None;result=None;failure=None
        try:
            # HTTPSConnection의 기본 인증서·호스트 검증을 유지한다. proxy/env 설정을 읽지 않는다.
            connection=self._connection_factory('graph.threads.net',port=443,timeout=30)
            # http.client의 디버그 출력에도 Authorization이 나타나지 않게 한다.
            connection.debuglevel=0
            connection.request(method,path,body=body,headers=safe_headers)
            response=connection.getresponse()
            if type(response.status) is not int or not 200<=response.status<300:
                failure='threads_api_unavailable'
            else:
                raw=response.read(_MAX_BYTES+1)
                if not isinstance(raw,bytes) or len(raw)>_MAX_BYTES:
                    failure='threads_invalid_response'
                else:result=(response.status,raw)
        except Exception:
            failure='threads_api_unavailable'
        finally:
            if connection is not None:
                try:connection.close()
                except Exception:pass
        if failure is not None:raise ContractError(failure) from None
        return result
