"""업로드한 원본과 변환된 YouTube 공개 영상의 서버 영수증 결속.

원격 변환 영상의 바이트 해시를 원본 해시라고 주장하지 않는다. 이 검증기는 신뢰된
저장소가 읽은 승인 snapshot과 실제 업로드 경계가 기록한 attempt 영수증을 전제로 하며,
공개 읽기 관측의 불변 영상/채널 ID·메타데이터·처리 완료를 함께 확인한다. 순수 함수다.
"""
from collections.abc import Mapping
import hashlib
from .runtime_models import PublicationContext,utc
from .models import ContractError

UPLOAD_RECEIPT_KEYS=frozenset(('kind','connection_id','target_id','remote_id','owner_account_id',
    'destination_account_id','content_id','content_revision','manifest_hash','asset_id','asset_sha256',
    'asset_size','title_sha256','description_sha256'))


def _sha(text):
    if not isinstance(text,str):raise ValueError('invalid metadata')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def youtube_upload_identity(context,snapshot,candidate,attempt,now,remote_id):
    """검증된 업로드 영수증 + 공개 관측일 때만 True. 원격 해시를 만들지 않는다."""
    from common.publishers.youtube_payloads import build_youtube_payload
    try:
        if isinstance(context,Mapping):context=PublicationContext(**dict(context))
        if not isinstance(context,PublicationContext) or context.platform!='youtube':return False
        if (not isinstance(snapshot,Mapping) or snapshot.get('id')!=context.content_id
                or snapshot.get('owner_account_id')!=context.owner_account_id
                or not isinstance(candidate,Mapping) or not isinstance(attempt,Mapping)
                or not isinstance(remote_id,str) or not remote_id):return False
        if (type(attempt.get('request_started')) not in (bool,int) or attempt['request_started']!=1
                or attempt.get('context_hash')!=context.context_hash
                or attempt.get('outcome') not in ('submitted','scheduled')):return False
        result=attempt.get('result')
        if (not isinstance(result,Mapping) or result.get('outcome')!=attempt['outcome']
                or result.get('remote_id')!=remote_id or not isinstance(result.get('evidence'),Mapping)):return False
        receipt=result['evidence'].get('upload_receipt')
        if (not isinstance(receipt,Mapping) or set(receipt)!=UPLOAD_RECEIPT_KEYS
                or type(receipt.get('content_revision')) is not int or type(receipt.get('asset_size')) is not int):return False
        prepared=build_youtube_payload(snapshot,context,context.options.get('youtube_config',{}))
        asset,snippet=prepared['asset'],prepared['body']['snippet']
        expected=dict(kind='youtube_upload_receipt_v1',connection_id=context.connection_id,target_id=context.target_id,
            remote_id=remote_id,owner_account_id=context.owner_account_id,destination_account_id=context.destination_account_id,
            content_id=context.content_id,content_revision=context.content_revision,manifest_hash=context.manifest_hash,
            asset_id=asset['id'],asset_sha256=asset['sha256'],asset_size=asset['size'],
            title_sha256=_sha(snippet['title']),description_sha256=_sha(snippet['description']))
        if dict(receipt)!=expected:return False
        if (candidate.get('remote_id')!=remote_id or candidate.get('target_id')!=context.target_id
                or candidate.get('destination_account_id')!=context.destination_account_id
                or candidate.get('visibility')!='public' or candidate.get('upload_status')!='processed'
                or candidate.get('processing_status')!='succeeded'
                or _sha(candidate.get('title'))!=receipt['title_sha256']
                or _sha(candidate.get('description'))!=receipt['description_sha256']):return False
        return utc(attempt['created_at'])<=utc(candidate.get('created_at'))<=utc(now)
    except (ContractError,ValueError,TypeError,KeyError,UnicodeError,OverflowError):
        return False
