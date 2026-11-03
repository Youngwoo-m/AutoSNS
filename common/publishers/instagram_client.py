"""Facebook Login 전용 Instagram 요청 경계. 기본 transport는 차단한다.

공식 Meta SDK IGUser.create_media/create_media_publish와 IGMedia.api_get/get_children:
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/iguser.py
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/igmedia.py
버전 형식은 지원 버전임을 보증하지 않는다. Instagram Login은 별도 미지원 계약이다.
2200자 캡션은 내부 한도이며 공식 한도라고 주장하지 않는다. 공개 URL 구문 검사는
서버의 URL 소유·실제 바이트·계정 권한 증명을 대신하지 않는다. 원격 관측을 공개
검증 완료나 원격 매체 해시로 바꾸지 않는다. 자동 재시도·폴링·자격 획득은 없다.
"""
from datetime import datetime
import ipaddress
import json
import math
import re
from urllib.parse import urlencode,urlsplit,unquote
from common.operations.models import ContractError

_MAX_BYTES=1024*1024
_ID=re.compile(r'[0-9]{1,64}')
_VERSION=re.compile(r'v[1-9][0-9]*\.0')
_FIELDS='id,owner,caption,media_type,media_product_type,timestamp,permalink'

def _error(code):raise ContractError(code) from None

def _id(value,code='instagram_invalid_request'):
    if type(value) is not str or _ID.fullmatch(value) is None:_error(code)
    return value

def _text(value,code='instagram_invalid_response',*,caption=False):
    if type(value) is not str or '\x00' in value or (not caption and not value.strip()):_error(code)
    try:value.encode('utf-8')
    except UnicodeError:_error(code)
    if len(value)>(2200 if caption else 2000):_error(code)
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


