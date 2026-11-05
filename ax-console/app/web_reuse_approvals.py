"""이미지 재사용 수동 확인 HTTP 경계. 계정·해시·기록자는 서버가 결속한다."""
import re
from web_content import CONTENT_ID
from common.operations.content_store import StoreError,ConflictError
from common.operations.models import ContractError

CONTENT=re.compile('/api/v2/contents/('+CONTENT_ID+')/reuse-approvals')
FIELDS={'content_id','content_revision','manifest_hash','owner_account_id','asset_id','sha256','approval_revision',
        'approved_revision','rights_confirmed','visual_checked','notes','status','review_method'}

def recognizes(path):return isinstance(path,str) and CONTENT.fullmatch(path) is not None

def public(row):
    if (not isinstance(row,dict) or not FIELDS<=set(row) or row['status'] not in ('approved','not_approved')
        or row['review_method']!='manual'):raise StoreError('storage_error')
    return {key:row[key] for key in FIELDS}

def handle(service,method,path,query,read_body):
    match=CONTENT.fullmatch(path)
    if not match or method not in ('GET','POST'):return None
    if (set(query)!={'revision'} or not isinstance(query['revision'],list) or len(query['revision'])!=1
        or not re.fullmatch(r'[1-9][0-9]{0,9}',query['revision'][0])):raise StoreError('invalid')
    if service is None:raise StoreError('storage_error')
    content_id,revision=match.group(1),int(query['revision'][0])
    try:
        if method=='GET':
            result=service.get_for_content(content_id,revision)
            return dict(items=[public(row) for row in result['items']])
        body=read_body()
        if not isinstance(body,dict) or set(body)!={'asset_id','expected_revision','rights_confirmed','visual_checked','notes'}:
            raise StoreError('invalid')
        return public(service.save(content_id,revision,body['asset_id'],body['expected_revision'],
            body['rights_confirmed'],body['visual_checked'],body['notes'],actor='console_user'))
    except ContractError as error:
        if error.code in ('invalid_reuse_request','invalid'):raise StoreError('invalid') from None
        if error.code in ('reuse_approval_conflict','content_revision_conflict'):raise ConflictError() from None
        if error.code in ('content_not_found','asset_not_found'):raise StoreError('not_found') from None
        raise StoreError('storage_error') from None
