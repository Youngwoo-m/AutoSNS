"""명시 주입된 읽기 transport로만 Google 발행 권한을 확인한다.

Blogger role: https://developers.google.com/resources/api-libraries/documentation/blogger/v3/python/latest/blogger_v3.blogs.html
Blogger principal: https://developers.google.com/blogger/docs/3.0/reference/users/get
YouTube mine: https://developers.google.com/youtube/data/reference/rest/v3/channels/list
YouTube upload scope: https://developers.google.com/youtube/data/reference/rest/v3/videos/insert
can_publish는 현재 대상의 인증·권한 관측만 뜻한다. quota·콘텐츠·앱 정책 수락이나
공개 게시 성공을 보장하지 않는다. isLinked는 업로드의 필요조건이다. YouTube의
provider_subject는 Google 계정 ID가 아닌 기존 OAuth inspect에서 관측한 채널 ID여야 한다.
기본 네트워크·토큰 introspection·쓰기 endpoint·재시도·자동 등록은 없다.
"""
from collections.abc import Mapping
import re
from common.operations.content_store import StoreError
from common.operations.managed_credentials import ResolvedManagedCredential
from common.operations.oauth_catalog import provider_catalog
from common.operations.oauth_models import TokenBundle
from common.operations.publication_grants import PublicationGrantBinding,VerifiedPublicationEvidence
from common.operations.runtime_models import utc


def _deny():raise StoreError('publication_provider_unverified') from None


class GooglePublicationVerifier:
    def __init__(self,provider_id,transport):
        if provider_id not in ('youtube','blogger') or not callable(getattr(transport,'request',None)):_deny()
        self.provider_id=provider_id;self._transport=transport
    def __repr__(self):return 'GooglePublicationVerifier(<private>)'

    def _get(self,resolved,url,params):
        resolved.assert_current()
        try:result=self._transport.request('GET',url,params,{'Authorization':'Bearer '+resolved.bundle.access_token,'Accept':'application/json'})
        except Exception:_deny()
        resolved.assert_current()
        if not isinstance(result,Mapping) or 'error' in result:_deny()
        return result

    def verify(self,resolved,binding,*,now):
        try:
            if type(resolved) is not ResolvedManagedCredential or type(binding) is not PublicationGrantBinding or type(resolved.bundle) is not TokenBundle:_deny()
            if (self.provider_id!=binding.provider_id or resolved.provider_id!=binding.provider_id
                    or any(getattr(resolved,name)!=getattr(binding,name) for name in ('account_id','platform','connection_id','target_id'))
                    or resolved.generation!=binding.credential_generation or resolved.scope!='read'):_deny()
            checked=utc(now);expiry=utc(resolved.bundle.expires_at)
            if expiry<=checked or resolved.bundle.token_type.lower()!='bearer':_deny()
            definition=next(p for p in provider_catalog() if p.id==self.provider_id)
            scopes=tuple(resolved.bundle.scopes)
            if (len(scopes)!=len(set(scopes)) or not set(definition.publication_scopes)<=set(scopes)
                    or not set(scopes)<=set(definition.read_scopes)|set(definition.publication_scopes)):_deny()
            if self.provider_id=='youtube':
                if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',binding.target_id) or binding.provider_subject!=binding.target_id:_deny()
                response=self._get(resolved,'https://www.googleapis.com/youtube/v3/channels',{'part':'id,status','mine':'true','maxResults':50})
                items=response.get('items')
                if (type(items) is not list or len(items)!=1 or response.get('nextPageToken')
                        or not isinstance(items[0],Mapping) or items[0].get('id')!=binding.target_id
                        or not isinstance(items[0].get('status'),Mapping) or items[0]['status'].get('isLinked') is not True):_deny()
                method='google_youtube_mine_upload_scope'
            else:
                if not re.fullmatch(r'[0-9]{1,64}',binding.target_id) or not re.fullmatch(r'[0-9]{1,64}',binding.provider_subject):_deny()
                principal=self._get(resolved,'https://www.googleapis.com/blogger/v3/users/self',{'fields':'id'})
                if principal.get('id')!=binding.provider_subject:_deny()
                response=self._get(resolved,'https://www.googleapis.com/blogger/v3/users/self/blogs/'+binding.target_id,{'maxPosts':0})
                blog=response.get('blog');info=response.get('blog_user_info')
                if (not isinstance(blog,Mapping) or blog.get('id')!=binding.target_id or not isinstance(info,Mapping)
                        or info.get('userId')!=binding.provider_subject or info.get('blogId')!=binding.target_id
                        or info.get('role') not in ('ADMIN','AUTHOR')
                        or info.get('role')=='ADMIN' and info.get('hasAdminAccess') is not True):_deny()
                method='google_blogger_current_user_role'
            resolved.assert_current()
            return VerifiedPublicationEvidence(binding,scopes,checked,expiry,True,method)
        except StoreError:raise
        except Exception:_deny()


