"""로컬 배포 API의 엄격한 요청 경계. 등록부·실행 컨텍스트는 서버만 구성한다."""
import re
from common.operations.content_store import StoreError

DELIVERY_ID=r'delivery_[0-9a-f]{32}'

def fields(body,required):
    if not isinstance(body,dict) or set(body)!=set(required): raise StoreError('invalid')
    return body


def handle(ledger,method,path,query,read_body):
    if path=='/api/v2/connections':
        if method!='GET': return None
        return {'items':ledger.connections()}
    base='/api/v2/deliveries'
    if path==base:
        if method=='GET': return {'items':ledger.list_deliveries(query.get('account',['all'])[0],query.get('content_id',[None])[0])}
        if method=='POST': return ledger.create_or_get_delivery(read_body())
        return None
    if path==base+'/preview':
        return ledger.preview_delivery(read_body()) if method=='POST' else None
    match=re.fullmatch(base+'/('+DELIVERY_ID+')(?:/(events|approvals|schedule-preview|schedule|cancel))?',path)
    if not match: raise StoreError('not_found')
    id,suffix=match.groups()
    if suffix is None and method=='GET':
        result=ledger.get_delivery(id)
        if result is None: raise StoreError('not_found')
        return result
    if suffix=='events' and method=='GET': return {'items':ledger.events(id)}
    if suffix=='approvals' and method=='POST':
        body=fields(read_body(),('expected_version','subject_hash','decision','notes'))
        return ledger.record_approval(id,body['expected_version'],body['subject_hash'],body['decision'],body['notes'])
    if suffix in ('schedule-preview','schedule') and method==('POST' if suffix=='schedule-preview' else 'PUT'):
        names=['expected_version','scheduled_at','timezone']+(['preview_hash'] if suffix=='schedule' else [])
        body=fields(read_body(),names)
        args=(id,body['expected_version'],body['scheduled_at'],body['timezone'])
        return ledger.preview_schedule(*args) if suffix=='schedule-preview' else ledger.reschedule(*args,body['preview_hash'])
    if suffix=='cancel' and method=='POST':
        body=fields(read_body(),('expected_version',))
        return ledger.cancel(id,body['expected_version'])
    return None
