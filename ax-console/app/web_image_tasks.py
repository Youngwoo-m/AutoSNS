"""명시 로컬 카드 제작 요청. 계정·실행기·경로는 서버만 결정한다."""
import re
from common.operations.content_store import StoreError,ConflictError
from common.operations.models import ContractError
from web_content import CONTENT_ID
CAPABILITIES='/api/v2/capabilities/image-production'
CONTENT=re.compile('/api/v2/contents/('+CONTENT_ID+')/image-tasks')
TASK=re.compile(r'/api/v2/image-tasks/([A-Za-z0-9_-]{1,100})/resume')
FIELDS=('task_id','state','reason_code','content_id','input_revision','output_revision','asset_id','review_status')
STATES={'started','unknown','rendered','completed','failed','content_changed'}
def recognizes(path):return isinstance(path,str) and (path==CAPABILITIES or CONTENT.fullmatch(path) is not None or TASK.fullmatch(path) is not None)
def public(row):
    if not isinstance(row,dict) or row.get('state') not in STATES or any(k not in row for k in FIELDS):raise StoreError('storage_error')
    result={key:row[key] for key in FIELDS}
    allowed={'image_disabled','image_unavailable','image_render_unknown','image_result_invalid','image_output_invalid','image_artifact_invalid','image_storage_error','image_ingest_rejected','content_changed','storage_error',None}
    if result['reason_code'] not in allowed:result['reason_code']='image_result_invalid'
    result['review_status']='not_checked'
    return result

def handle(store,service,method,path,query,read_body):
    capability=service.capabilities() if service is not None else dict(provider_id='local-card',service_available=False,execution_enabled=False,review_status='not_checked')
    enabled=service is not None and capability.get('execution_enabled') is True
    if path==CAPABILITIES and method=='GET':
        if query:raise StoreError('invalid')
        return {key:capability[key] for key in ('provider_id','service_available','execution_enabled','review_status')}
    content=CONTENT.fullmatch(path);task=TASK.fullmatch(path)
    if content and method=='GET':
        if (set(query)!={'revision'} or not isinstance(query['revision'],list) or len(query['revision'])!=1
                or not isinstance(query['revision'][0],str) or not re.fullmatch('[1-9][0-9]{0,9}',query['revision'][0])):raise StoreError('invalid')
        revision=int(query['revision'][0])
        try:return dict(items=[public(row) for row in store.list_for_content(content.group(1)) if row['input_revision']==revision] if store else [])
        except ContractError:raise StoreError('storage_error') from None
    if method!='POST' or not (content or task):return None
    if query:raise StoreError('invalid')
    body=read_body()
    if not isinstance(body,dict) or set(body)!=({'expected_revision','spec'} if content else set()):raise StoreError('invalid')
    if not enabled:raise StoreError('storage_error')
    try:
        row=service.create(content.group(1),body['expected_revision'],body['spec']) if content else service.resume(task.group(1))
    except ContractError as error:
        if error.code in ('invalid_image_spec','invalid_image_request','invalid_task','invalid'):raise StoreError('invalid') from None
        if error.code in ('content_revision_conflict','image_task_conflict','image_task_busy'):raise ConflictError() from None
        if error.code in ('content_not_found','task_not_found','image_content_not_found','image_task_not_found'):raise StoreError('not_found') from None
        raise StoreError('storage_error') from None
    return public(row)
