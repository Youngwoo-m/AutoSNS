"""계정별 전달 현황과 명시 회수. 임대 URL·private authority는 응답하지 않는다."""
import re
from collections.abc import Mapping
from common.operations.content_store import StoreError
from common.operations.models import ContractError
from common.operations.runtime_models import utc

ROUTE='/api/v2/media-leases'
REVOKE=re.compile(ROUTE+r'/([0-9a-f]{64})/revoke')
FIELDS=frozenset(('lease_id','owner_account_id','destination_account_id','connection_id','content_id',
    'content_revision','asset_id','asset_sha256','asset_size','media_type','expires_at','status'))


def recognizes(path):return path==ROUTE or REVOKE.fullmatch(path) is not None


def _account(value):
    if value not in ('personal','dept'):raise StoreError('invalid')
    return value


def _public(store,account,now):
    rows=store.list_status(destination_account_id=account,now=now) if store is not None else []
    items=[]
    for row in rows:
        if (not isinstance(row,Mapping) or not FIELDS<=set(row)
                or row['destination_account_id']!=account or row['owner_account_id'] not in ('personal','dept')
                or row['status'] not in ('active','expired','revoked','purged')
                or row['media_type'] not in ('image/jpeg','video/mp4')
                or type(row['lease_id']) is not str or re.fullmatch('[0-9a-f]{64}',row['lease_id']) is None
                or type(row['asset_sha256']) is not str or re.fullmatch('[0-9a-f]{64}',row['asset_sha256']) is None
                or type(row['content_revision']) is not int or row['content_revision']<1
                or type(row['asset_size']) is not int or row['asset_size']<1
                or any(type(row[k]) is not str or not row[k] or len(row[k])>300 for k in ('content_id','asset_id','connection_id'))):
            raise StoreError('storage_error')
        utc(row['expires_at'])
        items.append({key:row[key] for key in FIELDS})
    return dict(account_id=account,items=items)


def handle(store,method,path,query,read_body,*,now):
    if not recognizes(path):return None
    match=REVOKE.fullmatch(path)
    if path==ROUTE and method!='GET' or match is not None and method!='POST':return None
    try:
        if path==ROUTE:
            if set(query)!={'account'} or len(query['account'])!=1:raise StoreError('invalid')
            account=_account(query['account'][0])
            return _public(store,account,now)
        if query:raise StoreError('invalid')
        body=read_body()
        if type(body) is not dict or set(body)!={'account_id'}:raise StoreError('invalid')
        account=_account(body['account_id'])
        current=_public(store,account,now)
        if not any(row['lease_id']==match.group(1) for row in current['items']):raise StoreError('not_found')
        # 회수 버튼이 명시적인 쓰기다. 목록 조회는 저장소를 초기화하지 않는다.
        store.initialize()
        store.revoke(match.group(1),now=now)
        return _public(store,account,now)
    except ContractError:raise StoreError('storage_error') from None
