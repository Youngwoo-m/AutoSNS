"""로컬 도구 한도에 따른 실제 디코딩 검사. 플랫폼 API 한도 검증이 아니다."""
import hashlib
import io
import warnings

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 20_000_000
MAX_SIDE = 4096
FORMATS = {'image/png': 'PNG', 'image/jpeg': 'JPEG', 'image/webp': 'WEBP'}


def inspect_thumbnail(data: bytes, *, media_type: str, expected_sha256: str | None = None) -> dict:
    result = {'status': 'error', 'sha256': None, 'width': None, 'height': None, 'findings': []}
    def fail(code):
        result['findings'].append(code)
        return result
    if not isinstance(data, bytes):
        return fail('invalid_bytes')
    result['sha256'] = hashlib.sha256(data).hexdigest()
    if len(data) > MAX_BYTES:
        return fail('byte_limit')
    if media_type not in FORMATS:
        return fail('unsupported_media_type')
    if expected_sha256 is not None and expected_sha256 != result['sha256']:
        return fail('hash_mismatch')
    try:
        from PIL import Image, ImageOps
    except ImportError:
        result['status'] = 'unavailable'
        return fail('decoder_unavailable')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != FORMATS[media_type]:
                    return fail('media_type_mismatch')
                width, height = image.size
                if width * height > MAX_PIXELS or max(width, height) > MAX_SIDE:
                    return fail('dimension_limit')
                if getattr(image, 'n_frames', 1) != 1:
                    return fail('animated_image_unsupported')
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                normalized = ImageOps.exif_transpose(image)
                result['width'], result['height'] = normalized.size
        result['status'] = 'ok'
        return result
    except Exception:
        return fail('decode_failed')
