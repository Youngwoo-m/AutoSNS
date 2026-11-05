"""계정별 제작 준비 설정의 정확한 HTTP 계약. 실행/한도 관측은 하지 않는다."""
from common.operations.content_store import StoreError
BASE='/api/v2/production/settings'
def recognizes(path):
    return isinstance(path,str) and path==BASE

def handle(store,method,path,query,read_body):
    if not recognizes(path):return None
    if method not in ('GET','POST'):return None
    if (not isinstance(query,dict) or set(query)!={'account'} or
            not isinstance(query['account'],list) or len(query['account'])!=1 or
            query['account'][0] not in ('personal','dept')):
        raise StoreError('invalid')
    account=query['account'][0]
    if method=='GET':
        if store is not None:return store.get(account)
        return dict(account_id=account,revision=0,enabled_preference=False,daily_limit=None,
                    applies_to='next_startup',execution_enabled=False)
    body=read_body()
    if not isinstance(body,dict) or set(body)!={'expected_revision','enabled_preference','daily_limit'}:
        raise StoreError('invalid')
    if store is None:raise StoreError('storage_error')
    return store.save(account,body['expected_revision'],{k:body[k] for k in ('enabled_preference','daily_limit')})