# 공식 호스트 확인은 공개성 증명이 아니다. 루트·로그인 경로 등의 게시물 정체성은 후속 서비스가 검증한다.
def _url(value,*,permalink=False):
    code='instagram_invalid_response' if permalink else 'instagram_invalid_request'
    value=_text(value,code)
    if any(char.isspace() or ord(char)<=32 or 127<=ord(char)<=159 for char in value):_error(code)
    # URL 디코딩 전후 모두 검사한다. UTF-8 C1 및 ASCII 제어문자의 percent 표현도 차단한다.
    try:decoded=unquote(value,encoding='utf-8',errors='strict')
    except UnicodeError:_error(code)
    if any(ord(char)<32 or 127<=ord(char)<=159 for char in decoded):_error(code)
    invalid=False
    try:
        parsed=urlsplit(value);host=parsed.hostname
        if (parsed.scheme!='https' or not host or parsed.netloc!=host or parsed.username is not None
                or parsed.password is not None or parsed.port is not None or parsed.query or parsed.fragment):invalid=True
        if permalink:
            if host not in ('instagram.com','www.instagram.com'):invalid=True
        else:
            if not host or len(host)>253 or '.' not in host or host.endswith('.') or host.rsplit('.',1)[-1].isdigit():invalid=True
            elif any(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',label) is None for label in host.split('.')):invalid=True
            elif host.rsplit('.',1)[-1] in ('localhost','local','internal','test','invalid','example','onion'):invalid=True
            try:ipaddress.ip_address(host);invalid=True
            except ValueError:pass
    except (ValueError,TypeError):invalid=True
    if invalid:_error(code)
    return value

def _supported(value,allowed):
    # 공식 전체 enum을 단정하지 않는다. 현재 제작·검증 경로의 내부 지원 범위다.
    value=_text(value)
    if value not in allowed:_error('instagram_invalid_response')
    return value

def _time(value):
    value=_text(value);invalid=False
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        if dt.tzinfo is None or dt.utcoffset() is None:invalid=True
    except (ValueError,OverflowError):invalid=True
    if invalid:_error('instagram_invalid_response')
    return value

class InstagramApiClient:
    __slots__=('_access_token','_api_version','_transport')
    def __init__(self,access_token,*,api_version,login_mode='facebook_login',transport=None):
        if (type(access_token) is not str or re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,16384}',access_token) is None
                or type(api_version) is not str or _VERSION.fullmatch(api_version) is None
                or login_mode!='facebook_login' or transport is not None and not callable(transport)):
            _error('instagram_invalid_request')
        self._access_token,self._api_version,self._transport=access_token,api_version,transport
    def __repr__(self):return '<InstagramApiClient private>'
    def _send(self,method,path,form=None):
        if self._transport is None:_error('instagram_transport_unregistered')
        headers={'Accept':'application/json','Authorization':'Bearer '+self._access_token};body=None
        if form is not None:
            headers['Content-Type']='application/x-www-form-urlencoded'
            body=urlencode(form,encoding='utf-8',errors='strict').encode('ascii')
        failed=False
        try:response=self._transport(method,'/'+self._api_version+path,headers,body)
        except Exception:failed=True
        if failed:_error('instagram_api_unavailable')
        if (type(response) is not tuple or len(response)!=2 or type(response[0]) is not int
                or type(response[1]) is not bytes):_error('instagram_invalid_response')
        status,raw=response
        if not 200<=status<300:_error('instagram_api_unavailable')
        if len(raw)>_MAX_BYTES:_error('instagram_invalid_response')
        failed=False
        try:
            row=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=_constant,parse_float=_float);_unicode(row)
        except (ValueError,UnicodeError,RecursionError):failed=True
        if failed or type(row) is not dict:_error('instagram_invalid_response')
        if 'error' in row:_error('instagram_api_unavailable')
        return row
    def _create(self,account_id,form):
        row=self._send('POST','/'+_id(account_id)+'/media',form)
        return {'id':_id(row.get('id'),'instagram_invalid_response')}
    def inspect_account(self,account_id):
        account_id=_id(account_id);row=self._send('GET','/'+account_id+'?'+urlencode({'fields':'id,username'}))
        if row.get('id')!=account_id:_error('instagram_invalid_response')
        # 숫자 identity만 관측한다. 계정 유형·소유권·권한의 증거가 아니다.
        return {'id':account_id,'username':_text(row.get('username'))}
    def create_image(self,account_id,image_url,caption):
        return self._create(account_id,{'image_url':_url(image_url),'caption':_text(caption,'instagram_invalid_request',caption=True)})
    def create_reels(self,account_id,video_url,caption):
        return self._create(account_id,{'media_type':'REELS','video_url':_url(video_url),'caption':_text(caption,'instagram_invalid_request',caption=True)})
    def create_carousel_item(self,account_id,*,image_url=None,video_url=None):
        if (image_url is None)==(video_url is None):_error('instagram_invalid_request')
        form={'is_carousel_item':'true'}
        if image_url is not None:form['image_url']=_url(image_url)
        else:form.update(media_type='VIDEO',video_url=_url(video_url))
        return self._create(account_id,form)
    def create_carousel(self,account_id,children,caption):
        if type(children) not in (list,tuple) or not 2<=len(children)<=10:_error('instagram_invalid_request')
        children=[_id(child) for child in children]
        if len(set(children))!=len(children):_error('instagram_invalid_request')
        return self._create(account_id,{'media_type':'CAROUSEL','children':json.dumps(children,separators=(',',':')),'caption':_text(caption,'instagram_invalid_request',caption=True)})
    def container_status(self,container_id):
        container_id=_id(container_id);row=self._send('GET','/'+container_id+'?'+urlencode({'fields':'id,status_code'}))
        status=row.get('status_code')
        if row.get('id')!=container_id or type(status) is not str or status not in ('EXPIRED','ERROR','FINISHED','IN_PROGRESS','PUBLISHED'):_error('instagram_invalid_response')
        return {'id':container_id,'status_code':status}
    def publish(self,account_id,creation_id):
        account_id=_id(account_id);creation_id=_id(creation_id)
        row=self._send('POST','/'+account_id+'/media_publish',{'creation_id':creation_id})
        return {'id':_id(row.get('id'),'instagram_invalid_response')}
    def read_media(self,media_id):
        media_id=_id(media_id);row=self._send('GET','/'+media_id+'?'+urlencode({'fields':_FIELDS}))
        if row.get('id')!=media_id or type(row.get('owner')) is not dict:_error('instagram_invalid_response')
        return dict(id=media_id,owner={'id':_id(row['owner'].get('id'),'instagram_invalid_response')},
                    caption=_text(row.get('caption'),caption=True),media_type=_supported(row.get('media_type'),('IMAGE','VIDEO','CAROUSEL_ALBUM')),
                    media_product_type=_supported(row.get('media_product_type'),('FEED','REELS')),timestamp=_time(row.get('timestamp')),
                    permalink=_url(row.get('permalink'),permalink=True))
    def read_children(self,media_id):
        media_id=_id(media_id);row=self._send('GET','/'+media_id+'/children?'+urlencode({'fields':'id,media_type'}))
        data=row.get('data');paging=row.get('paging',{})
        if type(data) is not list or not 2<=len(data)<=10 or type(paging) is not dict or 'next' in paging:_error('instagram_invalid_response')
        children=[]
        for child in data:
            if type(child) is not dict:_error('instagram_invalid_response')
            children.append({'id':_id(child.get('id'),'instagram_invalid_response'),'media_type':_supported(child.get('media_type'),('IMAGE','VIDEO'))})
        if len({child['id'] for child in children})!=len(children):_error('instagram_invalid_response')
        return children
