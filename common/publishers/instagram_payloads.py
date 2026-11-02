"""승인된 콘텐츠와 명시 매체 선택을 결속하는 순수 Instagram 준비.

실제 파일 바이트·기술 규격·권리·최종 자산 승인·URL 공개 전송·계정 권한·API 수락을
검증하지 않는다. JPEG 변환이나 자산 자동 선택은 하지 않는다. 개수/캡션 상한은
서버 내부 선택 정책이며 현재 공식 API 제약을 검증했다는 뜻이 아니다.
"""
from collections.abc import Mapping
import hashlib
import re
from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext

PREPARED_KEYS=('platform','connection_id','target_id','owner_account_id','destination_account_id',
    'content_id','content_revision','manifest_hash','publication_purpose','schedule_slot','caption',
    'caption_sha256','media_format','assets','media_sha256')
NUMERIC_ID=re.compile(r'[0-9]{1,64}')
SHA256=re.compile(r'[0-9a-f]{64}')
MAX_CAPTION_CHARS=2200
MAX_CAROUSEL_ASSETS=10
_MEDIA_TYPES=frozenset(('image/jpeg','video/mp4'))


def _invalid(code='invalid_instagram_payload'):raise ContractError(code)


def validate_instagram_caption(text):
    if type(text) is not str or not text.strip() or '\x00' in text or len(text)>MAX_CAPTION_CHARS:
        _invalid('invalid_instagram_caption')
    try:text.encode('utf-8')
    except UnicodeError:_invalid('invalid_instagram_caption')
    return text


def _valid_asset_id(value):
    # 자산 식별자는 표시 문자열/경로가 아니다. 공백·개행·제어 문자를 허용하지 않는다.
    if (type(value) is not str or not value or len(value)>300 or value in ('.','..')
            or any(char in value for char in ('/','\\'))
            or any(char.isspace() or ord(char)<32 or 127<=ord(char)<=159 for char in value)):
        return False
    try:value.encode('utf-8')
    except UnicodeError:return False
    return True


def build_instagram_payload(snapshot,ctx):
    """파일/자격/URL 조회 없이 선택된 불변 자산 metadata와 캡션만 새 dict로 반환한다."""
    if not isinstance(ctx,PublicationContext):_invalid('publication_context_required')
    if (ctx.platform!='instagram' or type(ctx.owner_account_id) is not str or ctx.owner_account_id not in ('personal','dept')
            or type(ctx.destination_account_id) is not str or ctx.destination_account_id not in ('personal','dept') or NUMERIC_ID.fullmatch(ctx.target_id) is None
            or not isinstance(snapshot,Mapping) or type(snapshot.get('revision')) is not int
            or any(snapshot.get(name)!=getattr(ctx,field) for name,field in (
                ('id','content_id'),('revision','content_revision'),('manifest_hash','manifest_hash'),('owner_account_id','owner_account_id')))):
        _invalid('instagram_content_mismatch')
    if set(ctx.options)-{'visibility','instagram'} or ctx.options.get('visibility','public')!='public':
        _invalid('instagram_media_selection_required')
    selection=ctx.options.get('instagram')
    if not isinstance(selection,Mapping) or set(selection)!={'format','asset_ids'}:
        _invalid('instagram_media_selection_required')
    media_format,identifiers=selection['format'],selection['asset_ids']
    if (type(media_format) is not str or media_format not in ('image','reels','carousel')
            or not isinstance(identifiers,(list,tuple)) or any(not _valid_asset_id(identifier) for identifier in identifiers)
            or len(identifiers)!=len(set(identifiers))):_invalid('invalid_instagram_media_selection')
    if media_format=='carousel':
        if not 2<=len(identifiers)<=MAX_CAROUSEL_ASSETS:_invalid('invalid_instagram_media_selection')
    elif len(identifiers)!=1:_invalid('invalid_instagram_media_selection')
    available=snapshot.get('assets')
    if not isinstance(available,(list,tuple)) or any(not isinstance(item,Mapping) for item in available):
        _invalid('invalid_instagram_asset')
    assets=[]
    for identifier in identifiers:
        matches=[item for item in available if item.get('id')==identifier]
        if len(matches)!=1:_invalid('invalid_instagram_asset')
        item=matches[0]
        if (type(item.get('sha256')) is not str or SHA256.fullmatch(item['sha256']) is None
                or type(item.get('size')) is not int or item['size']<=0
                or type(item.get('media_type')) is not str or item['media_type'] not in _MEDIA_TYPES):
            _invalid('invalid_instagram_asset')
        if (media_format=='image' and item['media_type']!='image/jpeg'
                or media_format=='reels' and item['media_type']!='video/mp4'):_invalid('invalid_instagram_asset')
        assets.append({name:item[name] for name in ('id','sha256','size','media_type')})
    variants=snapshot.get('variants',())
    if not isinstance(variants,(list,tuple)) or any(not isinstance(item,Mapping) for item in variants):
        _invalid('invalid_instagram_content')
    selected=[item for item in variants if item.get('destination_account_id')==ctx.destination_account_id and item.get('platform')=='instagram']
    if len(selected)>1:_invalid('ambiguous_instagram_variant')
    caption=validate_instagram_caption(selected[0].get('text') if selected else snapshot.get('original'))
    result={name:getattr(ctx,name) for name in PREPARED_KEYS if name not in ('caption','caption_sha256','media_format','assets','media_sha256')}
    result.update(caption=caption,caption_sha256=hashlib.sha256(caption.encode('utf-8')).hexdigest(),
                  media_format=media_format,assets=assets,media_sha256=[item['sha256'] for item in assets])
    return result
