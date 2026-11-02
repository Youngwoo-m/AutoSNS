"""숏츠 제작 작업의 HTTP 경계. 실행 명령·경로·검사기는 서버만 등록한다."""
import re
from common.operations.content_store import StoreError, ConflictError
from common.operations.models import ContractError
from common.operations.video_tasks import SAFE_REASONS
from web_content import CONTENT_ID

CAPABILITIES='/api/v2/video/capabilities'
CONTENT=re.compile('/api/v2/contents/('+CONTENT_ID+')/video-tasks')
TASK=re.compile(r'/api/v2/video-tasks/([A-Za-z0-9_-]{1,100})(/resume)?')
FIELDS=('task_id','state','reason_code','content_id','input_revision','plan_revision','output_revision','asset_id','review_status')
STATES={'queued','preparing','rendering','rendered','completed','blocked','failed','unknown','content_changed'}
REASONS=SAFE_REASONS | {'video_task_error'}

def recognizes(path):
    return isinstance(path,str) and (path==CAPABILITIES or CONTENT.fullmatch(path) is not None or TASK.fullmatch(path) is not None)

def public(row):
    if not isinstance(row,dict) or row.get('state') not in STATES or not all(key in row for key in FIELDS):
        raise StoreError('storage_error')
    value={key:row[key] for key in FIELDS}
    if value['reason_code'] is not None and value['reason_code'] not in REASONS:
        value['reason_code']='video_task_error'
    value['review_status']='not_checked'
    return value

def handle(store,service,method,path,query,read_body):
    enabled=service is not None and getattr(service,'enabled',False) is True and callable(getattr(service,'runner_factory',None))
    if path==CAPABILITIES and method=='GET':
        if query:raise StoreError('invalid')
        return dict(provider_id='remotion-local',service_available=service is not None,execution_enabled=enabled,review_status='not_checked')
    content=CONTENT.fullmatch(path);task=TASK.fullmatch(path)
    if content and method=='GET':
        if (set(query)-{'revision'} or any(len(v)!=1 for v in query.values()) or
            ('revision' in query and not re.fullmatch(r'[1-9][0-9]{0,9}',query['revision'][0]))):raise StoreError('invalid')
        revision=int(query['revision'][0]) if 'revision' in query else None
        return dict(items=[public(row) for row in store.list_for_content(content.group(1),revision)] if store else [])
    if task and not task.group(2) and method=='GET':
        if query:raise StoreError('invalid')
        found=store.get(task.group(1)) if store else None
        if found is None:raise StoreError('not_found')
        return public(found)
    if method!='POST' or not (content or task and task.group(2)):return None
    if query:raise StoreError('invalid')
    body=read_body()
    fields={'expected_revision','expected_plan_revision'} if content else set()
    if not isinstance(body,dict) or set(body)!=fields:raise StoreError('invalid')
    if not enabled:raise StoreError('storage_error')
    try:
        result=service.create(content.group(1),body['expected_revision'],body['expected_plan_revision']) if content else service.resume(task.group(1))
    except ContractError as error:
        if error.code in ('invalid','invalid_video_request','invalid_task'):raise StoreError('invalid') from None
        if error.code in ('content_revision_conflict','video_task_conflict','video_plan_conflict','plan_revision_conflict','media_inputs_required'):
            raise ConflictError() from None
        if error.code in ('content_not_found','task_not_found','media_plan_not_found'):raise StoreError('not_found') from None
        raise StoreError('storage_error') from None
    return public(result)
