"""음성 프로필 선호 저장은 다음 명시 기동 준비이며 합성이 아니다."""
import re
from common.operations.content_store import StoreError
ROUTE=re.compile(r'/api/v2/accounts/(personal|dept)/voice-settings')
def recognizes(path):return isinstance(path,str) and ROUTE.fullmatch(path) is not None

def handle(store,method,path,query,read_body):
    match=ROUTE.fullmatch(path)
    if not match or method not in ('GET','POST'):return None
    if query:raise StoreError('invalid')
    account=match.group(1)
    if method=='GET':
        return store.get(account) if store else dict(account_id=account,revision=0,enabled_preference=False,profile_id=None,applies_to='next_startup',execution_enabled=False)
    body=read_body()
    if not isinstance(body,dict) or set(body)!={'expected_revision','settings'}:raise StoreError('invalid')
    if store is None:raise StoreError('storage_error')
    return store.save(account,body['expected_revision'],body['settings'])
