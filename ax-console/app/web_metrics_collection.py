"""서버 검증 배포 ID에 한정한 명시 성과 수집 HTTP 경계."""
from common.operations.content_store import StoreError,ConflictError
from web_metrics import _public_observation
BASE='/api/v2/metrics'
ROUTES=(BASE+'/collection-targets',BASE+'/collect')
def recognizes(path):return path in ROUTES

def handle(service,method,path,query,read_body):
    if path==ROUTES[0] and method=='GET':
        if set(query)-{'account'} or ('account' in query and (len(query['account'])!=1 or query['account'][0] not in ('all','personal','dept'))):raise StoreError('invalid')
        account=query.get('account',['all'])[0]
        return dict(account_id=account,execution_enabled=service is not None and service.enabled is True,
                    items=service.targets(account) if service is not None else [])
    if path==ROUTES[1] and method=='POST':
        if query:raise StoreError('invalid')
        body=read_body()
        if not isinstance(body,dict) or set(body)!={'delivery_id'} or not isinstance(body['delivery_id'],str) or not 1<=len(body['delivery_id'])<=200:raise StoreError('invalid')
        if service is None or service.enabled is not True:raise StoreError('storage_error')
        try:return dict(observation=_public_observation(service.collect(body['delivery_id'])))
        except StoreError as exc:
            if exc.code in ('delivery_not_verified','metrics_context_changed','metrics_identity_mismatch'):raise ConflictError() from None
            raise
    return None
