"""명시적 활성화와 비용 허가가 모두 필요한 X HTTPS 전송.

공식 경로/호스트/Bearer/JSON: https://docs.x.com/x-api/posts/create-post
https://docs.x.com/x-api/users/get-my-user
https://docs.x.com/x-api/posts/get-post-by-id
OAuth2 사용자 토큰의 실제 scope/주체 확인은 상위 서비스 책임이다.
"""
import http.client
import re
from common.operations.models import ContractError
from common.publishers.x_client import MAX_BYTES,ME_PATH,POST_FIELDS,_json,_text,_TOKEN


def _invalid():raise ContractError('x_invalid_request') from None


def _check(method,path,headers,body):
    if type(path) is not str or type(headers) is not dict or method not in ('GET','POST'):_invalid()
    keys={'Accept','Authorization'}|({'Content-Type'} if method=='POST' else set())
    if set(headers)!=keys or headers.get('Accept')!='application/json':_invalid()
    auth=headers.get('Authorization')
    if type(auth) is not str or not auth.startswith('Bearer ') or not _TOKEN.fullmatch(auth[7:]):_invalid()
    if method=='GET':
        if body is not None or not (path==ME_PATH or re.fullmatch(r'/2/tweets/[0-9]{1,64}'+re.escape(POST_FIELDS),path)):_invalid()
    else:
        if path!='/2/tweets' or headers.get('Content-Type')!='application/json':_invalid()
        try:
            data=_json(body)
            if type(data) is not dict or set(data)!={'text'}:_invalid()
            text=_text(data['text'],'x_invalid_request')
        except ContractError:_invalid()
        token=auth[7:]
        if text==token or len(token)>=16 and token in text:_invalid()
    return dict(headers)


class XHttpsTransport:
    __slots__=('_active','_cost_authorized','_connection_factory')
    def __init__(self,*,activate=False,cost_authorized=False,connection_factory=http.client.HTTPSConnection):
        if type(activate) is not bool or type(cost_authorized) is not bool or not callable(connection_factory):_invalid()
        self._active,self._cost_authorized,self._connection_factory=activate,cost_authorized,connection_factory
    def __repr__(self):return '<XHttpsTransport private>'
    def __call__(self,method,path,headers,body):
        if not self._active:raise ContractError('x_transport_unregistered')
        if not self._cost_authorized:raise ContractError('x_cost_authorization_required')
        safe=_check(method,path,headers,body);connection=None;failure=None;result=None
        try:
            connection=self._connection_factory('api.x.com',port=443,timeout=30)
            connection.debuglevel=0
            connection.request(method,path,headers=safe,body=body)
            response=connection.getresponse()
            if type(response.status) is not int or not 200<=response.status<300:failure='x_api_unavailable'
            else:
                raw=response.read(MAX_BYTES+1)
                if type(raw) is not bytes or len(raw)>MAX_BYTES:failure='x_invalid_response'
                else:result=(response.status,raw)
        except Exception:failure='x_api_unavailable'
        finally:
            if connection is not None:
                try:connection.close()
                except Exception:pass
        if failure:raise ContractError(failure) from None
        return result
