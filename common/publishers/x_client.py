"""X API v2 최소 사용자 문맥 경계. transport 기본 차단, 획득·폴링 없음.

공식 POST JSON/Bearer와 고정 호스트: https://docs.x.com/x-api/posts/create-post
본인 확인: https://docs.x.com/x-api/users/get-my-user
원문/URL entities: https://docs.x.com/x-api/posts/get-post-by-id
사용자명 내부 범위는 1..15 영숫자/밑줄: https://help.x.com/en/managing-your-account/change-x-handle
사용자 문맥 OAuth2 PKCE: https://docs.x.com/fundamentals/authentication/oauth-2-0/authorization-code
소유자 읽기 성공은 공개성 증명이 아니다. 원문 재구성·가중 길이·비용 정책은 상위 경계 책임이다.
"""
from datetime import datetime
import json
import math
import re
from common.operations.models import ContractError

MAX_BYTES=1024*1024
ME_PATH='/2/users/me?user.fields=protected'
POST_FIELDS='?tweet.fields=author_id%2Ccreated_at%2Centities%2Cwithheld'
_ID=re.compile(r'[0-9]{1,64}')
_TOKEN=re.compile(r'[A-Za-z0-9._~+/=-]{1,16384}')


def _error(code='x_invalid_response'):
    raise ContractError(code) from None


def _id(value,code='x_invalid_response'):
    if type(value) is not str or not _ID.fullmatch(value):_error(code)
    return value


def _text(value,code='x_invalid_response'):
    if type(value) is not str or not value.strip() or '\x00' in value or len(value)>25000:_error(code)
    try:value.encode('utf-8')
    except UnicodeError:_error(code)
    return value


def _exact(value,required,optional=()):
    if type(value) is not dict or not set(required)<=set(value) or set(value)-set(required)-set(optional):_error()


def _pairs(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('duplicate')
        result[key]=value
    return result


def _constant(_):raise ValueError('constant')


def _json(raw):
    if type(raw) is not bytes or len(raw)>MAX_BYTES:_error()
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=_constant)
        # Validate strings recursively, including ignored default name fields.
        def check(v,depth=0):
            if depth>32:raise ValueError('depth')
            if type(v) is str:v.encode('utf-8')
            elif type(v) is dict:
                for k,item in v.items():check(k,depth+1);check(item,depth+1)
            elif type(v) is list:
                for item in v:check(item,depth+1)
            elif type(v) is float and not math.isfinite(v):raise ValueError('float')
        check(value)
    except (ValueError,UnicodeError,RecursionError):_error()
    return value


def _history(data):
    for key in ('edit_history_tweet_ids','edit_history_post_ids'):
        if key in data:
            value=data[key]
            if type(value) is not list or not 1<=len(value)<=100 or any(type(v) is not str or not _ID.fullmatch(v) for v in value):_error()


def _entities(value):
    # Only URL evidence is returned. Standard non-URL entity groups are validated
    # as bounded JSON objects and omitted; unknown groups fail closed.
    _exact(value,(),('urls','hashtags','cashtags','mentions','annotations'))
    urls=value.get('urls',[])
    if type(urls) is not list or len(urls)>100:_error()
    result=[]
    for row in urls:
        _exact(row,('start','end','url','expanded_url'),('display_url','unwound_url','images','title','description','status','media_key'))
        if type(row['start']) is not int or type(row['end']) is not int or not 0<=row['start']<row['end']<=100000:_error()
        for key,item in row.items():
            if key in ('start','end'):continue
            if key=='status':
                if type(item) is not int or not 100<=item<=599:_error()
            elif key=='images':
                if type(item) is not list or len(item)>100:_error()
                for image in item:
                    _exact(image,('height','width','url'))
                    if any(type(image[k]) is not int or not 1<=image[k]<=100000 for k in ('height','width')):_error()
                    _text(image['url'])
            elif key in ('title','description'):
                if type(item) is not str or len(item)>25000 or '\x00' in item:_error()
            else:_text(item)
        result.append({k:v for k,v in row.items() if k in ('start','end','url','expanded_url','display_url','unwound_url')})
    shapes={'hashtags':(('start','end','tag'),()),'cashtags':(('start','end','tag'),()),'mentions':(('start','end','username'),('id',)),'annotations':(('start','end','probability','type','normalized_text'),())}
    for key in set(value)-{'urls'}:
        if type(value[key]) is not list or len(value[key])>100:_error()
        required,optional=shapes[key]
        for item in value[key]:
            _exact(item,required,optional)
            if type(item['start']) is not int or type(item['end']) is not int or not 0<=item['start']<item['end']<=100000:_error()
            for field,v in item.items():
                if field in ('start','end'):continue
                if field=='probability':
                    if type(v) not in (int,float) or not 0<=v<=1:_error()
                elif field=='id':_id(v)
                else:_text(v)
    return {'urls':result}


