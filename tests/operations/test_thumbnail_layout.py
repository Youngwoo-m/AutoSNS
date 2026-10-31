import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from common.operations.thumbnail_layout import PillowThumbnailRenderer, render_thumbnail, REGISTERED_FONT
try:
    from PIL import Image
except ImportError:
    Image=None

class ThumbnailLayoutTests(unittest.TestCase):
    def test_unavailable_renderer_never_calls_network(self):
        with patch('socket.socket', side_effect=AssertionError('network forbidden')):
            self.assertEqual(render_thumbnail({'preset_id':'landscape.v1','title':'제목'})['status'],'unavailable')

    def test_unknown_request_fields_and_bad_presets_block(self):
        self.assertEqual(render_thumbnail({'preset_id':[], 'title':'x'},renderer=lambda r: {})['status'],'blocked')
        self.assertEqual(render_thumbnail({'preset_id':'wrong','title':'x'},renderer=lambda r: {})['status'],'blocked')
        self.assertEqual(render_thumbnail({'preset_id':'landscape.v1','title':'x','font_path':'/tmp/x'},renderer=lambda r: {})['status'],'blocked')

    def test_font_symlink_or_hash_change_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'font.otf'; path.symlink_to(REGISTERED_FONT)
            renderer=PillowThumbnailRenderer(path,font_sha256='0'*64)
            self.assertEqual(render_thumbnail({'preset_id':'landscape.v1','title':'x'},renderer=renderer)['status'],'blocked')
        with tempfile.TemporaryDirectory() as tmp:
            font=Path(tmp)/'font.otf'; font.write_bytes(b'old font bytes')
            with patch('common.operations.thumbnail_layout.REGISTERED_FONT',font):
                renderer=PillowThumbnailRenderer(font,font_sha256=hashlib.sha256(font.read_bytes()).hexdigest())
                font.write_bytes(b'changed font bytes')
                self.assertEqual(render_thumbnail({'preset_id':'landscape.v1','title':'x'},renderer=renderer)['reason_code'],'font_validation_failed')
        renderer=PillowThumbnailRenderer(REGISTERED_FONT,font_sha256='0'*64)
        self.assertEqual(render_thumbnail({'preset_id':'landscape.v1','title':'x'},renderer=renderer)['status'],'blocked')

    def test_rendered_png_byte_limit_is_enforced(self):
        data=b'x'*(8*1024*1024+1)
        renderer=lambda request: {'status':'completed','reason_code':'rendered','asset':{'data':data,'sha256':hashlib.sha256(data).hexdigest()}}
        result=render_thumbnail({'preset_id':'landscape.v1','title':'x'},renderer=renderer)
        self.assertEqual(result['reason_code'],'invalid_render_output')
        self.assertEqual(result['findings'],['byte_limit'])

    @unittest.skipUnless(Image and REGISTERED_FONT.is_file(), 'Pillow/등록 폰트 미가용: 실제 렌더 환경 미확인')
    def test_three_lines_safe_box_overflow_never_truncates(self):
        renderer=PillowThumbnailRenderer(REGISTERED_FONT,font_sha256=hashlib.sha256(REGISTERED_FONT.read_bytes()).hexdigest())
        for preset, dimensions in [('landscape.v1',(1280,720)),('portrait.v1',(1080,1920))]:
            result=render_thumbnail({'preset_id':preset,'title':'측량 기술\n안전한 작업\n기준 확인'},renderer=renderer)
            self.assertEqual(result['status'],'completed',result)
            asset=result['asset']; self.assertEqual((asset['width'],asset['height']),dimensions)
            self.assertEqual(asset['sha256'],hashlib.sha256(asset['data']).hexdigest())
        for title in ['가'*500, '1\n2\n3\n4']:
            result=render_thumbnail({'preset_id':'landscape.v1','title':title},renderer=renderer)
            self.assertEqual(result['reason_code'],'text_overflow')
            self.assertIsNone(result['asset'])
