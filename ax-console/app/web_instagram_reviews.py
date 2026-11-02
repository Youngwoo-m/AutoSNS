"""저장된 Instagram 계획의 수동 구성 검토. 계정·대상·기록자는 서버가 결속한다."""
import re
from collections.abc import Mapping
from common.operations.content_store import StoreError,ConflictError
from common.operations.models import ContractError
from web_deliveries import DELIVERY_ID

ROUTE=re.compile('/api/v2/deliveries/('+DELIVERY_ID+')/instagram-review')
FIELDS=frozenset(('plan_id','content_id','content_revision','manifest_hash','owner_account_id',
    'destination_account_id','connection_id','target_id','media_format','caption','assets','subject_hash',
    'review_revision','decision','checks','notes','review_method','status','audio_required'))
CHECKS=frozenset(('rights_confirmed','visual_checked','caption_checked','composition_checked','audio_checked'))
ASSET_FIELDS=('id','sha256','size','media_type')

def recognizes(path):return type(path) is str and ROUTE.fullmatch(path) is not None

def public(row):
    if (not isinstance(row,Mapping) or not FIELDS<=set(row) or row['review_method']!='manual'
            or row['status'] not in ('not_reviewed','approved','revoked')
            or not isinstance(row['checks'],Mapping) or set(row['checks'])!=CHECKS
            or any(type(value) is not bool for value in row['checks'].values())
            or not isinstance(row['assets'],(list,tuple))
            or any(not isinstance(asset,Mapping) or not set(ASSET_FIELDS)<=set(asset) for asset in row['assets'])):
        raise StoreError('storage_error')
    result={key:row[key] for key in FIELDS}
    result['checks']=dict(row['checks'])
    result['assets']=[{key:asset[key] for key in ASSET_FIELDS} for asset in row['assets']]
    return result

def handle(service,method,path,query,read_body):
    match=ROUTE.fullmatch(path)
    if match is None or method not in ('GET','POST'):return None
    if query:raise StoreError('invalid')
    if service is None:raise StoreError('storage_error')
    try:
        if method=='GET':return public(service.get(match.group(1)))
        body=read_body()
        if type(body) is not dict or set(body)!={'expected_review_revision','subject_hash','decision','checks','notes'}:
            raise StoreError('invalid')
        return public(service.record(match.group(1),body,actor='console_user'))
    except ContractError as error:
        if error.code in ('instagram_review_invalid','invalid_instagram_payload','invalid_instagram_caption',
                'invalid_instagram_media_selection','invalid_instagram_asset','instagram_media_selection_required'):
            raise StoreError('invalid') from None
        if error.code in ('instagram_review_conflict','instagram_review_stale','instagram_target_unverified',
                'instagram_asset_changed','content_revision_conflict'):
            raise ConflictError() from None
        if error.code in ('instagram_plan_unavailable','content_not_found','asset_not_found'):
            raise StoreError('not_found') from None
        raise StoreError('storage_error') from None
