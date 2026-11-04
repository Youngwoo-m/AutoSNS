"""TikTok용 선택 MP4의 로컬 기술 검사. 업로드·공개·계정 허가는 아니다.

공식 영상 기준(크기/프레임률/코덱):
https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide
360..4096 px, 23..60 fps, H264/HEVC/VP8/VP9를 검사한다. 100MiB와
1..600000ms는 내부 준비 한도이며 제작자별 게시 가능 길이를 대신하지 않는다.
공식 문서에 오디오 코덱 한도가 없으므로 관측한 코덱명만 보존한다.
실행 파일은 서버의 신뢰하는 절대 경로로만 주입한다. 기본값은 실행을 차단한다.
ffprobe 옵션: https://ffmpeg.org/ffprobe.html
외부 트랙·demuxer 제한: https://ffmpeg.org/ffmpeg-formats.html
"""
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile
import time

from common.operations.models import ContractError

MAX_ASSET_BYTES=100*1024*1024
MAX_PROBE_OUTPUT=64*1024
PROBE_TIMEOUT=15
_KEYS={'width','height','fps','duration_ms','video_codec','audio_codec'}
_VIDEO_CODECS={'h264','hevc','vp8','vp9'}


def _invalid():
    raise ContractError('tiktok_invalid_video_metadata') from None


def validate_tiktok_video_metadata(value):
    """Validate normalized measured metadata; return a detached six-field dict.

    Missing audio_codec is normalized to None. Codec names outside AAC are
    observations, not claims that TikTok accepts the audio encoding.
    """
    if not isinstance(value,Mapping) or set(value)-_KEYS or not _KEYS-{'audio_codec'}<=set(value):_invalid()
    for key in ('width','height'):
        if type(value[key]) is not int or not 360<=value[key]<=4096:_invalid()
    fps=value['fps']
    if type(fps) not in (int,float) or not 23<=fps<=60 or not math.isfinite(fps):_invalid()
    if type(value['duration_ms']) is not int or not 1<=value['duration_ms']<=600000:_invalid()
    if type(value['video_codec']) is not str or value['video_codec'] not in _VIDEO_CODECS:_invalid()
    audio=value.get('audio_codec')
    if audio is not None:
        import re
        if type(audio) is not str or not re.fullmatch(r'[a-z0-9_]{1,64}',audio):_invalid()
    return dict(width=value['width'],height=value['height'],fps=float(fps),
                duration_ms=value['duration_ms'],video_codec=value['video_codec'],audio_codec=audio)


