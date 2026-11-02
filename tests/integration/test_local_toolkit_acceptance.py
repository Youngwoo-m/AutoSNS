"""배포 보호 gate는 자체 fixture, 제품 webroot는 optional overlay/추적 파일 사용."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
OAUTH_MANIFEST=ROOT/'.superpowers/sdd/2026-11-01-sns-oauth-connections/web-artifacts/manifest.json'
MANIFEST=ROOT/'.superpowers/sdd/2026-10-31-local-sns-toolkit/web-artifacts/manifest.json'
def overlay(webroot,manifest,*,source_root=ROOT):
    for entry in manifest['entries']:
        actual=hashlib.sha256((webroot/Path(entry['target']).name).read_bytes()).hexdigest()
        if actual not in (entry['original_sha256'],entry['artifact_sha256']):raise ValueError('held baseline mismatch')
        if hashlib.sha256((source_root/entry['artifact']).read_bytes()).hexdigest()!=entry['artifact_sha256']:raise ValueError('artifact mismatch')
    for entry in manifest.get('new_modules',[]):
        if hashlib.sha256((source_root/entry['source']).read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('module mismatch')
    for entry in manifest.get('new_modules',[]):shutil.copyfile(source_root/entry['source'],webroot/Path(entry['target']).name)
    for entry in manifest['entries']:shutil.copyfile(source_root/entry['artifact'],webroot/Path(entry['target']).name)
def product_webroot(webroot):
    shutil.copytree(ROOT/'ax-console/app/web',webroot)
    manifest=OAUTH_MANIFEST if OAUTH_MANIFEST.exists() else MANIFEST
    if not (webroot/'account_navigation.js').exists() and manifest.exists():overlay(webroot,json.loads(manifest.read_text()))
class ProtectedAcceptance(unittest.TestCase):
    def fixture(self,root):
        web=root/'web';web.mkdir();art=root/'art';art.mkdir();entries=[]
        for name in ('app.js','index.html'):
            old=('old '+name).encode();desired=('desired '+name).encode()
            (web/name).write_bytes(old);(art/name).write_bytes(desired)
            entries.append(dict(target='web/'+name,artifact='art/'+name,original_sha256=hashlib.sha256(old).hexdigest(),artifact_sha256=hashlib.sha256(desired).hexdigest()))
        return web,dict(entries=entries)
    def test_verified_overlay_accepts_old_and_already_deployed_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);web,manifest=self.fixture(root)
            overlay(web,manifest,source_root=root);overlay(web,manifest,source_root=root)
            self.assertEqual((web/'app.js').read_text(),'desired app.js')
    def test_manifest_original_hash_mismatch_rejected_without_partial_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);web,manifest=self.fixture(root);before=(web/'app.js').read_bytes()
            manifest['entries'][-1]['original_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'baseline mismatch'):overlay(web,manifest,source_root=root)
            self.assertEqual((web/'app.js').read_bytes(),before)
    def test_artifact_mismatch_rejected_without_partial_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);web,manifest=self.fixture(root);before=(web/'app.js').read_bytes()
            (root/'art/index.html').write_text('tampered')
            with self.assertRaisesRegex(ValueError,'artifact mismatch'):overlay(web,manifest,source_root=root)
            self.assertEqual((web/'app.js').read_bytes(),before)
    def test_product_sources_work_without_mandatory_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            web=Path(temp)/'web';product_webroot(web)
            self.assertIn('createToolkitPanel',(web/'app.js').read_text())
