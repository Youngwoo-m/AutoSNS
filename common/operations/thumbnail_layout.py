"""서버 등록 폰트·고정 템플릿만 쓰는 선택적 로컬 PNG 렌더러."""
import hashlib
import io
import os
from pathlib import Path
from collections.abc import Mapping

from .thumbnail_checks import inspect_thumbnail

REGISTERED_FONT = Path(__file__).resolve().parents[1] / 'remotion-shorts/public/Pretendard-Bold.otf'
PRESETS = {'landscape.v1': (1280, 720), 'portrait.v1': (1080, 1920)}
TEMPLATE_VERSION = 'local-thumbnail.v1'


def _result(status, code, asset=None, findings=None):
    return {'status': status, 'reason_code': code, 'asset': asset, 'findings': findings or []}


def render_thumbnail(request: Mapping, *, renderer=None) -> dict:
    if not isinstance(request, Mapping) or set(request) - {'preset_id','title','image_bytes','image_sha256'}:
        return _result('blocked','invalid_request')
    if not isinstance(request.get('preset_id'), str) or request.get('preset_id') not in PRESETS or not isinstance(request.get('title'), str) or not request['title'].strip():
        return _result('blocked','invalid_request')
    if request.get('image_bytes') is not None:
        data = request['image_bytes']
        if not isinstance(data, bytes) or not isinstance(request.get('image_sha256'), str):
            return _result('blocked','invalid_image')
        # Detect only supported formats; actual decoder and hash remain authoritative.
        media_type = _media_type(data)
        checked = inspect_thumbnail(data, media_type=media_type, expected_sha256=request['image_sha256'])
        if checked['status'] != 'ok':
            return _result('unavailable' if checked['status']=='unavailable' else 'blocked','invalid_image',findings=checked['findings'])
    elif request.get('image_sha256') is not None:
        return _result('blocked','invalid_image')
    if renderer is None:
        return _result('unavailable','renderer_unavailable')
    try:
        result = renderer(dict(request))
        if result['status'] != 'completed':
            return result
        asset = result['asset']
        checked = inspect_thumbnail(asset['data'], media_type='image/png', expected_sha256=asset['sha256'])
        if checked['status'] != 'ok':
            return _result('unavailable' if checked['status']=='unavailable' else 'blocked','invalid_render_output',findings=checked['findings'])
        if (checked['width'],checked['height']) != PRESETS[request['preset_id']]:
            return _result('blocked','invalid_render_dimensions')
        asset.update(width=checked['width'],height=checked['height'])
        return result
    except Exception:
        return _result('blocked','render_failed')


def _media_type(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith(b'\xff\xd8'):
        return 'image/jpeg'
    if data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return 'image/webp'
    return ''


class PillowThumbnailRenderer:
    def __init__(self, font_path: Path, *, font_sha256: str):
        self.font_path = Path(font_path)
        self.font_sha256 = font_sha256

    def _font_bytes(self):
        path = self.font_path.absolute()
        if path != REGISTERED_FONT.absolute() or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError('unregistered font')
        # Open once without following a final symlink, then hash and use those exact bytes.
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd, 'rb') as source:
            data = source.read()
        if hashlib.sha256(data).hexdigest() != self.font_sha256:
            raise ValueError('font hash mismatch')
        return data

    def __call__(self, request: Mapping) -> dict:
        try:
            font_bytes = self._font_bytes()
        except (OSError, ValueError):
            return _result('blocked','font_validation_failed')
        try:
            from PIL import Image, ImageDraw, ImageFont, ImageOps
        except ImportError:
            return _result('unavailable','renderer_unavailable')
        width,height = PRESETS[request['preset_id']]
        image = Image.new('RGB',(width,height),(20,29,46))
        if request.get('image_bytes') is not None:
            with Image.open(io.BytesIO(request['image_bytes'])) as source:
                source.load()
                background = ImageOps.fit(ImageOps.exif_transpose(source).convert('RGB'),(width,height))
                image.paste(background)
            image = Image.blend(image,Image.new('RGB',image.size,(0,0,0)),0.45)
        font = ImageFont.truetype(io.BytesIO(font_bytes),size=64 if width==1280 else 72)
        draw = ImageDraw.Draw(image)
        lines = request['title'].split('\n')
        inset_x,inset_y = int(width*.05),int(height*.05)
        if len(lines) > 3:
            return _result('blocked','text_overflow')
        boxes = [draw.textbbox((0,0),line,font=font) for line in lines]
        gap=20
        total_height=sum(b[3]-b[1] for b in boxes) + gap*(len(lines)-1)
        if len(lines)>3 or total_height>height-2*inset_y or any(b[2]-b[0]>width-2*inset_x for b in boxes):
            return _result('blocked','text_overflow',findings=['문구를 축약하지 않았습니다. 최대 3줄과 각 변 5% 안전영역을 확인하세요.'])
        y=(height-total_height)//2
        for line,box in zip(lines,boxes):
            x=(width-(box[2]-box[0]))//2
            draw.text((x-box[0],y-box[1]),line,font=font,fill='white')
            y+=box[3]-box[1]+gap
        out=io.BytesIO(); image.save(out,format='PNG'); data=out.getvalue()
        checked=inspect_thumbnail(data,media_type='image/png')
        if checked['status']!='ok':
            return _result('unavailable' if checked['status']=='unavailable' else 'blocked','invalid_render_output',findings=checked['findings'])
        return _result('completed','rendered',asset={'data':data,'filename':request['preset_id']+'.png','media_type':'image/png','sha256':checked['sha256'],'width':width,'height':height,'font_sha256':self.font_sha256,'template_version':TEMPLATE_VERSION})
