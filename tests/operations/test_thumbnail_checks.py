import hashlib
import io
import struct
import unittest
import zlib
from unittest.mock import patch
from common.operations.thumbnail_checks import inspect_thumbnail

try:
    from PIL import Image
except ImportError:
    Image = None


class ThumbnailChecksTests(unittest.TestCase):
    def test_signature_is_not_successful_decode(self):
        self.assertNotEqual(inspect_thumbnail(b'\x89PNG\r\n\x1a\n' + b'broken', media_type='image/png')['status'], 'ok')

    def test_missing_decoder_is_unavailable(self):
        with patch.dict('sys.modules', {'PIL': None}):
            self.assertEqual(inspect_thumbnail(b'image', media_type='image/png')['status'], 'unavailable')

    def test_byte_limit_and_hash(self):
        self.assertEqual(inspect_thumbnail(b'x' * (8*1024*1024+1), media_type='image/png')['status'], 'error')
        self.assertEqual(inspect_thumbnail(b'x', media_type='image/png', expected_sha256='0'*64)['status'], 'error')

    @unittest.skipUnless(Image, 'Pillow 미설치: 실제 디코딩 환경 미확인')
    def test_pixel_bomb_exif_orientation_and_oversize(self):
        def encoded(size, fmt='PNG', exif=None):
            out=io.BytesIO(); Image.new('RGB', size).save(out, format=fmt, **({'exif':exif} if exif else {})); return out.getvalue()
        data=encoded((2,3)); result=inspect_thumbnail(data,media_type='image/png')
        self.assertEqual((result['status'],result['width'],result['height']), ('ok',2,3))
        self.assertEqual(result['sha256'],hashlib.sha256(data).hexdigest())
        exif=Image.Exif(); exif[274]=6
        result=inspect_thumbnail(encoded((2,3),'JPEG',exif),media_type='image/jpeg')
        self.assertEqual((result['width'],result['height']), (3,2))
        self.assertEqual(inspect_thumbnail(encoded((4097,1)),media_type='image/png')['status'],'error')
        # A real decoder opens this valid 25M-pixel PNG header; no huge allocation is needed.
        header=struct.pack('>IIBBBBB',5000,5000,8,2,0,0,0)
        chunk=b'IHDR'+header
        bomb=b'\x89PNG\r\n\x1a\n'+struct.pack('>I',len(header))+chunk+struct.pack('>I',zlib.crc32(chunk))
        self.assertEqual(inspect_thumbnail(bomb,media_type='image/png')['status'],'error')
        with patch.object(Image,'MAX_IMAGE_PIXELS',4):
            self.assertEqual(inspect_thumbnail(data,media_type='image/png')['status'],'error')
        with patch('common.operations.thumbnail_checks.MAX_PIXELS', 5):
            self.assertEqual(inspect_thumbnail(data,media_type='image/png')['status'],'error')
        self.assertEqual(inspect_thumbnail(data,media_type='image/jpeg')['status'],'error')
        self.assertEqual(inspect_thumbnail(data[:-15],media_type='image/png')['status'],'error')
