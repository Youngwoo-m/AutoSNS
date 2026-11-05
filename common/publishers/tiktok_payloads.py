"""TikTok용 로컬 준비물만 만드는 순수 변환.

계획의 visibility는 사용자 의도이며 TikTok privacy_level이나 전송 동의가 아니다.
인증·creator info·코덱·실제 바이트·API 수락을 검사하거나 업로드하지 않는다.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import re

from common.operations.models import ContractError, _freeze_json
from common.operations.runtime_models import PublicationContext

PREPARED_KEYS = ('platform','connection_id','target_id','owner_account_id','destination_account_id',
                 'content_id','content_revision','manifest_hash','publication_purpose','schedule_slot',
                 'caption','caption_sha256','asset','media_sha256','delivery_mode')
MAX_ASSET_BYTES = 100 * 1024 * 1024
MAX_CAPTION_UNITS = 2200
_SHA = re.compile(r'[0-9a-f]{64}\Z')


def _invalid(code='invalid_tiktok_payload'):
    raise ContractError(code)


def _text(value):
    if type(value) is not str or not value.strip() or '\x00' in value:
        return False
    try:
        value.encode('utf-8')
    except UnicodeError:
        return False
    return True


@dataclass(frozen=True)
class TikTokPreparationContext:
    """인증·발행 권한이 없는 계획 문맥. 대상 미확인 상태도 로컬 준비할 수 있다."""
    platform: str
    connection_id: str
    target_id: str | None
    owner_account_id: str
    destination_account_id: str
    content_id: str
    content_revision: int
    manifest_hash: str
    publication_purpose: str
    schedule_slot: str
    options: Mapping

    def __post_init__(self):
        for name in ('platform','connection_id','owner_account_id','destination_account_id',
                     'content_id','manifest_hash','publication_purpose','schedule_slot'):
            if not _text(getattr(self,name)):
                _invalid('invalid_tiktok_preparation_context')
        if (self.target_id is not None and not _text(self.target_id) or
                type(self.content_revision) is not int or self.content_revision < 1 or
                not isinstance(self.options,Mapping)):
            _invalid('invalid_tiktok_preparation_context')
        try:
            object.__setattr__(self,'options',_freeze_json(self.options))
        except (TypeError,ValueError,UnicodeError,RecursionError):
            _invalid('invalid_tiktok_preparation_context')


def validate_tiktok_caption(text):
    if not _text(text):
        _invalid('invalid_tiktok_caption')
    if len(text.encode('utf-16-le')) // 2 > MAX_CAPTION_UNITS:
        _invalid('invalid_tiktok_caption')
    return text


def _asset_id(value):
    return (_text(value) and len(value) <= 300 and value not in ('.','..') and
            not any(char in value for char in ('/','\\')) and
            not any(char.isspace() or ord(char)<32 or 127<=ord(char)<=159 for char in value))


def select_tiktok_assets(snapshot, selection):
    """자동 선택 없이 MP4 하나의 metadata만 반환한다. 파일·기술 규격 검사는 아니다."""
    if not isinstance(snapshot,Mapping):
        _invalid('invalid_tiktok_asset')
    if not isinstance(selection,Mapping) or set(selection)!={'asset_ids'}:
        _invalid('tiktok_media_selection_required')
    identifiers=selection['asset_ids']
    if not isinstance(identifiers,(tuple,list)) or len(identifiers)!=1 or not _asset_id(identifiers[0]):
        _invalid('invalid_tiktok_media_selection')
    available=snapshot.get('assets')
    if not isinstance(available,(list,tuple)) or any(not isinstance(item,Mapping) for item in available):
        _invalid('invalid_tiktok_asset')
    matches=[item for item in available if item.get('id')==identifiers[0]]
    if len(matches)!=1:
        _invalid('invalid_tiktok_asset')
    item=matches[0]
    if (type(item.get('sha256')) is not str or _SHA.fullmatch(item['sha256']) is None or
            type(item.get('size')) is not int or not 0<item['size']<=MAX_ASSET_BYTES or
            item.get('media_type')!='video/mp4'):
        _invalid('invalid_tiktok_asset')
    return [{name:item[name] for name in ('id','sha256','size','media_type')}]


def build_tiktok_payload(snapshot, ctx):
    """인증·네트워크·파일 조회 없이 선택 자산과 원문을 로컬 준비물로 고정한다."""
    if not isinstance(ctx,(PublicationContext,TikTokPreparationContext)):
        _invalid('tiktok_preparation_context_required')
    if (ctx.platform!='tiktok' or ctx.owner_account_id not in ('personal','dept') or
            ctx.destination_account_id not in ('personal','dept') or
            ctx.target_id is not None and not _text(ctx.target_id) or
            not isinstance(snapshot,Mapping) or type(snapshot.get('revision')) is not int or
            _SHA.fullmatch(ctx.manifest_hash) is None or
            any(snapshot.get(key)!=getattr(ctx,field) for key,field in
                (('id','content_id'),('revision','content_revision'),('manifest_hash','manifest_hash'),
                 ('owner_account_id','owner_account_id')))):
        _invalid('tiktok_content_mismatch')
    if (set(ctx.options)-{'tiktok','visibility'} or
            'visibility' in ctx.options and ctx.options['visibility'] not in ('public','private','unlisted')):
        _invalid('tiktok_media_selection_required')
    assets=select_tiktok_assets(snapshot,ctx.options.get('tiktok'))
    variants=snapshot.get('variants',())
    if not isinstance(variants,(list,tuple)) or any(not isinstance(item,Mapping) for item in variants):
        _invalid('invalid_tiktok_content')
    selected=[item for item in variants if item.get('destination_account_id')==ctx.destination_account_id and item.get('platform')=='tiktok']
    if len(selected)>1:
        _invalid('ambiguous_tiktok_variant')
    caption=validate_tiktok_caption(selected[0].get('text') if selected else snapshot.get('original'))
    result={name:getattr(ctx,name) for name in PREPARED_KEYS if name not in
            ('caption','caption_sha256','asset','media_sha256','delivery_mode')}
    result.update(caption=caption,caption_sha256=hashlib.sha256(caption.encode('utf-8')).hexdigest(),
                  asset=assets[0],media_sha256=[assets[0]['sha256']],delivery_mode='local_preparation')
    return result
