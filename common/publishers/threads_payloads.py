"""승인된 텍스트 전용 Threads 변환. 원고·자산을 바꾸거나 외부 상태를 읽지 않는다."""
from collections.abc import Mapping
import hashlib
import re
from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext

PREPARED_KEYS=('platform','connection_id','target_id','owner_account_id','destination_account_id','content_id','content_revision','manifest_hash','publication_purpose','schedule_slot','text','body_sha256','media_sha256')
NUMERIC_ID=re.compile(r'[0-9]{1,64}')


def validate_threads_text(text):
    if type(text) is not str or not text.strip() or len(text)>500:
        raise ContractError('invalid_threads_text')
    try:text.encode('utf-8')
    except UnicodeError:raise ContractError('invalid_threads_text') from None
    return text


def build_threads_payload(snapshot,ctx):
    if not isinstance(ctx,PublicationContext):raise ContractError('publication_context_required')
    if (ctx.platform!='threads' or ctx.owner_account_id not in ('personal','dept') or ctx.destination_account_id not in ('personal','dept')
            or not NUMERIC_ID.fullmatch(ctx.target_id) or not isinstance(snapshot,Mapping) or type(snapshot.get('revision')) is not int
            or any(snapshot.get(key)!=getattr(ctx,field) for key,field in (('id','content_id'),('revision','content_revision'),('manifest_hash','manifest_hash'),('owner_account_id','owner_account_id')))):
        raise ContractError('threads_content_mismatch')
    if set(ctx.options)-{'text_only','visibility'} or ctx.options.get('text_only') is not True or ctx.options.get('visibility','public')!='public':
        raise ContractError('threads_text_only_required')
    variants=snapshot.get('variants',())
    if not isinstance(variants,(list,tuple)) or any(not isinstance(v,Mapping) for v in variants):
        raise ContractError('invalid_threads_content')
    selected=[v for v in variants if v.get('destination_account_id')==ctx.destination_account_id and v.get('platform')=='threads']
    if len(selected)>1:raise ContractError('ambiguous_threads_variant')
    text=validate_threads_text(selected[0].get('text') if selected else snapshot.get('original'))
    result={name:getattr(ctx,name) for name in PREPARED_KEYS if name not in ('text','body_sha256','media_sha256')}
    result.update(text=text,body_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),media_sha256=[])
    return result
