"""명시 버전 Facebook Pages 요청·응답 경계. 기본 transport는 차단한다.

공식 Meta SDK의 Page.create_feed()/PagePost.api_get()와 필드 계약을 근거로 한다:
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/page.py
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/pagepost.py
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/api.py
버전 형식 검사는 최신성·해당 앱의 버전 지원을 증명하지 않는다. /me 응답은 숫자
identity 관측일 뿐 Page 유형·게시 권한·소유권을 증명하지 않는다. is_published와
is_hidden 역시 관측값이며 공개 검증 완료로 변환하지 않는다. 실제 transport,
Page token·tasks·scope와 공개 접근 수락은 별도 서버 실행 경계가 담당한다.
"""
from datetime import datetime
import json
import math
import re
from urllib.parse import urlencode,urlsplit

from common.operations.models import ContractError
from .facebook_payloads import MAX_TEXT_BYTES,validate_facebook_text

_MAX_BYTES=1024*1024
_ID=re.compile(r'[0-9]{1,64}')
_POST=re.compile(r'([0-9]{1,64})_([0-9]{1,64})')
_VERSION=re.compile(r'v[1-9][0-9]*\.0')
_FIELDS='id,from,message,created_time,permalink_url,is_published,is_hidden'


def _error(code):raise ContractError(code) from None


def _id(value,*,post=False,code='facebook_invalid_request'):
    pattern=_POST if post else _ID
    if type(value) is not str or pattern.fullmatch(value) is None:_error(code)
    return value


def _text(value,limit,code='facebook_invalid_response'):
    if type(value) is not str or not value.strip() or '\x00' in value:_error(code)
    try:raw=value.encode('utf-8')
    except UnicodeError:_error(code)
    if len(raw)>limit:_error(code)
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


def _time(value):
    value=_text(value,100)
    failed=False
    try:
        timestamp=datetime.fromisoformat(value.replace('Z','+00:00'))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:failed=True
    except (ValueError,OverflowError):failed=True
    if failed:_error('facebook_invalid_response')
    return value


def _permalink(value):
    value=_text(value,2000)
    if any(ord(char)<=32 or ord(char)==127 for char in value):_error('facebook_invalid_response')
    failed=False
    try:
        parsed=urlsplit(value)
        if (parsed.scheme!='https' or parsed.hostname not in ('www.facebook.com','facebook.com')
                or parsed.username is not None or parsed.password is not None or parsed.port is not None
                or parsed.netloc not in ('www.facebook.com','facebook.com') or parsed.query or parsed.fragment):failed=True
    except ValueError:failed=True
    if failed:_error('facebook_invalid_response')
    return value


class FacebookApiClient:
    __slots__=('_access_token','_api_version','_transport')

    def __init__(self,access_token,*,api_version,transport=None):
        if (type(access_token) is not str or re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,16384}',access_token) is None
                or type(api_version) is not str or _VERSION.fullmatch(api_version) is None
                or transport is not None and not callable(transport)):
            _error('facebook_invalid_request')
        self._access_token,self._api_version,self._transport=access_token,api_version,transport

    def __repr__(self):return '<FacebookApiClient private>'

    def _send(self,method,path,form=None):
        if self._transport is None:_error('facebook_transport_unregistered')
        headers={'Accept':'application/json','Authorization':'Bearer '+self._access_token};body=None
        if form is not None:
            headers['Content-Type']='application/x-www-form-urlencoded'
            body=urlencode(form,encoding='utf-8',errors='strict').encode('ascii')
        failed=False
        try:response=self._transport(method,'/'+self._api_version+path,headers,body)
        except Exception:failed=True
        if failed:_error('facebook_api_unavailable')
        if (not isinstance(response,tuple) or len(response)!=2 or type(response[0]) is not int
                or not isinstance(response[1],bytes)):_error('facebook_invalid_response')
        status,raw=response
        if not 200<=status<300:_error('facebook_api_unavailable')
        if len(raw)>_MAX_BYTES:_error('facebook_invalid_response')
        failed=False
        try:
            row=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=_constant,parse_float=_float)
            _unicode(row)
        except (ValueError,UnicodeError,RecursionError):failed=True
        if failed or not isinstance(row,dict):_error('facebook_invalid_response')
        if 'error' in row:_error('facebook_api_unavailable')
        return row

    def me(self):
        # Page access token인지나 Page 권한이 있는지는 이 숫자 ID 관측만으로 판정하지 않는다.
        row=self._send('GET','/me?'+urlencode({'fields':'id,name'}))
        return dict(id=_id(row.get('id'),code='facebook_invalid_response'),name=_text(row.get('name'),2000))

    def create_text(self,page_id,message):
        page_id=_id(page_id)
        try:message=validate_facebook_text(message)
        except ContractError:_error('facebook_invalid_request')
        row=self._send('POST','/'+page_id+'/feed',{'message':message,'published':'true'})
        identifier=_id(row.get('id'),post=True,code='facebook_invalid_response')
        if identifier.split('_')[0]!=page_id:_error('facebook_invalid_response')
        return {'id':identifier}

    def read_post(self,post_id):
        post_id=_id(post_id,post=True);page_id=post_id.split('_')[0]
        row=self._send('GET','/'+post_id+'?'+urlencode({'fields':_FIELDS}))
        if row.get('id')!=post_id or not isinstance(row.get('from'),dict):_error('facebook_invalid_response')
        owner=_id(row['from'].get('id'),code='facebook_invalid_response')
        if owner!=page_id or type(row.get('is_published')) is not bool or type(row.get('is_hidden')) is not bool:
            _error('facebook_invalid_response')
        observed={'id':post_id,'from':{'id':owner},'message':_text(row.get('message'),MAX_TEXT_BYTES),
                'created_time':_time(row.get('created_time')),'permalink_url':_permalink(row.get('permalink_url')),
                'is_published':row['is_published'],'is_hidden':row['is_hidden']}
        # PagePost.get_attachments()의 별도 EDGE 관측이다. 본문만 읽고 매체 없음으로 추정하지 않는다.
        edge=self._send('GET','/'+post_id+'/attachments')
        data=edge.get('data');paging=edge.get('paging',{})
        if (type(data) is not list or any(not isinstance(item,dict) for item in data)
                or not isinstance(paging,dict) or not data and paging.get('next')):
            _error('facebook_invalid_response')
        # 첨부가 하나라도 있으면 텍스트 전용 증거가 아니다. 원격 URL·토큰은 복사하지 않는다.
        observed['attachments']=[] if not data else [{'present':True}]
        return observed
