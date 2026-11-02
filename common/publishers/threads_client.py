"""Threads API 요청·응답 경계. 실제 transport는 아직 등록하지 않는다.

공식 Meta 샘플의 postman/threads-api.postman_collection.json에서 경로·fields·상태를
확인했다. Authorization Bearer의 Threads 전용 live 계약은 추가 확인이 필요하다.
따라서 기본 transport는 항상 차단하며 테스트/신뢰된 서버가 명시 주입한 transport만
요청을 받는다. 토큰을 URL/query/body로 보내는 fallback·리다이렉트·재시도는 없다.
근거: https://github.com/fbsamples/threads_api/blob/main/postman/threads-api.postman_collection.json
"""
import json
import math
import re
from urllib.parse import urlencode

from common.operations.models import ContractError

_MAX_BYTES=1024*1024
_ID=re.compile(r'[0-9]{1,64}')
_STATUSES=frozenset(('EXPIRED','ERROR','FINISHED','IN_PROGRESS','PUBLISHED'))


def _error(code):
    raise ContractError(code) from None


def _id(value,code='threads_invalid_request'):
    if not isinstance(value,str) or _ID.fullmatch(value) is None:
        _error(code)
    return value


def _string(value,limit,*,empty=False,code='threads_invalid_response'):
    if not isinstance(value,str) or len(value)>limit or '\x00' in value or (not empty and not value.strip()):
        _error(code)
    try:value.encode('utf-8')
    except UnicodeError:_error(code)
    return value


def _pairs(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('duplicate')
        value[key]=item
    return value


def _constant(_):raise ValueError('nonfinite')


def _float(value):
    parsed=float(value)
    if not math.isfinite(parsed):raise ValueError('nonfinite')
    return parsed


def _unicode(value,depth=0):
    if depth>64:raise ValueError('depth')
    if isinstance(value,str):value.encode('utf-8')
    elif isinstance(value,dict):
        for key,item in value.items():_unicode(key,depth+1);_unicode(item,depth+1)
    elif isinstance(value,list):
        for item in value:_unicode(item,depth+1)


class ThreadsApiClient:
    __slots__=('_access_token','_transport')

    def __init__(self,access_token,*,transport=None):
        if (not isinstance(access_token,str) or re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,16384}',access_token) is None
                or transport is not None and not callable(transport)):
            _error('threads_invalid_request')
        self._access_token,self._transport=access_token,transport

    def __repr__(self):return '<ThreadsApiClient private>'

    def _send(self,method,path,form=None):
        if self._transport is None:
            _error('threads_transport_unregistered')
        headers={'Accept':'application/json','Authorization':'Bearer '+self._access_token}
        body=None
        if form is not None:
            headers['Content-Type']='application/x-www-form-urlencoded'
            body=urlencode(form,encoding='utf-8',errors='strict').encode('ascii')
        failed=False
        try:response=self._transport(method,path,headers,body)
        except Exception:failed=True
        if failed:_error('threads_api_unavailable')
        if (not isinstance(response,tuple) or len(response)!=2 or type(response[0]) is not int
                or not isinstance(response[1],bytes)):
            _error('threads_invalid_response')
        status,raw=response
        if not 200<=status<300:
            _error('threads_api_unavailable')
        if len(raw)>_MAX_BYTES:
            _error('threads_invalid_response')
        failed=False
        try:
            value=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=_constant,parse_float=_float)
            _unicode(value)
        except (ValueError,UnicodeError,RecursionError):failed=True
        if failed or not isinstance(value,dict):
            _error('threads_invalid_response')
        if 'error' in value:
            _error('threads_api_unavailable')
        return value

    def me(self):
        row=self._send('GET','/me?'+urlencode({'fields':'id,username'}))
        return dict(id=_id(row.get('id'),'threads_invalid_response'),username=_string(row.get('username'),256))

    def create_text(self,user_id,text):
        user_id=_id(user_id);text=_string(text,500,code='threads_invalid_request')
        row=self._send('POST','/'+user_id+'/threads',{'media_type':'TEXT','text':text,'auto_publish_text':'false'})
        return dict(id=_id(row.get('id'),'threads_invalid_response'))

    def container_status(self,container_id):
        container_id=_id(container_id)
        row=self._send('GET','/'+container_id+'?'+urlencode({'fields':'id,status,error_message'}))
        if row.get('id')!=container_id or not isinstance(row.get('status'),str) or row['status'] not in _STATUSES:
            _error('threads_invalid_response')
        result=dict(id=container_id,status=row['status'])
        if 'error_message' in row:
            _string(row['error_message'],2000,empty=True)  # 원격 오류 원문은 결과에 복사하지 않는다.
        return result

    def publish(self,user_id,container_id):
        user_id,container_id=_id(user_id),_id(container_id)
        row=self._send('POST','/'+user_id+'/threads_publish',{'creation_id':container_id})
        return dict(id=_id(row.get('id'),'threads_invalid_response'))

    def read_post(self,post_id):
        post_id=_id(post_id)
        row=self._send('GET','/'+post_id+'?'+urlencode({'fields':'id,owner,text,timestamp,media_type,permalink'}))
        if row.get('id')!=post_id or not isinstance(row.get('owner'),dict):
            _error('threads_invalid_response')
        return dict(id=post_id,owner={'id':_id(row['owner'].get('id'),'threads_invalid_response')},
            text=_string(row.get('text'),500,empty=True),timestamp=_string(row.get('timestamp'),100),
            media_type=_string(row.get('media_type'),64),permalink=_string(row.get('permalink'),2000))
