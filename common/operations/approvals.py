"""검증된 불변 스냅숏에 대한 순수 계획 승인 subject. 파일 접근은 호출자 책임이다."""
import hashlib
import json
from collections.abc import Mapping
from .models import ContractError, thaw


def approval_fingerprint(snapshot: dict, context: dict) -> str:
    if not isinstance(snapshot, Mapping) or not isinstance(context, Mapping):
        raise ContractError('invalid_approval_subject')
    snapshot, context = thaw(snapshot), thaw(context)
    if not isinstance(context.get('target_id'), str) or not context['target_id'].strip():
        raise ContractError('unverified_target')
    if context.get('scope') != 'plan' or context.get('execution_enabled') is not False or context.get('dry_run') is not True:
        raise ContractError('invalid_approval_scope')
    if not all(isinstance(context.get(key),str) and context[key] for key in ('policy_revision','registry_revision')):
        raise ContractError('invalid_approval_subject')
    revision = snapshot.get('revision')
    if type(revision) is not int or revision < 1 or context.get('content_revision') != revision:
        raise ContractError('content_revision_mismatch')
    if snapshot.get('owner_account_id') != context.get('owner_account_id') or snapshot.get('id') != context.get('content_id'):
        raise ContractError('content_owner_mismatch')
    for key in ('reviews','variants','sources','assets'):
        value=snapshot.get(key,[])
        if not isinstance(value,list) or not all(isinstance(item,dict) for item in value):
            raise ContractError('invalid_approval_subject')
    reviews=[]
    for review in snapshot.get('reviews', []):
        if not isinstance(review, dict) or review.get('revision') != revision or review.get('manifest_hash') != snapshot.get('manifest_hash'):
            raise ContractError('review_revision_mismatch')
        reviews.append({key:value for key,value in review.items() if key not in ('id','created_at','updated_at','recorded_at','reviewed_at')})
    selected=[variant for variant in snapshot.get('variants', []) if variant.get('destination_account_id') == context.get('destination_account_id') and variant.get('platform') == context.get('platform')]
    if len(selected)>1:
        raise ContractError('invalid_approval_subject')
    content={key:snapshot.get(key) for key in ('id','revision','manifest_hash','owner_account_id','title','kind','series','original','sources','assets')}
    content['selected_variant']=selected[0] if selected else None
    # Review insertion order and review timestamps are bookkeeping, unlike asset order.
    try:
        reviews.sort(key=lambda row:json.dumps(row,sort_keys=True,ensure_ascii=False,allow_nan=False))
        payload={'snapshot':content,'reviews':reviews,'context':dict(context,scope='plan',execution_enabled=False,dry_run=True)}
        raw=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
    except (ValueError,TypeError,UnicodeError,RecursionError) as exc:
        raise ContractError('invalid_approval_subject') from exc
    return hashlib.sha256(raw).hexdigest()


def is_approval_current(record, snapshot, context) -> bool:
    if not isinstance(record, Mapping) or record.get('decision') != 'approved' or record.get('source') != 'manual' or record.get('scope') != 'plan':
        return False
    if record.get('content_revision') != snapshot.get('revision'):
        return False
    if any(key in record and record[key] != context.get(key) for key in ('policy_revision','registry_revision')):
        return False
    try:
        return record.get('subject_hash') == approval_fingerprint(snapshot, context)
    except (ContractError,TypeError,AttributeError):
        return False