class GooglePublicationTransport:
    """고정 읽기 요청만 허용한다. fetch=urllib_fetch는 서버의 별도 명시 등록이다.

    common.oauth.transport.urllib_fetch는 TLS 검증 context를 사용하며 시스템 proxy·
    쿠키·리다이렉트를 차단한다. 이 클래스는 생성자나 기본 fetch=None에서 연결하지 않는다.
    비용·앱 사용 정책 gate는 호출 서비스가 별도로 검사해야 한다.
    """
    def __init__(self,fetch=None,*,timeout=10,max_response_bytes=262144):
        if (fetch is not None and not callable(fetch) or type(timeout) not in (int,float)
                or not 0<timeout<=30 or type(max_response_bytes) is not int or not 0<max_response_bytes<=262144):_deny()
        self._fetch=fetch;self.timeout=timeout;self.max_response_bytes=max_response_bytes
    def __repr__(self):return 'GooglePublicationTransport(<private>)'

    def request(self,method,url,params,headers):
        if method!='GET' or type(params) is not dict or type(headers) is not dict:_deny()
        if url=='https://www.googleapis.com/youtube/v3/channels':
            if params!={'part':'id,status','mine':'true','maxResults':50} or type(params.get('maxResults')) is not int:_deny()
        elif url=='https://www.googleapis.com/blogger/v3/users/self':
            if params!={'fields':'id'}:_deny()
        elif type(url) is str and re.fullmatch(r'https://www\.googleapis\.com/blogger/v3/users/self/blogs/[0-9]{1,64}',url):
            if params!={'maxPosts':0} or type(params.get('maxPosts')) is not int:_deny()
        else:_deny()
        if (set(headers)!={'Authorization','Accept'} or headers['Accept']!='application/json'
                or type(headers['Authorization']) is not str or not headers['Authorization'].startswith('Bearer ')
                or not headers['Authorization'][7:] or any(ord(c)<33 or ord(c)>126 for c in headers['Authorization'][7:])):_deny()
        if self._fetch is None:raise StoreError('publication_transport_unconfigured')
        import json
        import ssl
        from urllib.parse import urlencode
        from urllib.request import Request
        def unique(pairs):
            value={}
            for key,item in pairs:
                if key in value:raise ValueError()
                value[key]=item
            return value
        def safe(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if re.search(r'(?:access_token|refresh_token|client_secret|authorization|credential)',key,re.I):raise ValueError()
                    safe(item)
            elif isinstance(value,list):
                for item in value:safe(item)
        full_url=url+'?'+urlencode(params);response=None
        try:
            request=Request(full_url,headers=dict(headers),method='GET')
            response=self._fetch(request,timeout=self.timeout,context=ssl.create_default_context())
            if response.status!=200 or response.geturl()!=full_url:_deny()
            raw=response.read(self.max_response_bytes+1)
            if type(raw) is not bytes or not raw or len(raw)>self.max_response_bytes:_deny()
            value=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,parse_constant=lambda value:(_ for _ in ()).throw(ValueError()))
            if type(value) is not dict or 'error' in value:_deny()
            safe(value)
            return value
        except Exception:raise StoreError('publication_transport_failed') from None
        finally:
            if response is not None:
                try:response.close()
                except Exception:pass
