"""Facebook Pages 텍스트 전용 준비. 계정 namespace는 개인 프로필 게시를 뜻하지 않는다.

숫자 target_id의 실제 Page 유형·권한·소유 확인은 서버 등록/실행 경계의 책임이다.
여기는 승인된 자료의 논리 결속만 검사하며 자격·파일·네트워크에 접근하지 않는다.
"""
from collections.abc import Mapping
import hashlib
import re
from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext

PREPARED_KEYS=('platform','connection_id','target_id','owner_account_id','destination_account_id',
               'content_id','content_revision','manifest_hash','publication_purpose','schedule_slot',
               'text','body_sha256','media_sha256')
NUMERIC_ID=re.compile(r'[0-9]{1,64}')
# 서버 내부의 UTF-8 전송 상한이다. Facebook의 문자수 제한이나 공식 API 수락 증거가 아니다.
MAX_TEXT_BYTES=200000


def validate_facebook_text(text):
    if type(text) is not str or not text.strip() or '\x00' in text:
        raise ContractError('invalid_facebook_text')
    try:raw=text.encode('utf-8')
    except UnicodeError:raise ContractError('invalid_facebook_text') from None
    if len(raw)>MAX_TEXT_BYTES:raise ContractError('invalid_facebook_text')
    return text


def build_facebook_payload(snapshot,ctx):
    if not isinstance(ctx,PublicationContext):raise ContractError('publication_context_required')
    if (ctx.platform!='facebook' or ctx.owner_account_id not in ('personal','dept')
            or ctx.destination_account_id not in ('personal','dept') or not NUMERIC_ID.fullmatch(ctx.target_id)
            or not isinstance(snapshot,Mapping) or type(snapshot.get('revision')) is not int
            or any(snapshot.get(key)!=getattr(ctx,field) for key,field in (
                ('id','content_id'),('revision','content_revision'),('manifest_hash','manifest_hash'),('owner_account_id','owner_account_id')))):
        raise ContractError('facebook_content_mismatch')
    if (set(ctx.options)-{'text_only','visibility'} or ctx.options.get('text_only') is not True
            or ctx.options.get('visibility','public')!='public'):
        raise ContractError('facebook_text_only_required')
    variants=snapshot.get('variants',())
    if not isinstance(variants,(list,tuple)) or any(not isinstance(item,Mapping) for item in variants):
        raise ContractError('invalid_facebook_content')
    selected=[item for item in variants if item.get('destination_account_id')==ctx.destination_account_id and item.get('platform')=='facebook']
    if len(selected)>1:raise ContractError('ambiguous_facebook_variant')
    text=validate_facebook_text(selected[0].get('text') if selected else snapshot.get('original'))
    result={name:getattr(ctx,name) for name in PREPARED_KEYS if name not in ('text','body_sha256','media_sha256')}
    result.update(text=text,body_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),media_sha256=[])
    return result
