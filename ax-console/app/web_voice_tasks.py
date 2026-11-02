"""로컬 음성 작업 HTTP 경계. 프로필·경로·실행 정책은 서버가 주입한다."""
import re
from common.operations.content_store import StoreError,ConflictError
from common.operations.models import ContractError
from web_content import CONTENT_ID
CAPABILITIES='/api/v2/voicebox/capabilities'
CONTENT=re.compile('/api/v2/contents/('+CONTENT_ID+')/voice-tasks')
TASK=re.compile(r'/api/v2/voice-tasks/([A-Za-z0-9_-]{1,100})(/resume)?')
FIELDS=('task_id','state','reason_code','content_id','input_revision','output_revision','asset_id','seconds','review_status','voice_label','generation_id')
STATES={'started','pending','audio_ready','completed','failed','unknown','content_changed'}
REASONS={'voicebox_disabled','voicebox_unavailable','voicebox_generation_unknown','voicebox_generation_failed','voicebox_poll_timeout','voicebox_audio_invalid','voicebox_invalid_response','voicebox_task_unknown','content_changed','duration_exceeded','storage_error','audio_probe_failed','unknown','voicebox_task_error','voicebox_request_unknown','voicebox_probe_failed','voicebox_duration_invalid','voicebox_artifact_conflict','voicebox_artifact_invalid','voicebox_ingest_rejected'}
def recognizes(path):return isinstance(path,str) and (path==CAPABILITIES or CONTENT.fullmatch(path) is not None or TASK.fullmatch(path) is not None)
def public(task):
    if not isinstance(task,dict) or task.get('state') not in STATES:raise StoreError('storage_error')
    result={k:task[k] for k in FIELDS if k in task}
    if result.get('reason_code') not in REASONS and result.get('reason_code') is not None:result['reason_code']='voicebox_task_error'
    result['review_status']='not_checked'
    return result

def handle(store,service,method,path,query,read_body):
    enabled=service is not None and getattr(service,'enabled',False) is True
    if path==CAPABILITIES and method=='GET':
        if query:raise StoreError('invalid')
        return dict(provider_id='voicebox-local',service_available=service is not None,execution_enabled=enabled,readiness='not_checked',external_fallback=False)
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
    fields={'expected_revision','script','seed'} if content else set()
    if not isinstance(body,dict) or set(body)!=fields:raise StoreError('invalid')
    if not enabled:raise StoreError('storage_error')
    try:
        result=service.create(content.group(1),body['expected_revision'],body['script'],body['seed']) if content else service.resume(task.group(1))
    except ContractError as error:
        if error.code in ('invalid','invalid_request','invalid_voice_request','invalid_task'):raise StoreError('invalid') from None
        if error.code in ('content_revision_conflict','voice_task_conflict'):raise ConflictError() from None
        if error.code in ('content_not_found','task_not_found'):raise StoreError('not_found') from None
        raise StoreError('storage_error') from None
    return public(result)
