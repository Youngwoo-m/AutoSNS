"""승인된 X 텍스트 전용 변환. 원문·URL·공백·자산은 변경하지 않는다.

길이 판정은 고정된 twitter-text v3 규칙과 공식 twemoji-parser 11.0.2를 쓴다.
NFC는 계산에만 적용하며 반환 원문에는 적용하지 않는다. 네트워크나 subprocess는 없다.
"""
from collections.abc import Mapping
import hashlib
import re
from types import MappingProxyType

from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext
from .vendor.twitter_text import parse_tweet

PREPARED_KEYS = ('platform','connection_id','target_id','owner_account_id','destination_account_id',
                 'content_id','content_revision','manifest_hash','publication_purpose','schedule_slot',
                 'text','body_sha256','media_sha256')
NUMERIC_ID = re.compile(r'[0-9]{1,64}\Z')
_X_CONFIG = MappingProxyType(dict(version=3, max_weighted_tweet_length=280, scale=100,
    default_weight=200, transformed_url_length=23, emoji_parsing_enabled=True,
    ranges=tuple(MappingProxyType(dict(start=start,end=end,weight=100)) for start,end in
                 ((0,4351),(8192,8205),(8208,8223),(8242,8247)))))


def validate_x_text(text):
    if type(text) is not str or not text.strip() or '\x00' in text:
        raise ContractError('invalid_x_text')
    try:
        text.encode('utf-8')
        if not parse_tweet(text, _X_CONFIG).valid:
            raise ContractError('invalid_x_text')
    except (UnicodeError, ValueError, OverflowError, RecursionError):
        raise ContractError('invalid_x_text') from None
    return text


def build_x_payload(snapshot, ctx):
    if not isinstance(ctx, PublicationContext):
        raise ContractError('publication_context_required')
    if (ctx.platform != 'x' or ctx.owner_account_id not in ('personal','dept') or
            ctx.destination_account_id not in ('personal','dept') or type(ctx.target_id) is not str or
            NUMERIC_ID.fullmatch(ctx.target_id) is None or not isinstance(snapshot, Mapping) or
            type(snapshot.get('revision')) is not int or
            any(snapshot.get(key) != getattr(ctx, field) for key,field in
                (('id','content_id'),('revision','content_revision'),('manifest_hash','manifest_hash'),
                 ('owner_account_id','owner_account_id')))):
        raise ContractError('x_content_mismatch')
    if (set(ctx.options)-{'text_only','visibility'} or ctx.options.get('text_only') is not True or
            ctx.options.get('visibility','public') != 'public'):
        raise ContractError('x_text_only_required')
    variants = snapshot.get('variants', ())
    if not isinstance(variants, (list,tuple)) or any(not isinstance(v, Mapping) for v in variants):
        raise ContractError('invalid_x_content')
    selected = [v for v in variants if v.get('destination_account_id') == ctx.destination_account_id and v.get('platform') == 'x']
    if len(selected) > 1:
        raise ContractError('ambiguous_x_variant')
    text = validate_x_text(selected[0].get('text') if selected else snapshot.get('original'))
    result = {name:getattr(ctx,name) for name in PREPARED_KEYS if name not in ('text','body_sha256','media_sha256')}
    result.update(text=text,body_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),media_sha256=[])
    return result
