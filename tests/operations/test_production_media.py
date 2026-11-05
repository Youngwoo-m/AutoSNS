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
                'scenes':[{'title':str(i),'caption':'설명','image':str(self.image),'kind':'diorama','seconds':5.0,'image_asset_id':'scene-image'} for i in range(2)]}

    def video_runners(self, seconds=10.0, width=1080, height=1920):
        return {'scene_assets':self.scene_registry(),'reuse_authorization':self.scene_authorization,
                'remotion_video':lambda **kw:{'path':str(self.video),'font_sha256':'1'*64},
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
        leaf=api('RemotionVideoRunner')(template,template_hash=module.template_hash(template),font_path=font,spawn=child,
                scene_assets=self.scene_registry(),reuse_authorization=self.scene_authorization)
        result=leaf(manifest=dict(self.props(),output='rendered.mp4'),artifact_root=self.root)
        self.assertEqual(result['path'],str(self.root/'rendered.mp4'))
        self.assertEqual(commands[0][:6],['npx','--no-install','remotion','render','src/survey-short/index.ts','SurveyShort'])
        (template/'src/survey-short/index.ts').write_text('// changed')
        with self.assertRaisesRegex(Exception,'template_changed'):leaf(manifest=self.props(),artifact_root=self.root)

    def test_real_pdf_page_count_does_not_claim_object_safety(self):
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
        self.assertEqual(parsed['page_count'],2);self.assertFalse(parsed['safe_parser'])
        self.assertEqual(parsed['reason_code'],'pdf_object_inspection_unavailable')
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

    def test_pdf_escaped_names_compressed_objects_and_non_js_actions_are_never_claimed_safe(self):
        import zlib
        import subprocess
        def make_pdf(action, compressed=False, annotation=False):
            root=b'<< /Type /Catalog /Pages 2 0 R'+(b'' if annotation else b' /Open#41ction 6 0 R')+b' >>'
            page=b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R'+(b' /Annots [6 0 R]' if annotation else b'')+b' >>'
            objects={1:root,2:b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',3:page,4:b'<< /Length 0 >>\nstream\n\nendstream',5:b'null'}
            if not compressed:objects[6]=action
            else:
                stream=zlib.compress(b'6 0 '+action)
                objects[7]=f'<< /Type /ObjStm /N 1 /First 4 /Filter /FlateDecode /Length {len(stream)} >>\nstream\n'.encode()+stream+b'\nendstream'
            raw=b'%PDF-1.5\n';offsets={}
            for i,obj in sorted(objects.items()):
                offsets[i]=len(raw);raw+=f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n'
            if not compressed:
                xref=len(raw);raw+=b'xref\n0 7\n0000000000 65535 f \n'
                raw+=b''.join(f'{offsets[i]:010d} 00000 n \n'.encode() for i in range(1,7))
                raw+=f'trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
            else:
                offsets[8]=len(raw)
                entries=b'\0'+(0).to_bytes(4,'big')+(65535).to_bytes(2,'big')
                for i in range(1,9):
                    entries+=(b'\2'+(7).to_bytes(4,'big')+b'\0\0' if i==6 else b'\1'+offsets[i].to_bytes(4,'big')+b'\0\0')
                raw+=f'8 0 obj\n<< /Type /XRef /Size 9 /W [1 4 2] /Root 1 0 R /Length {len(entries)} >>\nstream\n'.encode()+entries+b'\nendstream\nendobj\n'
                raw+=f'startxref\n{offsets[8]}\n%%EOF\n'.encode()
            return raw
        cases=[('escaped-launch',make_pdf(b'<< /S /L#61unch /F (untrusted.bin) >>')),
               ('compressed-launch',make_pdf(b'<< /S /L#61unch /F (untrusted.bin) >>',compressed=True)),
               ('non-js-annotation',make_pdf(b'<< /Type /Annot /Subtype /Link /Rect [0 0 10 10] /A << /S /GoToR /F (untrusted.pdf) /D [0 /Fit] >> >>',annotation=True))]
        for name,raw in cases:
            with self.subTest(case=name):
                path=self.root/(name+'.pdf');path.write_bytes(raw)
                parsed=subprocess.run(['pdfinfo',str(path)],capture_output=True,text=True,timeout=30)
                self.assertEqual(parsed.returncode,0,parsed.stderr)
                result=api('probe_pdf')(path)
                self.assertEqual(result['page_count'],1)
                self.assertFalse(result['safe_parser'])

    def test_video_requires_server_scene_asset_registration_and_reuse_authorization(self):
        # 기존 파일·검사 callback만으로 재사용 승인을 대신할 수 없다.
        runners=self.video_runners();runners.pop('scene_assets')
        result=self.render('remotion_video',self.props(),runners)
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(result['reason_code'],'scene_asset_unregistered')


    def scene_registry(self, *, sha256=None, origin='reuse'):
        return {'scene-image':api('RegisteredSceneAsset')(
            asset_id='scene-image', path=str(self.image), sha256=sha256 or hashlib.sha256(self.image.read_bytes()).hexdigest(),
            source='user-owned', origin=origin, provenance={'kind':'reuse','record_id':'server-source-1'},
            reuse_request_id='request-1')}

    def scene_authorization(self, **kwargs):
        return dict(authorized=True,reviewed=True,**{k:kwargs['manifest'][k] for k in ('sha256','source','reuse_request_id')})

    def test_registered_scene_reuse_requires_exact_server_hash_source_and_request(self):
        props=self.props()
        for scene in props['scenes']:scene['image_asset_id']='scene-image'
        runners=self.video_runners();runners['scene_assets']=self.scene_registry();runners.pop('reuse_authorization')
        self.assertEqual(self.render('remotion_video',props,runners)['reason_code'],'reuse_not_authorized')
        runners['reuse_authorization']=self.scene_authorization
        result=self.render('remotion_video',props,runners)
        self.assertEqual(result['status'],'completed')
        self.assertEqual([item['asset_id'] for item in result['evidence']['inputs']],['scene-image','scene-image'])
        for field in ('sha256','source','reuse_request_id'):
            with self.subTest(field=field):
                def wrong(**kwargs):return dict(self.scene_authorization(**kwargs),**{field:'wrong'})
                runners['reuse_authorization']=wrong
                self.assertEqual(self.render('remotion_video',props,runners)['status'],'blocked')
        runners['reuse_authorization']=self.scene_authorization
        runners['scene_assets']=self.scene_registry(sha256='0'*64)
        self.assertEqual(self.render('remotion_video',props,runners)['reason_code'],'asset_changed')

    def test_scene_manifest_cannot_register_its_own_provenance_or_swap_file(self):
        props=self.props()
        for scene in props['scenes']:scene['image_asset_id']='scene-image'
        runners=self.video_runners();runners.update(scene_assets=self.scene_registry(),reuse_authorization=self.scene_authorization)
        from dataclasses import FrozenInstanceError
        registration=runners['scene_assets']['scene-image']
        with self.assertRaises(FrozenInstanceError):registration.sha256='0'*64
        with self.assertRaises(TypeError):registration.provenance['record_id']='forged'
        actual_registry=runners['scene_assets']
        runners['scene_assets']={'scene-image':dict(registration.__dict__)}
        self.assertEqual(self.render('remotion_video',props,runners)['reason_code'],'scene_asset_unregistered')
        runners['scene_assets']=actual_registry
        props['scenes'][0]['provenance']={'kind':'reuse','record_id':'model-claim'}
        self.assertEqual(self.render('remotion_video',props,runners)['status'],'blocked')
        props['scenes'][0].pop('provenance')
        other=self.root/'other.png';other.write_bytes(self.image.read_bytes())
        props['scenes'][0]['image']=str(other)
        self.assertEqual(self.render('remotion_video',props,runners)['status'],'blocked')

    def test_scene_generated_provenance_needs_server_generation_authorization(self):
        props=self.props()
        for scene in props['scenes']:scene['image_asset_id']='generated-image'
        asset=api('RegisteredSceneAsset')(asset_id='generated-image',path=str(self.image),sha256=hashlib.sha256(self.image.read_bytes()).hexdigest(),
                source='server-generated',origin='generated',provenance={'kind':'generated','provider_id':'allowed-image-provider','execution_id':'image-generation',
                'policy_revision':'explicit-dept-policy','request_hash':'2'*64})
        runners=self.video_runners();runners['scene_assets']={'generated-image':asset}
        self.assertEqual(self.render('remotion_video',props,runners)['reason_code'],'missing_required_media')
        runners['generation_authorization']=lambda **kw:{'authorized':True,'sha256':asset.sha256,'provenance_hash':asset.provenance_hash}
        self.assertEqual(self.render('remotion_video',props,runners)['status'],'completed')
        # 렌더 중 원본 변경도 기존 provenance로 완료할 수 없다.
        def changing(**kwargs):
            self.image.write_bytes(self.image.read_bytes()+b'changed')
            return {'path':str(self.video),'font_sha256':'1'*64}
        runners['remotion_video']=changing
        self.assertEqual(self.render('remotion_video',props,runners)['reason_code'],'asset_changed')
