"""로컬 도구의 정확한 경로/요청 경계. HTTP 서버와 실행기는 이 모듈이 조립하지 않는다."""
from common.operations.content_store import StoreError

BASE='/api/v2/tools/'
POST_ROUTES={
    'packaging-preview':'packaging_preview', 'research-preview':'research_preview',
    'thumbnail-inspect':'thumbnail_inspect', 'thumbnail-render':'thumbnail_render',
    'metrics-csv-preview':'csv_preview', 'metrics-csv-import':'csv_import',
    'schedule-inspect':'schedule_inspect',
}
ROUTES=frozenset([BASE+'capabilities',*(BASE+name for name in POST_ROUTES)])


def recognizes(path):
    return type(path) is str and path in ROUTES


def handle(service, method, path, query, read_body):
    if not recognizes(path): return None
    if type(query) is not dict: raise StoreError('invalid')
    if path==BASE+'capabilities' and method=='GET':
        if set(query)-{'account'} or any(type(values) is not list or len(values)!=1 for values in query.values()):
            raise StoreError('invalid')
        account=query.get('account',['all'])[0]
        if type(account) is not str or account not in ('all','personal','dept'): raise StoreError('invalid')
        if service is None:
            return dict(account_id=account,toolkit_enabled=False,external_execution_supported=False,items=[],connections=[])
        return service.capabilities(account)
    if query: raise StoreError('invalid')
    if method=='POST' and path[len(BASE):] in POST_ROUTES:
        if service is None: raise StoreError('storage_error')
        return getattr(service,POST_ROUTES[path[len(BASE):]])(read_body())
    return None
