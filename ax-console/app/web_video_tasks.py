"""숏츠 제작 작업의 HTTP 경계. 실행 명령·경로·검사기는 서버만 등록한다."""
import re
from dataclasses import dataclass
from common.operations.content_store import StoreError, ConflictError
from common.operations.models import ContractError
from common.operations.video_tasks import SAFE_REASONS
from web_content import CONTENT_ID

CAPABILITIES='/api/v2/video/capabilities'
CONTENT=re.compile('/api/v2/contents/('+CONTENT_ID+')/video-tasks')
TASK=re.compile(r'/api/v2/video-tasks/([A-Za-z0-9_-]{1,100})(/resume|/review|/preview)?')
FIELDS=('task_id','state','reason_code','content_id','input_revision','plan_revision','output_revision','asset_id','review_status')
STATES={'queued','preparing','rendering','awaiting_review','rendered','completed','blocked','failed','unknown','content_changed'}
REASONS=SAFE_REASONS | {'video_task_error'}

@dataclass(frozen=True)
class VideoPreview:
    raw: bytes

def preview_response(preview,range_header=None):
    raw=preview.raw;size=len(raw);headers={'Accept-Ranges':'bytes','Content-Disposition':'inline; filename="short.mp4"'}
    if range_header is None:return 200,raw,headers
    match=re.fullmatch(r'bytes=([0-9]{0,18})-([0-9]{0,18})',range_header)
    if not match or not any(match.groups()):return 416,b'',{**headers,'Content-Range':f'bytes */{size}'}
    first,last=match.groups()
    if not first:
        count=int(last)
        if count<1:return 416,b'',{**headers,'Content-Range':f'bytes */{size}'}
        start,end=max(0,size-count),size-1
    else:
        start=int(first);end=min(int(last),size-1) if last else size-1
    if start>=size or end<start:return 416,b'',{**headers,'Content-Range':f'bytes */{size}'}
    return 206,raw[start:end+1],{**headers,'Content-Range':f'bytes {start}-{end}/{size}'}

def public_review(value,task_id):
    keys={'task_id','state','content_id','input_revision','plan_revision','context_fingerprint','scene_count','media','manifest','review_status'}
    if (not isinstance(value,dict) or set(value)!=keys or value.get('task_id')!=task_id or value.get('state')!='awaiting_review'
        or value.get('review_status')!='not_checked' or not isinstance(value.get('context_fingerprint'),str)
        or not re.fullmatch(r'[0-9a-f]{64}',value['context_fingerprint'])):raise StoreError('storage_error')
    media=value['media'];manifest=value['manifest']
    if (not isinstance(media,dict) or set(media)!={'filename','media_type','size','sha256','seconds','width','height','has_audio'}
        or media.get('filename')!='short.mp4' or media.get('media_type')!='video/mp4'
        or not isinstance(manifest,dict) or set(manifest)!={'exam','field','source','footer','disclosure','scenes'}
        or not all(isinstance(manifest[k],str) for k in ('exam','field','source','footer','disclosure'))
        or not isinstance(manifest['scenes'],list) or type(value['scene_count']) is not int
        or value['scene_count']!=len(manifest['scenes'])):raise StoreError('storage_error')
    for index,scene in enumerate(manifest['scenes'],1):
        if (not isinstance(scene,dict) or set(scene)!={'index','kind','seconds','title','caption'}
            or scene['index']!=index or not all(isinstance(scene[k],str) for k in ('kind','title','caption'))):
            raise StoreError('storage_error')
    return value

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
    action=task.group(2) if task else None
    if task and action in ('/review','/preview') and method=='GET':
        if query:raise StoreError('invalid')
        if service is None:raise StoreError('storage_error')
        try:
            if action=='/review':return public_review(service.review_context(task.group(1)),task.group(1))
            metadata,raw=service.review_video(task.group(1))
            if not isinstance(raw,bytes) or not 12<=len(raw)<=100*1024*1024 or raw[4:8]!=b'ftyp':raise StoreError('storage_error')
            return VideoPreview(raw)
        except ContractError as error:
            if error.code in ('task_not_found','content_not_found'):raise StoreError('not_found') from None
            if error.code in ('video_review_conflict','review_not_available','video_review_unavailable','video_review_stale','content_changed','plan_changed','content_revision_conflict'):raise ConflictError() from None
            raise StoreError('storage_error') from None
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
    fields={'expected_revision','expected_plan_revision'} if content else {'context_fingerprint','decision','checks','notes'} if action=='/review' else set()
    if action=='/preview':return None
    if not isinstance(body,dict) or set(body)!=fields:raise StoreError('invalid')
    if not enabled:raise StoreError('storage_error')
    try:
        if content:result=service.create(content.group(1),body['expected_revision'],body['expected_plan_revision'])
        elif action=='/review':result=service.confirm_review(task.group(1),body['context_fingerprint'],body['decision'],body['checks'],body['notes'],actor='console_user')
        else:result=service.resume(task.group(1))
    except ContractError as error:
        if error.code in ('invalid','invalid_video_request','invalid_task','invalid_video_review','invalid_review'):raise StoreError('invalid') from None
        if error.code in ('content_revision_conflict','video_task_conflict','video_plan_conflict','plan_revision_conflict','media_inputs_required',
                          'video_review_conflict','review_not_available','video_review_unavailable','video_review_stale','content_changed','plan_changed','video_worker_busy'):
            raise ConflictError() from None
        if error.code in ('content_not_found','task_not_found','media_plan_not_found'):raise StoreError('not_found') from None
        raise StoreError('storage_error') from None
    return public(result)
