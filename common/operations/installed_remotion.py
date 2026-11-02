"""설치된 Remotion SurveyShort 코드를 읽기 전용으로 검증하고 영상 등록만 조립한다.

생성자와 create_registration은 렌더·명령·네트워크를 실행하지 않는다. verify()만 파일을 읽는다.
"""
import hashlib
import json
import os
import re
import stat
from pathlib import Path

from . import production_media
from .models import ContractError
from .production_media import RemotionVideoRunner
from .video_startup import VideoRegistration

PROVIDER_ID = 'remotion-local'
TEMPLATE_ID = 'SurveyShort'
MAX_FONT_BYTES = 50 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
FONT_MAGIC = (b'OTTO', b'\x00\x01\x00\x00')
SOURCES = ('src/survey-short/index.ts', 'src/survey-short/Root.tsx', 'src/survey-short/SurveyShort.tsx',
           'package.json', 'package-lock.json')
PACKAGES = ('remotion', '@remotion/cli')
_HASH = re.compile('[0-9a-f]{64}')
_VERSION = re.compile(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.\-]+)?')


class _Reject(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class InstalledRemotion:
    def __init__(self, code_root, *, expected_template_hash, expected_font_hash, runner_class=RemotionVideoRunner):
        ok = (isinstance(code_root, (str, Path)) and bool(str(code_root)) and callable(runner_class) and
              all(isinstance(value, str) and bool(_HASH.fullmatch(value))
                  for value in (expected_template_hash, expected_font_hash)))
        if not ok:
            raise ContractError('invalid_installed_remotion')
        self.code_root = Path(code_root).absolute()
        self.root = self.code_root/'common'/'remotion-shorts'
        self.font_path = self.root/'public'/'Pretendard-Bold.otf'
        self.expected_template_hash, self.expected_font_hash = expected_template_hash, expected_font_hash
        self.runner_class = runner_class
        self._evidence = None

    def verify(self):
        self._evidence = None
        state = dict(template_hash=None, font_sha256=None, dependencies_available=False)
        try:
            self._check(state)
            reason = 'ok'
        except _Reject as error:
            reason = error.code
        except Exception:  # 경로·내용 원문을 노출하지 않고 닫는다.
            reason = 'verify_failed'
        verified = reason == 'ok'
        if verified:
            self._evidence = (state['template_hash'], state['font_sha256'])
        return dict(provider_id=PROVIDER_ID, template_id=TEMPLATE_ID, verified=verified, reason_code=reason,
                    template_hash=state['template_hash'], font_sha256=state['font_sha256'],
                    dependencies_available=state['dependencies_available'])

    def create_registration(self, *, reuse_authorization, inspect_video, probe, defer_video_review=False):
        if type(defer_video_review) is not bool or not all(callable(value) for value in (reuse_authorization, inspect_video, probe)):
            raise ContractError('invalid_video_registration')
        self._revalidate()

        def factory(scene_assets, reuse_authorization):
            self._revalidate()
            return self.runner_class(self.root, template_hash=self.expected_template_hash, font_path=self.font_path,
                                     scene_assets=scene_assets, reuse_authorization=reuse_authorization)
        return VideoRegistration(factory, reuse_authorization, probe, inspect_video,defer_video_review)

    def _revalidate(self):
        previous = self._evidence
        if previous is None:
            raise ContractError('installed_remotion_unverified')
        result = self.verify()
        if not result['verified']:
            raise ContractError(result['reason_code'])
        if self._evidence != previous:
            raise ContractError('installed_remotion_changed')

    def _lstat(self, path, *, missing, unsafe, allow_final_link=False):
        """code_root 아래 각 구성요소가 심볼릭 링크가 아님을 확인하고 마지막 lstat을 돌려준다."""
        parts = path.relative_to(self.code_root).parts
        current, info = self.code_root, None
        for index, part in enumerate(parts):
            current = current/part
            try:
                info = os.lstat(current)
            except (FileNotFoundError, NotADirectoryError):
                raise _Reject(missing)
            if stat.S_ISLNK(info.st_mode) and not (allow_final_link and index == len(parts)-1):
                raise _Reject(unsafe)
        return info

    def _read(self, path, limit, *, missing, unsafe):
        info = self._lstat(path, missing=missing, unsafe=unsafe)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise _Reject(unsafe)
        try:
            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        except OSError:
            raise _Reject(unsafe)
        with os.fdopen(fd, 'rb') as stream:
            data = stream.read(limit+1)
        if len(data) > limit:
            raise _Reject(unsafe)
        return data

    def _json(self, path, *, missing, unsafe, schema):
        try:
            value = json.loads(self._read(path, MAX_JSON_BYTES, missing=missing, unsafe=unsafe))
        except (ValueError, UnicodeDecodeError):
            raise _Reject(schema)
        if not isinstance(value, dict):
            raise _Reject(schema)
        return value

    def _check(self, state):
        info = self._lstat(self.root, missing='root_missing', unsafe='root_unsafe')
        if not stat.S_ISDIR(info.st_mode):
            raise _Reject('root_unsafe')
        for relative in SOURCES:
            info = self._lstat(self.root/relative, missing='source_missing', unsafe='source_unsafe')
            if not stat.S_ISREG(info.st_mode):
                raise _Reject('source_unsafe')
        font = self._read(self.font_path, MAX_FONT_BYTES, missing='font_missing', unsafe='font_unsafe')
        if not font.startswith(FONT_MAGIC):
            raise _Reject('font_invalid')
        state['font_sha256'] = hashlib.sha256(font).hexdigest()
        if state['font_sha256'] != self.expected_font_hash:
            raise _Reject('font_changed')
        try:
            state['template_hash'] = production_media.template_hash(self.root)
        except ContractError:
            raise _Reject('template_unsafe')
        if state['template_hash'] != self.expected_template_hash:
            raise _Reject('template_changed')
        package = self._json(self.root/'package.json', missing='source_missing', unsafe='source_unsafe',
                             schema='package_schema_unknown')
        declared = package.get('dependencies')
        if not isinstance(declared, dict) or not all(
                isinstance(declared.get(name), str) and _VERSION.fullmatch(declared[name]) for name in PACKAGES):
            raise _Reject('package_schema_unknown')
        self._dependencies({name: declared[name] for name in PACKAGES})
        state['dependencies_available'] = True

    def _dependencies(self, declared):
        modules = self.root/'node_modules'
        info = self._lstat(modules, missing='dependencies_missing', unsafe='dependencies_unsafe')
        if not stat.S_ISDIR(info.st_mode):
            raise _Reject('dependencies_unsafe')
        binary = modules/'.bin'/'remotion'
        info = self._lstat(binary, missing='dependencies_missing', unsafe='dependencies_unsafe', allow_final_link=True)
        if stat.S_ISLNK(info.st_mode):
            try:
                target = binary.resolve(strict=True)
            except (OSError, RuntimeError):
                raise _Reject('dependencies_unsafe')
            if not target.is_relative_to(modules.resolve()) or not target.is_file():
                raise _Reject('dependencies_unsafe')
        elif not stat.S_ISREG(info.st_mode):
            raise _Reject('dependencies_unsafe')
        for name in PACKAGES:
            installed = self._json(modules/name/'package.json', missing='dependencies_missing',
                                   unsafe='dependencies_unsafe', schema='dependencies_invalid')
            version = installed.get('version')
            if not isinstance(version, str):
                raise _Reject('dependencies_invalid')
            if version != declared[name]:
                raise _Reject('dependency_version_mismatch')
