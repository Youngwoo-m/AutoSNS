"""고정 로컬 카드 PNG 제작 leaf. 명시 호출 외에는 렌더·프로세스를 실행하지 않는다."""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
from .models import ContractError,thaw

SOURCES=('src/local-card/index.ts','src/local-card/Root.tsx','src/local-card/LocalCard.tsx','package.json','package-lock.json')
HASH=re.compile(r'[0-9a-f]{64}')
MAX_PNG_BYTES=20*1024*1024


def _require(ok,code='invalid_image_spec'):
    if not ok:raise ContractError(code)


def validate_image_spec(spec):
    _require(type(spec) is dict and set(spec)=={'template','title','body','footer'})
    _require(spec['template'] in ('card','steps'))
    def text(value,limit,nonblank=False):
        _require(type(value) is str and len(value)<=limit and '\x00' not in value and (not nonblank or bool(value.strip())))
        try:value.encode('utf-8')
        except UnicodeError:raise ContractError('invalid_image_spec') from None
        return value
    body=spec['body'];_require(type(body) is list and 1<=len(body)<=6)
    return dict(template=spec['template'],title=text(spec['title'],80,True),body=[text(v,120,True) for v in body],footer=text(spec['footer'],120))


def _read(root,path,limit=1024*1024,allow_link=False):
    _require(path.is_relative_to(root),'image_renderer_unsafe')
    for part in (root,*list(path.relative_to(root).parents)[::-1]):
        candidate=part if part==root else root/part
        _require(not candidate.is_symlink(),'image_renderer_unsafe')
    if path.is_symlink():
        _require(allow_link and path.resolve().is_relative_to(root.resolve()),'image_renderer_unsafe')
    _require(path.is_file() and path.stat().st_size<=limit,'image_renderer_unsafe')
    return path.read_bytes()


def local_card_template_hash(root):
    root=Path(root).absolute();digest=hashlib.sha256()
    for source in SOURCES:
        raw=_read(root,root/source)
        digest.update(source.encode()+b'\x00'+raw+b'\x00')
    return digest.hexdigest()


class LocalCardRenderer:
    def __init__(self,code_root,*,expected_template_hash,expected_font_hash,execute=subprocess.run,browser_executable=None):
        _require(isinstance(code_root,(str,Path)) and bool(str(code_root)) and callable(execute),'invalid_image_renderer')
        _require(all(type(v) is str and HASH.fullmatch(v) for v in (expected_template_hash,expected_font_hash)),'invalid_image_renderer')
        self.code_root=Path(code_root).absolute();self.root=self.code_root/'common/remotion-shorts'
        self.expected_template_hash=expected_template_hash;self.expected_font_hash=expected_font_hash;self.execute=execute
        self.browser_executable=browser_executable

    def verify(self):
        try:
            _require(not self.code_root.is_symlink() and not (self.code_root/'common').is_symlink(),'image_renderer_unsafe')
            _require(local_card_template_hash(self.root)==self.expected_template_hash,'image_template_changed')
            font=_read(self.root,self.root/'public/Pretendard-Bold.otf',50*1024*1024)
            _require(font.startswith((b'OTTO',b'\x00\x01\x00\x00')) and hashlib.sha256(font).hexdigest()==self.expected_font_hash,'image_font_changed')
            package=json.loads(_read(self.root,self.root/'package.json'))
            for name in ('remotion','@remotion/cli'):
                version=package['dependencies'][name]
                _require(type(version) is str and re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.\-]+)?',version),'image_dependencies_invalid')
                installed=json.loads(_read(self.root,self.root/'node_modules'/name/'package.json'))
                _require(installed.get('version')==version,'image_dependencies_invalid')
            binary=self.root/'node_modules/.bin/remotion'
            _read(self.root,binary,allow_link=True)
            _require(binary.resolve().is_relative_to((self.root/'node_modules').resolve()),'image_renderer_unsafe')
            return dict(provider_id='local-card',verified=True,reason_code='ok',template_hash=self.expected_template_hash,font_sha256=self.expected_font_hash)
        except Exception:
            return dict(provider_id='local-card',verified=False,reason_code='image_renderer_unavailable',template_hash=None,font_sha256=None)

    def __call__(self,spec,*,owner_account_id,artifact_root):
        spec=validate_image_spec(thaw(spec));_require(owner_account_id in ('personal','dept'))
        _require(not os.path.lexists(self.code_root/'ax-console/data/STOP.json'),'image_stopped')
        _require(self.verify()['verified'],'image_renderer_unavailable')
        _require(isinstance(self.browser_executable,(str,Path)) and bool(str(self.browser_executable)),'image_browser_required')
        browser=Path(self.browser_executable)
        _require(browser.is_absolute() and not browser.is_symlink() and browser.is_file() and os.access(browser,os.X_OK),'image_browser_required')
        lock=self.code_root/'common/shared/axlock.py'
        _read(self.code_root,lock)
        root=Path(artifact_root).absolute()
        for part in (root,*root.parents):
            _require(not part.is_symlink() or str(part) in ('/var','/tmp'),'image_artifact_unsafe')
        root.mkdir(parents=True,exist_ok=True)
        props=root/'props.json';output=root/'output.png'
        _require(not props.exists() and not props.is_symlink() and not output.exists() and not output.is_symlink(),'image_artifact_exists')
        props.write_text(json.dumps(dict(spec=spec,owner_account_id=owner_account_id),ensure_ascii=False,allow_nan=False),encoding='utf-8')
        args=[sys.executable,str(lock),'run','--job','managed-local-card','--res','renderer:local-card','--','npx','--no-install','remotion','still','src/local-card/index.ts','LocalCard',str(output),'--props='+str(props),'--image-format=png','--browser-executable='+str(browser)]
        env={key:os.environ.get(key,'') for key in ('HOME','USER','LOGNAME')}
        env.update(PATH='/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin',LANG='en_US.UTF-8')
        try:
            result=self.execute(args,cwd=self.root,env=env,shell=False,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=120,check=False)
            _require(result.returncode==0,'image_render_failed')
            raw=_read(root,output,MAX_PNG_BYTES)
            _require(len(raw)>=33 and raw[:8]==b'\x89PNG\r\n\x1a\n' and raw[8:16]==b'\x00\x00\x00\rIHDR','image_output_invalid')
            width,height=struct.unpack('>II',raw[16:24]);_require((width,height)==(1080,1350),'image_output_invalid')
            return dict(path=str(output),sha256=hashlib.sha256(raw).hexdigest(),size=len(raw),width=width,height=height)
        except ContractError:raise
        except Exception:raise ContractError('image_render_failed') from None
