"""실제 임시 파일과 비네트워크 probe/renderer 경계를 검증한다."""
import hashlib
import importlib
from pathlib import Path
import struct
import tempfile
import unittest
import wave


def api(name):
    try:
        module = importlib.import_module('common.operations.production_media')
    except ModuleNotFoundError:
        module = None
    value = getattr(module, name, None)
    if value is None:
        raise AssertionError(f'미디어 계약 구현 누락: {name}')
    return value


class MediaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.image = self.root/'image.png'
        # 실제 PNG 최소 fixture(1x1).
        import base64
        self.image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII='))
        self.voice = self.root/'voice.wav'
        with wave.open(str(self.voice), 'wb') as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000)
            f.writeframes(b'\0\0'*8000)
        self.video = self.root/'short.mp4'
        self.video.write_bytes(struct.pack('>I',24)+b'ftypisom'+b'\0'*12)

    def render(self, kind, manifest, runners=None):
        return api('render_registered_media')(kind, manifest, artifact_root=self.root, runners=runners or {})

    def props(self):
        return {'exam':'시험','field':'학습용','source':'출처','footer':'자세한 답안',
                'disclosure':'AI 생성 그림 · AI 합성 음성(본인 목소리 복제)', 'voice':str(self.voice),
                'scenes':[{'title':str(i),'caption':'설명','image':str(self.image),'kind':'diorama','seconds':5.0} for i in range(2)]}

    def video_runners(self, seconds=10.0, width=1080, height=1920):
        return {'remotion_video':lambda **kw:{'path':str(self.video),'font_sha256':'1'*64},
                'probe':lambda path:{'seconds':seconds,'width':width,'height':height,'has_audio':True},
                'inspect_video':lambda **kw:{'scenes':[{'index':1,'checked':True},{'index':2,'checked':True}],
                                          'audio_checked':True,'font_checked':True,'disclosure_checked':True}}

    def test_render_requires_all_assets_and_duration_at_most_20(self):
        for seconds in (20.001, float('nan'), 0):
            with self.subTest(seconds=seconds):
                self.assertEqual(self.render('remotion_video', self.props(), self.video_runners(seconds))['status'],'blocked')
        props=self.props(); props['scenes'][1]['image']=str(self.root/'absent.png')
        self.assertEqual(self.render('remotion_video',props,self.video_runners())['reason_code'],'missing_required_media')
        result=self.render('remotion_video',self.props(),self.video_runners(20.0))
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['assets'][0]['sha256'],hashlib.sha256(self.video.read_bytes()).hexdigest())
        self.assertEqual(result['evidence']['probe']['seconds'],20.0)

    def test_horizontal_video_and_unchecked_scene_are_blocked(self):
        self.assertEqual(self.render('remotion_video',self.props(),self.video_runners(width=1920,height=1080))['status'],'blocked')
        runners=self.video_runners();runners['inspect_video']=lambda **kw:{'scenes':[{'index':1,'checked':True}], 'audio_checked':True,'font_checked':True,'disclosure_checked':True}
        self.assertEqual(self.render('remotion_video',self.props(),runners)['status'],'blocked')

    def test_voice_font_disclosure_cannot_be_model_self_assertions(self):
        for missing in ('voice','disclosure'):
            props=self.props();props.pop(missing)
            self.assertEqual(self.render('remotion_video',props,self.video_runners())['status'],'blocked')
        runners=self.video_runners();runners.pop('inspect_video')
        self.assertEqual(self.render('remotion_video',self.props(),runners)['status'],'blocked')
        runners=self.video_runners();runners['remotion_video']=lambda **kw:{'path':str(self.video)}
        self.assertEqual(self.render('remotion_video',self.props(),runners)['status'],'blocked')

    def test_unregistered_image_generation_and_model_code_are_never_executed(self):
        sentinel=self.root/'executed'
        for kind,manifest in [('image_generation',{'prompt':'x'}),('remotion_video',dict(self.props(),code=f'open({str(sentinel)!r},"w")'))]:
            self.assertEqual(self.render(kind,manifest,self.video_runners())['status'],'blocked')
        self.assertFalse(sentinel.exists())

    def test_reuse_requires_server_authorization_source_and_exact_hash(self):
        manifest={'path':str(self.image),'sha256':hashlib.sha256(self.image.read_bytes()).hexdigest(),'source':'user-owned','reuse_request_id':'request-1'}
        self.assertEqual(self.render('reuse_image',manifest)['status'],'blocked')
        runners={'reuse_authorization':lambda **kw:{'authorized':True,'reviewed':True,'sha256':manifest['sha256'],'source':'user-owned','reuse_request_id':'request-1'}}
        self.assertEqual(self.render('reuse_image',manifest,runners)['status'],'completed')
        self.image.write_bytes(self.image.read_bytes()+b'changed')
        self.assertEqual(self.render('reuse_image',manifest,runners)['status'],'blocked')

    def test_paths_cannot_escape_root_or_follow_symlink(self):
        alias=self.root/'alias.png';alias.symlink_to(self.image)
        for path in (str(alias),'/tmp/outside.png','../outside.png'):
            manifest={'path':path,'sha256':'0'*64,'source':'user','reuse_request_id':'r'}
            self.assertEqual(self.render('reuse_image',manifest,{'reuse_authorization':lambda **kw:{'authorized':True}})['status'],'blocked')

    def test_real_wav_probe_and_voicebox_leaf_without_lifecycle_control(self):
        class Client:
            def ready(inner):return True
            def generate(inner, **body):
                self.assertEqual(body,dict(profile_id='server-profile',text='읽을 원고',language='ko',engine='qwen',model_size='0.6B',seed=14,normalize=True,max_chunk_chars=250))
                return {'status':'completed','id':'generation-local'}
            def audio(inner, generation_id):
                self.assertEqual(generation_id,'generation-local');return self.voice.read_bytes()
        leaf=api('VoiceboxAudioRunner')(Client(),profile_id='server-profile')
        runners={'voicebox_audio':leaf,'inspect_audio':lambda **kw:{'checked':True,'script_matches':True,'intelligible':True}}
        result=self.render('voicebox_audio',{'text':'읽을 원고','seed':14,'output':'generated.wav'},runners)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['evidence']['probe']['seconds'],1.0)
        self.assertIn('본인 목소리 복제',result['evidence']['voice_label'])
        self.assertEqual((self.root/'generated.wav').read_bytes(),self.voice.read_bytes())

    def test_unready_voicebox_is_blocked_without_start_restart_or_fallback(self):
        class Client:
            def ready(self):return False
            def generate(self, **kw):raise AssertionError('준비 안 된 서비스 호출')
        leaf=api('VoiceboxAudioRunner')(Client(),profile_id='server-profile')
        result=self.render('voicebox_audio',{'text':'원고','seed':1}, {'voicebox_audio':leaf})
        self.assertEqual(result['reason_code'],'voicebox_unavailable')

    def test_pdf_requires_all_pages_checked(self):
        pdf=self.root/'answer.pdf';pdf.write_bytes(b'%PDF-1.4\nfixture\n%%EOF\n')
        calls=[]
        def inspect(**kw):
            calls.append(kw['page_number'])
            return {'checked':True,'page_number':kw['page_number'],'rendered_path':str(self.image)}
        runners={'pdf_document':lambda **kw:{'path':str(pdf)},'pdf_probe':lambda path:{'page_count':2,'safe_parser':True,'encrypted':False},'inspect_pdf_page':inspect}
        result=self.render('pdf_document',{'title':'답안','body':'본문'},runners)
        self.assertEqual(result['status'],'completed');self.assertEqual(calls,[1,2])
        self.assertEqual(len(result['evidence']['pages']),2)
        self.assertEqual(result['assets'][0]['media_type'],'application/pdf')
        runners['inspect_pdf_page']=lambda **kw:{'checked':kw['page_number']==1,'page_number':kw['page_number'],'rendered_path':str(self.image)}
        self.assertEqual(self.render('pdf_document',{'title':'답안','body':'본문'},runners)['status'],'blocked')
        runners['pdf_probe']=lambda path:{'page_count':2,'safe_parser':False,'encrypted':False}
        self.assertEqual(self.render('pdf_document',{'title':'답안','body':'본문'},runners)['status'],'blocked')

    def test_remotion_leaf_executes_fixed_reviewed_template_with_schema_data(self):
        module=importlib.import_module('common.operations.production_media') if api('RemotionVideoRunner') else None
        template=self.root/'template';(template/'src/survey-short').mkdir(parents=True)
        (template/'src/survey-short/index.ts').write_text('// reviewed fixture')
        font=self.root/'font.otf';font.write_bytes(b'fixture-font')
        commands=[]
        def child(args,**kwargs):
            import json
            commands.append(args)
            self.assertFalse(kwargs['shell']);self.assertEqual(Path(kwargs['cwd']),template)
            propsfile=next(a[8:] for a in args if a.startswith('--props='))
            props=__import__('json').loads(Path(propsfile).read_text())
            self.assertEqual(props['exam'],'시험');self.assertEqual(props['voice'],'voice.wav')
            public=Path(next(a[13:] for a in args if a.startswith('--public-dir=')))
            self.assertEqual((public/'Pretendard-Bold.otf').read_bytes(),b'fixture-font')
            Path(args[6]).write_bytes(self.video.read_bytes())
            return __import__('types').SimpleNamespace(returncode=0,stdout='',stderr='')
        leaf=api('RemotionVideoRunner')(template,template_hash=module.template_hash(template),font_path=font,spawn=child)
        result=leaf(manifest=dict(self.props(),output='rendered.mp4'),artifact_root=self.root)
        self.assertEqual(result['path'],str(self.root/'rendered.mp4'))
        self.assertEqual(commands[0][:6],['npx','--no-install','remotion','render','src/survey-short/index.ts','SurveyShort'])
        (template/'src/survey-short/index.ts').write_text('// changed')
        with self.assertRaisesRegex(Exception,'template_changed'):leaf(manifest=self.props(),artifact_root=self.root)

    def test_real_pdf_parser_counts_two_pages_and_rejects_javascript(self):
        def pdf_bytes(action=False):
            objects=[b'<< /Type /Catalog /Pages 2 0 R'+(b' /OpenAction 6 0 R' if action else b'')+b' >>',
                     b'<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>',
                     b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 5 0 R >>',
                     b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 5 0 R >>',
                     b'<< /Length 0 >>\nstream\n\nendstream']
            if action:objects.append(br'<< /S /JavaScript /JS (app.alert\(1\)) >>')
            raw=b'%PDF-1.4\n';offsets=[0]
            for i,obj in enumerate(objects,1):
                offsets.append(len(raw));raw+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
            xref=len(raw);raw+=f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode()
            raw+=b''.join(f'{off:010d} 00000 n \n'.encode() for off in offsets[1:])
            return raw+f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
        path=self.root/'real.pdf';path.write_bytes(pdf_bytes())
        parsed=api('probe_pdf')(path)
        self.assertEqual(parsed['page_count'],2);self.assertTrue(parsed['safe_parser'])
        path.write_bytes(pdf_bytes(True))
        self.assertFalse(api('probe_pdf')(path)['safe_parser'])

    def test_manifest_wrong_types_block_before_leaf_execution(self):
        for props in (dict(self.props(),scenes=[None,None]),dict(self.props(),scenes=[{},{}]),dict(self.props(),output=[])):
            result=self.render('remotion_video',props,self.video_runners())
            self.assertEqual(result['status'],'blocked')

    def test_server_leaf_unavailable_and_incomplete_disclosure_block(self):
        def unavailable(**kwargs):raise RuntimeError('fixture 서비스 준비 안 됨')
        try:result=self.render('voicebox_audio',{'text':'원고'}, {'voicebox_audio':unavailable})
        except RuntimeError:result={'status':'escaped_exception'}
        self.assertEqual(result['status'],'blocked')
        props=dict(self.props(),disclosure='AI 음성')
        self.assertEqual(self.render('remotion_video',props,self.video_runners())['status'],'blocked')