def _pairs(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('duplicate')
        result[key]=value
    return result


def _constant(_):raise ValueError('constant')


def _duration(value):
    if type(value) is not str or not 0<len(value)<=64:_invalid()
    try:
        duration=Decimal(value)
        if not duration.is_finite() or not 0<duration<=600:_invalid()
        return duration
    except InvalidOperation:_invalid()


def _fps(value):
    if type(value) is not str or len(value)>64:_invalid()
    import re
    if not re.fullmatch(r'[0-9]{1,12}/[0-9]{1,12}',value):_invalid()
    try:
        fps=Fraction(value)
        if not 23<=fps<=60:_invalid()
        return fps
    except (ValueError,ZeroDivisionError):_invalid()


def _normalize(raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_PROBE_OUTPUT:_invalid()
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=_constant)
    except (ValueError,UnicodeError,RecursionError):_invalid()
    if (type(value) is not dict or not {'streams','format'}<=set(value)
            or set(value)-{'streams','format','programs','stream_groups'}):_invalid()
    for optional in ('programs','stream_groups'):
        if optional in value and (type(value[optional]) is not list or value[optional]):_invalid()
    streams=value['streams'];fmt=value['format']
    if type(streams) is not list or not 1<=len(streams)<=2 or type(fmt) is not dict or set(fmt)!={'format_name','duration'}:_invalid()
    if type(fmt['format_name']) is not str or 'mp4' not in fmt['format_name'].split(','):_invalid()
    videos=[];audios=[];indices=[]
    for stream in streams:
        if type(stream) is not dict or set(stream)-{'index','codec_type','codec_name','width','height','avg_frame_rate','r_frame_rate','duration'}:_invalid()
        if type(stream.get('index')) is not int or stream['index']<0 or stream['index'] in indices:_invalid()
        indices.append(stream['index'])
        if stream.get('codec_type')=='video':videos.append(stream)
        elif stream.get('codec_type')=='audio':
            if type(stream.get('codec_name')) is not str:_invalid()
            audios.append(stream)
        else:_invalid()
    if len(videos)!=1 or len(audios)>1:_invalid()
    video=videos[0]
    for name in ('codec_name','width','height','avg_frame_rate'):
        if name not in video:_invalid()
    fps=_fps(video['avg_frame_rate'])
    if 'r_frame_rate' in video:_fps(video['r_frame_rate'])
    duration=_duration(fmt['duration'])
    # Container tails can differ slightly; more than 100ms or one frame of disagreement
    # is unsupported rather than guessed away from measured metadata.
    for stream in streams:
        if 'duration' in stream and abs(_duration(stream['duration'])-duration)>max(Decimal('0.1'),Decimal(fps.denominator)/Decimal(fps.numerator)):_invalid()
    milliseconds=int((duration*1000).to_integral_value(rounding=ROUND_CEILING))
    return validate_tiktok_video_metadata(dict(width=video['width'],height=video['height'],fps=float(fps),
        duration_ms=milliseconds,video_codec=video['codec_name'],audio_codec=audios[0].get('codec_name') if audios else None))


def _run_probe(command,*,timeout,max_output_bytes,env):
    """Bound output while reading; never accumulate an unbounded communicate()."""
    process=None
    try:
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,env=env,close_fds=True,start_new_session=True)
        deadline=time.monotonic()+timeout;output=bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout,selectors.EVENT_READ)
            while selector.get_map():
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError()
                for key,_ in selector.select(remaining):
                    block=os.read(key.fileobj.fileno(),min(8192,max_output_bytes+1-len(output)))
                    if not block:selector.unregister(key.fileobj);continue
                    output.extend(block)
                    if len(output)>max_output_bytes:raise ValueError('output limit')
        remaining=deadline-time.monotonic()
        if remaining<=0 or process.wait(timeout=remaining)!=0:raise ValueError('probe failed')
        return bytes(output)
    finally:
        if process is not None:
            if process.poll() is None:
                try:os.killpg(process.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                process.wait()
            if process.stdout is not None:process.stdout.close()


class TikTokMediaProbe:
    """Explicit inspect(bytes) only. runner(command,timeout,max_output_bytes,env)
    may be injected for isolated tests and must return bounded JSON bytes.
    Constructor never inspects or executes the supplied server-owned path.
    """
    __slots__=('_executable','_runner')
    def __init__(self,executable=None,*,runner=None):
        if executable is not None and (type(executable) is not str or not Path(executable).is_absolute()):
            raise ContractError('tiktok_media_probe_unconfigured')
        if runner is not None and not callable(runner):raise ContractError('tiktok_media_probe_unconfigured')
        self._executable=executable;self._runner=runner or _run_probe
    def __repr__(self):return '<TikTokMediaProbe private>'
    def inspect(self,raw):
        if self._executable is None:raise ContractError('tiktok_media_probe_unconfigured')
        if type(raw) is not bytes or not 0<len(raw)<=MAX_ASSET_BYTES:_invalid()
        try:
            executable=Path(self._executable).resolve(strict=True)
            if not executable.is_file() or not os.access(executable,os.X_OK):raise ValueError()
            with tempfile.TemporaryDirectory(prefix='autosns-tiktok-probe-') as folder:
                path=Path(folder)/'selected.mp4'
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as stream:stream.write(raw)
                command=[str(executable),'-v','error','-max_alloc','16777216',
                    '-protocol_whitelist','file','-format_whitelist','mov','-enable_drefs','0',
                    '-use_absolute_path','0','-max_streams','2',
                    '-probesize','5000000','-analyzeduration','10000000','-show_entries',
                    'stream=index,codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,duration:format=format_name,duration',
                    '-of','json',str(path)]
                output=self._runner(command,timeout=PROBE_TIMEOUT,max_output_bytes=MAX_PROBE_OUTPUT,
                                    env={'LANG':'C','LC_ALL':'C'})
                return _normalize(output)
        except ContractError:raise
        except Exception:raise ContractError('tiktok_media_probe_failed') from None