class XApiClient:
    __slots__=('_token','_transport')
    def __init__(self,access_token,*,transport=None,login_mode='oauth2_pkce'):
        if type(access_token) is not str or not _TOKEN.fullmatch(access_token) or login_mode!='oauth2_pkce' or transport is not None and not callable(transport):_error('x_invalid_request')
        self._token,self._transport=access_token,transport
    def __repr__(self):return '<XApiClient private>'
    def _send(self,method,path,form=None):
        if self._transport is None:_error('x_transport_unregistered')
        headers={'Accept':'application/json','Authorization':'Bearer '+self._token};body=None
        if form is not None:
            headers['Content-Type']='application/json'
            body=json.dumps(form,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        failed=False
        try:response=self._transport(method,path,headers,body)
        except Exception:failed=True
        if failed:_error('x_api_unavailable')
        if type(response) is not tuple or len(response)!=2 or type(response[0]) is not int:_error()
        if not 200<=response[0]<300:_error('x_api_unavailable')
        value=_json(response[1]);_exact(value,('data',))
        return value['data']
    def inspect_account(self):
        data=self._send('GET',ME_PATH)
        _exact(data,('id','username','protected'),('name',))
        if type(data['username']) is not str or not re.fullmatch(r'[A-Za-z0-9_]{1,15}',data['username']) or type(data['protected']) is not bool:_error()
        if 'name' in data:_text(data['name'])
        return dict(id=_id(data['id']),username=data['username'],protected=data['protected'])
    def create_post(self,text):
        text=_text(text,'x_invalid_request')
        data=self._send('POST','/2/tweets',{'text':text})
        _exact(data,('id','text'),('edit_history_tweet_ids','edit_history_post_ids'));_history(data)
        return dict(id=_id(data['id']),text=_text(data['text']))
    def read_post(self,post_id):
        post_id=_id(post_id,'x_invalid_request');data=self._send('GET','/2/tweets/'+post_id+POST_FIELDS)
        _exact(data,('id','text','author_id','created_at'),('entities','withheld','edit_history_tweet_ids','edit_history_post_ids'));_history(data)
        if data['id']!=post_id:_error()
        try:
            timestamp=datetime.fromisoformat(data['created_at'].replace('Z','+00:00'))
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:_error()
        except (ValueError,TypeError,AttributeError):_error()
        result=dict(id=_id(data['id']),text=_text(data['text']),author_id=_id(data['author_id']),created_at=data['created_at'],entities=_entities(data.get('entities',{})))
        if 'withheld' in data:
            held=data['withheld'];_exact(held,('country_codes',),('copyright','scope'))
            if type(held['country_codes']) is not list or not held['country_codes'] or any(type(c) is not str or not re.fullmatch(r'[A-Z]{2}',c) for c in held['country_codes']):_error()
            if 'copyright' in held and type(held['copyright']) is not bool:_error()
            if 'scope' in held and held['scope'] not in ('tweet','post','user'):_error()
            result['withheld']={k:list(v) if type(v) is list else v for k,v in held.items()}
        return result
