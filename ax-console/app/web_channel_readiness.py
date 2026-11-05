"""채널별 로컬 구현·연결 준비 상태만 조회한다."""
from common.operations.channel_readiness import build_channel_readiness
from common.operations.content_store import StoreError
PATH='/api/v2/channels/readiness'
def recognizes(path):return path==PATH

def handle(registry,method,path,query):
    if path!=PATH or method!='GET':return None
    if set(query)-{'account'} or ('account' in query and (len(query['account'])!=1 or query['account'][0] not in ('all','personal','dept'))):raise StoreError('invalid')
    return build_channel_readiness(registry,query.get('account',['all'])[0])
