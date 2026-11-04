import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from common.operations.models import ContractError
from common.operations.tiktok_media_probe import (
    TikTokMediaProbe, validate_tiktok_video_metadata, MAX_ASSET_BYTES,
    MAX_PROBE_OUTPUT, PROBE_TIMEOUT)

META=dict(width=1080,height=1920,fps=30.0,duration_ms=10000,video_codec='h264',audio_codec='aac')


def probe_json(**over):
    value=dict(streams=[dict(index=0,codec_type='video',codec_name='h264',width=1080,height=1920,avg_frame_rate='30/1',r_frame_rate='30/1',duration='10.000'),dict(index=1,codec_type='audio',codec_name='aac',duration='10.000')],format=dict(format_name='mov,mp4,m4a,3gp,3g2,mj2',duration='10.000'))
    value.update(over)
    return value


class MediaProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.executable=Path(self.temp.name)/'trusted-ffprobe'
        self.executable.write_bytes(b'not executed fixture');self.executable.chmod(0o700)
        self.calls=[];self.paths=[];self.output=json.dumps(probe_json()).encode()
        def runner(command,**options):
            self.calls.append((command,options));path=Path(command[-1]);self.paths.append(path)
            self.assertEqual(path.read_bytes(),b'local selected mp4 bytes')
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(path.parent.stat().st_mode&0o777,0o700)
            return self.output
        self.runner=runner
        self.probe=TikTokMediaProbe(str(self.executable),runner=runner)
    def inspect(self):return self.probe.inspect(b'local selected mp4 bytes')
    def invalid(self,fn,code='tiktok_invalid_video_metadata'):
        with self.assertRaises(ContractError) as caught:fn()
        self.assertEqual(str(caught.exception),code)
    def test_default_and_constructor_are_inert(self):
        with patch('subprocess.Popen',side_effect=AssertionError('no process')),patch('tempfile.TemporaryDirectory',side_effect=AssertionError('no temporary files')):
            default=TikTokMediaProbe();self.invalid(lambda:default.inspect(b'bytes'),'tiktok_media_probe_unconfigured')
            configured=TikTokMediaProbe('/nonexistent/trusted-ffprobe',runner=self.runner)
            self.assertNotIn('/nonexistent',repr(configured))
        self.assertEqual(self.calls,[])
    def test_actual_probe_response_fixed_command_private_file_and_cleanup(self):
        with patch.dict(os.environ,{'API_KEY':'private-secret','HTTPS_PROXY':'http://proxy.invalid'}):
            self.assertEqual(self.inspect(),META)
        command,options=self.calls[0]
        self.assertEqual(command[0],str(self.executable.resolve()))
        self.assertEqual(command[command.index('-protocol_whitelist')+1],'file')
        self.assertEqual(command[command.index('-format_whitelist')+1],'mov')
        self.assertEqual(command[command.index('-enable_drefs')+1],'0')
        self.assertEqual(options,{'timeout':PROBE_TIMEOUT,'max_output_bytes':MAX_PROBE_OUTPUT,'env':{'LANG':'C','LC_ALL':'C'}})
        self.assertTrue(all(not path.exists() and not path.parent.exists() for path in self.paths))
    def test_pure_validation_bounds_known_video_and_observed_audio(self):
        for codec in ('h264','hevc','vp8','vp9'):
            self.assertEqual(validate_tiktok_video_metadata({**META,'video_codec':codec})['video_codec'],codec)
        for codec in (None,'aac','opus','mp3','pcm_s16le'):
            self.assertEqual(validate_tiktok_video_metadata({**META,'audio_codec':codec})['audio_codec'],codec)
        no_audio={k:v for k,v in META.items() if k!='audio_codec'}
        self.assertIsNone(validate_tiktok_video_metadata(no_audio)['audio_codec'])
        for changes in ({'width':360,'height':4096,'fps':23,'duration_ms':1},{'fps':60,'duration_ms':600000}):
            self.assertIsInstance(validate_tiktok_video_metadata({**META,**changes}),dict)
        invalid=[{'width':359},{'height':4097},{'width':True},{'fps':22.999},{'fps':60.001},{'fps':float('nan')},{'fps':float('inf')},{'fps':10**1000},{'fps':True},{'duration_ms':0},{'duration_ms':600001},{'duration_ms':10.1},{'video_codec':'av1'},{'audio_codec':'AAC'},{'audio_codec':'codec\nprivate'},{'extra':'unknown'}]
        for changes in invalid:
            with self.subTest(changes=changes):self.invalid(lambda:validate_tiktok_video_metadata({**META,**changes}))
    def test_rational_fps_decimal_rounding_silent_video(self):
        value=probe_json();value['streams']=value['streams'][:1]
        value['streams'][0].update(avg_frame_rate='30000/1001',r_frame_rate='30000/1001',duration='1.000001')
        value['format']['duration']='1.000001';self.output=json.dumps(value).encode()
        observed=self.inspect()
        self.assertAlmostEqual(observed['fps'],30000/1001);self.assertEqual(observed['duration_ms'],1001);self.assertIsNone(observed['audio_codec'])
    def test_ffprobe_default_empty_programs_and_stream_groups(self):
        value=probe_json(programs=[],stream_groups=[])
        value['streams'][0]['duration']='32.033333'
        value['streams'][1]['duration']='32.056009'
        value['format']['duration']='32.056009'
        self.output=json.dumps(value).encode()
        self.assertEqual(self.inspect(),{**META,'duration_ms':32057})
        for changes in ({'programs':[{}]},{'stream_groups':[{}]},{'programs':{}},
                        {'stream_groups':None},{'unknown':[]}):
            self.output=json.dumps({**value,**changes}).encode()
            with self.subTest(changes=changes):self.invalid(self.inspect)
        for optional in ('programs','stream_groups'):
            self.output=json.dumps(probe_json(**{optional:[]})).encode()
            self.assertEqual(self.inspect(),META)

    def test_structural_stream_format_duration_and_fps_errors(self):
        invalid=[]
        value=probe_json();value['streams'].append(dict(value['streams'][0],index=2));invalid.append(value)
        value=probe_json();value['streams'][0]['codec_type']='subtitle';invalid.append(value)
        value=probe_json();value['streams'][1]['index']=0;invalid.append(value)
        value=probe_json();value['streams'][1].pop('codec_name');invalid.append(value)
        value=probe_json();value['format']['format_name']='matroska,webm';invalid.append(value)
        for duration in ('NaN','Infinity','0','-1','600.0001','not-duration'):
            value=probe_json();value['format']['duration']=duration;invalid.append(value)
        value=probe_json();value['streams'][1]['duration']='11.0';invalid.append(value)
        for fps in ('0/0','30/0','not-fps','30','22/1','61/1','30000/1000000'):
            value=probe_json();value['streams'][0]['avg_frame_rate']=fps;invalid.append(value)
        for value in invalid:
            with self.subTest(value=value):
                self.output=json.dumps(value).encode();self.invalid(self.inspect)
                self.assertFalse(self.paths[-1].exists());self.assertFalse(self.paths[-1].parent.exists())
    def test_untrusted_raw_and_bad_executable_never_run(self):
        for raw in (b'',bytearray(b'x'),'https://untrusted/video.mp4',str(self.executable),None):
            self.invalid(lambda:self.probe.inspect(raw))
        with patch('common.operations.tiktok_media_probe.MAX_ASSET_BYTES',3):self.invalid(lambda:self.probe.inspect(b'four'))
        self.assertEqual(self.calls,[])
        self.invalid(lambda:TikTokMediaProbe('/nonexistent/private').inspect(b'x'),'tiktok_media_probe_failed')
        for path in ('ffprobe','https://server/ffprobe'):
            self.invalid(lambda:TikTokMediaProbe(path),'tiktok_media_probe_unconfigured')
    def test_malicious_json_nonfinite_duplicate_and_oversize_clean_up(self):
        for raw in (b'{"streams":[],"streams":[],"format":{}}',b'{"streams":[],"format":{"duration":NaN}}',b'\xff',b'[]',b'x'*(MAX_PROBE_OUTPUT+1),b'{"streams":[],"format":{}}'):
            self.output=raw;self.invalid(self.inspect);self.assertFalse(self.paths[-1].parent.exists())
    def test_runner_failure_is_redacted_and_private_temp_removed(self):
        seen=[]
        def failing(command,**options):seen.append(Path(command[-1]));raise TimeoutError('private path and token')
        failed=TikTokMediaProbe(str(self.executable),runner=failing)
        self.invalid(lambda:failed.inspect(b'bytes'),'tiktok_media_probe_failed')
        self.assertFalse(seen[0].exists());self.assertFalse(seen[0].parent.exists())


if __name__=='__main__':unittest.main()
