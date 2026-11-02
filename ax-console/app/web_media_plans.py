"""버전 고정 숏츠 제작 계획 HTTP 경계. 실제 렌더는 실행하지 않는다."""
import re
from web_content import CONTENT_ID
from common.operations.content_store import StoreError
ROUTE=re.compile('/api/v2/contents/('+CONTENT_ID+')/media-plan')
def recognizes(path):return isinstance(path,str) and ROUTE.fullmatch(path) is not None

def handle(store,method,path,query,read_body):
    match=ROUTE.fullmatch(path)
    if not match or method not in ('GET','POST'):return None
    if (not isinstance(query,dict) or set(query)!={'revision'} or
        not isinstance(query['revision'],list) or len(query['revision'])!=1 or
        not isinstance(query['revision'][0],str) or not re.fullmatch(r'[1-9][0-9]{0,9}',query['revision'][0])):
        raise StoreError('invalid')
    content_id=match.group(1);revision=int(query['revision'][0])
    if method=='GET':
        if store is None:raise StoreError('storage_error')
        return store.get(content_id,revision)
    body=read_body()
    if isinstance(body,dict) and set(body)=={'action','expected_revision','source_revision','source_plan_revision','voice_asset_id'} and body['action']=='import':
        if store is None:raise StoreError('storage_error')
        return store.import_plan(content_id,revision,body['expected_revision'],body['source_revision'],body['source_plan_revision'],body['voice_asset_id'])
    if not isinstance(body,dict) or set(body)!={'expected_revision','plan'}:raise StoreError('invalid')
    if store is None:raise StoreError('storage_error')
    return store.save(content_id,revision,body['expected_revision'],body['plan'])
