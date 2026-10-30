"""서버가 등록한 미디어 leaf만 실행한다. 모델 자료는 코드로 실행하지 않는다.

기본 등록은 비어 있다. Voicebox client/검토자/템플릿 hash는 서버 구성에서만
주입한다. legacy CLI를 import하거나 Voicebox 수명 주기를 제어하지 않는다.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .models import ContractError, thaw, freeze

MAX_ASSET_BYTES = 100 * 1024 * 1024
MAX_CONTENT_ASSET_BYTES = 500 * 1024 * 1024
KINDS = frozenset(('reuse_image', 'voicebox_audio', 'remotion_video', 'pdf_document'))
VOICE_LABEL = 'AI 합성 음성(본인 목소리 복제)'


def _require(ok, reason='invalid_media_manifest'):
    if not ok:
        raise ContractError(reason)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(value):
    return isinstance(value, str) and bool(re.fullmatch('[0-9a-f]{64}', value))


def _path(root, value, *, exists=True):
    _require(isinstance(value, (str, Path)) and bool(str(value)), 'unsafe_artifact_path')
    root = Path(root).absolute()
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    _require(not root.is_symlink() and path.resolve().is_relative_to(root.resolve()), 'unsafe_artifact_path')
    current = path
    while current != root and current != current.parent:
        _require(not current.is_symlink(), 'unsafe_artifact_path')
        current = current.parent
    if exists:
        _require(path.is_file(), 'missing_required_media')
        _require(path.stat().st_size <= MAX_ASSET_BYTES, 'media_too_large')
    return path


def _asset(root, value, media_type):
    path = _path(root, value)
    raw = path.read_bytes()
    valid = ((media_type == 'application/pdf' and raw.startswith(b'%PDF-') and b'%%EOF' in raw[-2048:])
             or (media_type == 'audio/wav' and raw[:4] == b'RIFF' and raw[8:12] == b'WAVE')
             or (media_type == 'video/mp4' and len(raw) >= 12 and raw[4:8] == b'ftyp')
             or (media_type == 'image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n'))
             or (media_type == 'image/jpeg' and raw.startswith(b'\xff\xd8\xff'))
             or (media_type == 'image/webp' and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP'))
    _require(valid, 'unsupported_media')
    return dict(path=str(path), filename=path.name, media_type=media_type, size=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def _finite_positive(value):
    return type(value) in (float, int) and math.isfinite(value) and value > 0


def probe_media(path):
    """ffprobe 실측만 사용한다. 모델이 적은 duration을 읽지 않는다."""
    completed = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                                'stream=codec_type,width,height:format=duration', '-of', 'json', str(path)],
                               capture_output=True, text=True, timeout=30, shell=False)
    _require(completed.returncode == 0, 'media_probe_failed')
    data = json.loads(completed.stdout)
    streams = data.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video'), {})
    return dict(seconds=float(data['format']['duration']), width=video.get('width'), height=video.get('height'),
                has_audio=any(s.get('codec_type') == 'audio' for s in streams))


def probe_pdf(path):
    """pdfinfo는 페이지 수 관측기다. 객체 안전성 검사기로 취급하지 않는다.

    현재 배포에는 PDF 객체/name/action을 해석해 검사하는 파서가 등록되어
    있지 않다. #xx name/ObjStm/비 JS action을 raw token으로 추측하지 않고
    정상 문서도 safe_parser=False로 둔다. 실제 안전 객체 검사기가 설치·등록되기
    전 ContentStore ingest와 기본 PDF 렌더 완료는 차단되는 것이 정상이다.
    """
    result = subprocess.run(['pdfinfo', str(path)], capture_output=True, text=True, timeout=30, shell=False)
    _require(result.returncode == 0, 'pdf_parser_failed')
    fields = dict(line.split(':', 1) for line in result.stdout.splitlines() if ':' in line)
    encrypted = not fields.get('Encrypted', '').strip().startswith('no')
    return dict(page_count=int(fields.get('Pages', '0').strip()), encrypted=encrypted,
                safe_parser=False, parser='pdfinfo', reason_code='pdf_object_inspection_unavailable')


def _strings(data, fields):
    return all(isinstance(data.get(k), str) and len(data[k]) <= 200000 and '\x00' not in data[k] for k in fields)


@dataclass(frozen=True)
class RegisteredSceneAsset:
    """서버가 검증·동결한 자산 등록. 모델 JSON/HTTP에서 생성하지 않는다."""
    asset_id: str
    path: str
    sha256: str
    source: str
    origin: str
    provenance: Mapping
    reuse_request_id: str | None = None

    def __post_init__(self):
        _require(all(isinstance(v, str) and v for v in (self.asset_id, self.path, self.source))
                 and Path(self.path).is_absolute() and _hash(self.sha256), 'invalid_scene_registration')
        _require(self.origin in ('reuse', 'generated') and isinstance(self.provenance, Mapping), 'invalid_scene_registration')
        if self.origin == 'reuse':
            _require(isinstance(self.reuse_request_id, str) and bool(self.reuse_request_id)
                     and set(self.provenance) == {'kind', 'record_id'} and self.provenance.get('kind') == 'reuse'
                     and isinstance(self.provenance.get('record_id'), str) and bool(self.provenance['record_id']), 'invalid_scene_registration')
        else:
            _require(set(self.provenance) == {'kind', 'provider_id', 'execution_id', 'policy_revision', 'request_hash'}
                     and self.provenance.get('kind') == 'generated'
                     and all(isinstance(v, str) and v for v in self.provenance.values())
                     and _hash(self.provenance['request_hash']) and self.reuse_request_id is None, 'invalid_scene_registration')
        object.__setattr__(self, 'provenance', freeze(thaw(self.provenance)))

    @property
    def provenance_hash(self):
        return hashlib.sha256(json.dumps(thaw(self.provenance), sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _authorize_reuse(manifest, asset, authorize):
    _require(callable(authorize), 'reuse_not_authorized')
    auth = authorize(manifest=thaw(manifest), asset=dict(asset))
    _require(isinstance(auth, Mapping) and auth.get('authorized') is True and auth.get('reviewed') is True
             and all(auth.get(k) == manifest[k] for k in ('sha256', 'source', 'reuse_request_id')), 'reuse_not_authorized')


def _validate_scene_assets(manifest, root, runners):
    registry = runners.get('scene_assets')
    _require(isinstance(registry, Mapping), 'scene_asset_unregistered')
    records = []
    for scene in manifest['scenes']:
        asset_id = scene.get('image_asset_id')
        _require(isinstance(asset_id, str) and bool(asset_id), 'scene_asset_unregistered')
        registered = registry.get(asset_id)
        _require(isinstance(registered, RegisteredSceneAsset) and registered.asset_id == asset_id, 'scene_asset_unregistered')
        path = _path(root, scene['image'])
        _require(path.resolve() == _path(root, registered.path).resolve(), 'scene_asset_mismatch')
        mime = 'video/mp4' if scene['kind'] in ('clip', 'dioclip') else {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(path.suffix.lower())
        asset = _asset(root, path, mime)
        _require(asset['sha256'] == registered.sha256, 'asset_changed')
        if registered.origin == 'reuse':
            reuse = dict(path=registered.path, sha256=registered.sha256, source=registered.source, reuse_request_id=registered.reuse_request_id)
            _authorize_reuse(reuse, asset, runners.get('reuse_authorization'))
        else:
            authorize = runners.get('generation_authorization')
            _require(callable(authorize), 'missing_required_media')
            proof = authorize(registration=registered, asset=dict(asset))
            _require(isinstance(proof, Mapping) and proof.get('authorized') is True
                     and proof.get('sha256') == registered.sha256 and proof.get('provenance_hash') == registered.provenance_hash, 'generation_not_authorized')
        records.append(dict(asset_id=registered.asset_id, path=registered.path, sha256=registered.sha256,
                            source=registered.source, origin=registered.origin, provenance=thaw(registered.provenance),
                            provenance_hash=registered.provenance_hash, reuse_request_id=registered.reuse_request_id))
    return records


def _video_manifest(manifest, root):
    allowed = {'exam', 'field', 'source', 'footer', 'disclosure', 'voice', 'scenes', 'output'}
    _require(not set(manifest)-allowed and _strings(manifest, ('exam', 'field', 'source', 'footer', 'disclosure')))
    _require('AI 합성 음성' in manifest['disclosure'], 'synthetic_disclosure_required')
    scenes = manifest.get('scenes')
    _require(isinstance(scenes, (list, tuple)) and 1 <= len(scenes) <= 30)
    _require(2 <= sum(s.get('kind') in ('diorama', 'dioclip') for s in scenes if isinstance(s, Mapping)) <= 3)
    _require(all(isinstance(s, Mapping) for s in scenes))
    total = 0
    for scene in scenes:
        _require(not set(scene)-{'title', 'caption', 'image', 'kind', 'audio', 'overlay', 'captionSize', 'seconds', 'image_asset_id'})
        _require(_strings(scene, ('title', 'caption', 'image')) and scene['kind'] in ('diorama', 'dioclip', 'diagram', 'clip'))
        _require(_finite_positive(scene.get('seconds')))
        total += scene['seconds']
        _path(root, scene['image'])
        for key in ('audio', 'overlay'):
            if scene.get(key):
                _path(root, scene[key])
        if 'captionSize' in scene:
            _require(type(scene['captionSize']) is int and 12 <= scene['captionSize'] <= 100)
    _require(total <= 20.0, 'duration_exceeded')
    if manifest.get('voice'):
        _path(root, manifest['voice'])
    else:
        _require(all(s.get('audio') for s in scenes), 'audio_required')
    if 'output' in manifest:
        _path(root, manifest['output'], exists=False)
    return thaw(manifest)


def render_registered_media(kind: str, manifest: Mapping, *, artifact_root: Path, runners: Mapping) -> dict:
    """서버 registry에 없는 기능/검사기는 완료 불가. 결과는 불변 자산 ingest 자료다."""
    try:
        _require(kind in KINDS, 'missing_required_media')
        _require(isinstance(manifest, Mapping) and isinstance(runners, Mapping))
        root = Path(artifact_root).absolute()
        _require(root.is_dir() and not root.is_symlink(), 'unsafe_artifact_path')
        manifest = thaw(manifest)
        evidence = {'kind': kind}
        if kind == 'reuse_image':
            _require(set(manifest) == {'path', 'sha256', 'source', 'reuse_request_id'})
            _require(_hash(manifest['sha256']) and _strings(manifest, ('source', 'reuse_request_id'))
                     and manifest['source'] and manifest['reuse_request_id'])
            path = _path(root, manifest['path'])
            media_type = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}.get(path.suffix.lower())
            asset = _asset(root, path, media_type)
            _require(asset['sha256'] == manifest['sha256'], 'asset_changed')
            _authorize_reuse(manifest, asset, runners.get('reuse_authorization'))
            evidence.update(source=manifest['source'], reuse_request_id=manifest['reuse_request_id'], reviewed=True)
        else:
            leaf = runners.get(kind)
            _require(callable(leaf), 'missing_required_media')
            if kind == 'remotion_video':
                manifest = _video_manifest(manifest, root)
                evidence['inputs'] = _validate_scene_assets(manifest, root, runners)
            elif kind == 'voicebox_audio':
                _require(not set(manifest)-{'text', 'seed', 'output'} and _strings(manifest, ('text',)) and manifest['text'].strip())
                _require(type(manifest.get('seed', 14005)) is int)
                if 'output' in manifest:
                    _path(root, manifest['output'], exists=False)
            else:
                _require(not set(manifest)-{'title', 'body', 'output'} and _strings(manifest, ('title', 'body')))
                if 'output' in manifest:
                    _path(root, manifest['output'], exists=False)
            rendered = leaf(manifest=manifest, artifact_root=root)
            _require(isinstance(rendered, Mapping), 'invalid_media_result')
            _require(rendered.get('status') not in ('blocked', 'error'), rendered.get('reason_code') or 'media_render_failed')
            asset = _asset(root, rendered.get('path'), {'voicebox_audio': 'audio/wav', 'remotion_video': 'video/mp4', 'pdf_document': 'application/pdf'}[kind])
            if kind == 'pdf_document':
                parsed = runners.get('pdf_probe', probe_pdf)(Path(asset['path']))
                count = parsed.get('page_count')
                _require(parsed.get('safe_parser') is True and parsed.get('encrypted') is False
                         and type(count) is int and 1 <= count <= 10000, 'pdf_parser_failed')
                inspect = runners.get('inspect_pdf_page')
                _require(callable(inspect), 'pdf_pages_unchecked')
                pages = []
                for page_number in range(1, count+1):
                    check = inspect(path=Path(asset['path']), sha256=asset['sha256'], page_number=page_number)
                    _require(isinstance(check, Mapping) and check.get('checked') is True and check.get('page_number') == page_number, 'pdf_pages_unchecked')
                    frame = _path(root, check.get('rendered_path'))
                    pages.append({'page_number': page_number, 'checked': True, 'rendered_sha256': _sha(frame)})
                evidence.update(parser=thaw(parsed), pages=pages)
            else:
                measured = runners.get('probe', probe_media)(Path(asset['path']))
                _require(isinstance(measured, Mapping) and _finite_positive(measured.get('seconds')), 'media_probe_failed')
                _require(measured['seconds'] <= 20.0, 'duration_exceeded')
                evidence['probe'] = thaw(measured)
                if kind == 'voicebox_audio':
                    _require(rendered.get('voice_label') == VOICE_LABEL, 'synthetic_disclosure_required')
                    inspect = runners.get('inspect_audio')
                    _require(callable(inspect), 'audio_unchecked')
                    check = inspect(asset=dict(asset), manifest=manifest, probe=measured)
                    _require(isinstance(check, Mapping) and all(check.get(k) is True for k in ('checked', 'script_matches', 'intelligible')), 'audio_unchecked')
                    evidence.update(voice_label=VOICE_LABEL, audio_checked=True)
                else:
                    _require((measured.get('width'), measured.get('height')) == (1080, 1920) and measured.get('has_audio') is True, 'video_dimensions_or_audio')
                    _require(_hash(rendered.get('font_sha256')), 'font_unchecked')
                    inspect = runners.get('inspect_video')
                    _require(callable(inspect), 'video_unchecked')
                    check = inspect(asset=dict(asset), manifest=manifest, probe=measured)
                    _require(isinstance(check, Mapping) and all(check.get(k) is True for k in ('audio_checked', 'font_checked', 'disclosure_checked')), 'video_unchecked')
                    scenes = check.get('scenes')
                    _require(isinstance(scenes, (list, tuple)) and len(scenes) == len(manifest['scenes'])
                             and all(isinstance(s, Mapping) and s.get('index') == i and s.get('checked') is True for i, s in enumerate(scenes, 1)), 'video_scenes_unchecked')
                    evidence.update(font_sha256=rendered['font_sha256'], scenes=thaw(scenes), audio_checked=True, font_checked=True, disclosure=manifest['disclosure'])
        # 검사 도중 입력/산출물 변경도 완료하지 않는다.
        for item in evidence.get('inputs', ()):
            _require(_sha(_path(root, item['path'])) == item['sha256'], 'asset_changed')
        _require(_sha(Path(asset['path'])) == asset['sha256'], 'asset_changed')
        asset['evidence'] = dict(evidence)
        return dict(status='completed', assets=[asset], evidence=evidence)
    except ContractError as exc:
        return dict(status='blocked', reason_code=exc.code, assets=[])
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.SubprocessError):
        return dict(status='blocked', reason_code='media_validation_failed', assets=[])


class VoiceboxAudioRunner:
    """이미 준비된 Voicebox의 generate/audio leaf. up/down/kill/fallback 없음.

    client.ready(), client.generate(**body), client.wait_completed(id) (필요할 때),
    client.audio(id)->bytes는 서버가 고정한 loopback client의 메서드다.
    """
    def __init__(self, client, *, profile_id):
        _require(isinstance(profile_id, str) and bool(profile_id), 'invalid_voicebox_registration')
        self.client, self.profile_id = client, profile_id

    def __call__(self, *, manifest, artifact_root):
        _require(self.client.ready() is True, 'voicebox_unavailable')
        generated = self.client.generate(profile_id=self.profile_id, text=manifest['text'], language='ko',
                                         engine='qwen', model_size='0.6B', seed=manifest.get('seed', 14005),
                                         normalize=True, max_chunk_chars=250)
        if generated.get('status') != 'completed':
            generated = self.client.wait_completed(generated['id'])
        _require(generated.get('status') == 'completed' and isinstance(generated.get('id'), str), 'voicebox_generation_failed')
        raw = self.client.audio(generated['id'])
        _require(isinstance(raw, bytes) and len(raw) <= MAX_ASSET_BYTES, 'media_too_large')
        path = _path(artifact_root, manifest.get('output', 'voice.wav'), exists=False)
        _require(not path.exists(), 'artifact_already_exists')
        with path.open('xb') as stream:
            stream.write(raw)
        return dict(path=str(path), voice_label=VOICE_LABEL, generation_id=generated['id'])


def template_hash(root):
    """검토한 Remotion 코드/설정/lockfile 전체를 고정한다(node_modules 제외)."""
    root = Path(root)
    rows = []
    for path in sorted(root.rglob('*')):
        if 'node_modules' in path.parts or '.git' in path.parts:
            continue
        _require(not path.is_symlink(), 'unsafe_template_path')
        if path.is_file():
            rows.append((str(path.relative_to(root)), _sha(path)))
    return hashlib.sha256(json.dumps(rows, separators=(',', ':')).encode()).hexdigest()


class RemotionVideoRunner:
    """기존 SurveyShort leaf 명령. 모델은 props schema 자료만 전달한다."""
    def __init__(self, template_root, *, template_hash, font_path, spawn=subprocess.run,
                 scene_assets=None, reuse_authorization=None, generation_authorization=None):
        self.root, self.expected_hash = Path(template_root).absolute(), template_hash
        self.font_path, self.spawn = Path(font_path), spawn
        _require(_hash(template_hash) and self.font_path.is_file(), 'invalid_remotion_registration')
        self.font_hash = _sha(self.font_path)
        self.scene_registry = {'scene_assets': freeze(dict(scene_assets or {})), 'reuse_authorization': reuse_authorization,
                               'generation_authorization': generation_authorization}

    def __call__(self, *, manifest, artifact_root):
        _require(template_hash(self.root) == self.expected_hash and _sha(self.font_path) == self.font_hash, 'template_changed')
        props = _video_manifest(manifest, artifact_root)
        inputs = _validate_scene_assets(props, artifact_root, self.scene_registry)
        output = _path(artifact_root, props.pop('output', 'short.mp4'), exists=False)
        _require(not output.exists(), 'artifact_already_exists')
        with tempfile.TemporaryDirectory(prefix='autosns-remotion-') as directory:
            public = Path(directory)
            shutil.copyfile(self.font_path, public/'Pretendard-Bold.otf')
            if props.get('voice'):
                src = _path(artifact_root, props['voice']);name = 'voice'+src.suffix
                shutil.copyfile(src, public/name);props['voice'] = name
            for index, scene in enumerate(props['scenes'], 1):
                scene.pop('image_asset_id', None)
                for key in ('image', 'audio', 'overlay'):
                    if scene.get(key):
                        src = _path(artifact_root, scene[key]);name = f's{index}-{key}{src.suffix}'
                        shutil.copyfile(src, public/name)
                        if key == 'image':
                            _require(_sha(public/name) == inputs[index-1]['sha256'], 'asset_changed')
                        scene[key] = name
            props_path = public/'_props.json'
            props_path.write_text(json.dumps(props, ensure_ascii=False, allow_nan=False))
            args = ['npx', '--no-install', 'remotion', 'render', 'src/survey-short/index.ts', 'SurveyShort', str(output),
                    f'--props={props_path}', f'--public-dir={public}', '--log=error']
            result = self.spawn(args, cwd=str(self.root), capture_output=True, text=True, timeout=900, shell=False,
                                env={'PATH': '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin', 'LANG': 'en_US.UTF-8'})
            _require(result.returncode == 0 and output.is_file(), 'remotion_render_failed')
        return dict(path=str(output), font_sha256=self.font_hash)


class PdfDocumentRunner:
    """서버 등록 PDF renderer에는 텍스트와 지정 출력 경로만 넘긴다."""
    def __init__(self, renderer):
        _require(callable(renderer), 'invalid_pdf_registration')
        self.renderer = renderer

    def __call__(self, *, manifest, artifact_root):
        path = _path(artifact_root, manifest.get('output', 'document.pdf'), exists=False)
        _require(not path.exists(), 'artifact_already_exists')
        self.renderer(title=manifest['title'], body=manifest['body'], output=path)
        return {'path': str(path)}
