"""TikTok 로컬 준비물 조회와 명시 기술 검사. 업로드/게시 경로가 아니다."""
import re
from common.operations.content_store import StoreError
from web_deliveries import DELIVERY_ID

ROUTE=re.compile('/api/v2/deliveries/('+DELIVERY_ID+')/tiktok-preparation(/check)?')
FIELDS=frozenset(('plan_id','owner_account_id','destination_account_id','connection_id','content_id','content_revision',
    'manifest_hash','caption','caption_sha256','asset','asset_url','preparation_hash','status','publication_enabled',
    'technical_check_available','technical_check'))


def recognizes(path):return type(path) is str and ROUTE.fullmatch(path) is not None


def handle(service,method,path,query,read_body):
    match=ROUTE.fullmatch(path)
    if match is None:return None
    if (match.group(2) is None and method!='GET') or (match.group(2) is not None and method!='POST'):return None
    if query:raise StoreError('invalid')
    if service is None:raise StoreError('storage_error')
    value=service.get(match.group(1)) if match.group(2) is None else service.check(match.group(1),read_body())
    if (type(value) is not dict or set(value)!=FIELDS or value['status']!='local_preparation_only'
            or value['publication_enabled'] is not False):raise StoreError('storage_error')
    return value
