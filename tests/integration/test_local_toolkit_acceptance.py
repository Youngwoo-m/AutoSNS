"""held 보호와 임시 webroot overlay의 무결성 수락."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
MANIFEST=ROOT/'.superpowers/sdd/2026-10-31-local-sns-toolkit/web-artifacts/manifest.json'
def overlay(webroot,manifest):
    # 배포 전 원본과 artifact를 모두 확인한다. 검증 완료 전 복사하지 않는다.
    for entry in manifest['entries']:
        if hashlib.sha256((webroot/Path(entry['target']).name).read_bytes()).hexdigest()!=entry['original_sha256']:raise ValueError('held baseline mismatch')
        if hashlib.sha256((ROOT/entry['artifact']).read_bytes()).hexdigest()!=entry['artifact_sha256']:raise ValueError('artifact mismatch')
    for entry in manifest.get('new_modules',[]):
        if hashlib.sha256((ROOT/entry['source']).read_bytes()).hexdigest()!=entry['sha256']:raise ValueError('module mismatch')
    for entry in manifest.get('new_modules',[]):shutil.copyfile(ROOT/entry['source'],webroot/Path(entry['target']).name)
    for entry in manifest['entries']:shutil.copyfile(ROOT/entry['artifact'],webroot/Path(entry['target']).name)
class ProtectedAcceptance(unittest.TestCase):
    def test_actual_held_bytes_and_verified_overlay(self):
        manifest=json.loads(MANIFEST.read_text())
        with tempfile.TemporaryDirectory() as temp:
            webroot=Path(temp)/'web';shutil.copytree(ROOT/'ax-console/app/web',webroot)
            for entry in manifest['entries']:self.assertEqual(hashlib.sha256((ROOT/entry['target']).read_bytes()).hexdigest(),entry['original_sha256'])
            overlay(webroot,manifest)
            self.assertIn('createToolkitPanel',(webroot/'app.js').read_text())
    def test_manifest_original_hash_mismatch_rejected_without_partial_copy(self):
        manifest=json.loads(MANIFEST.read_text())
        with tempfile.TemporaryDirectory() as temp:
            webroot=Path(temp)/'web';shutil.copytree(ROOT/'ax-console/app/web',webroot);before=(webroot/'app.js').read_bytes();manifest['entries'][-1]['original_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'baseline mismatch'):overlay(webroot,manifest)
            self.assertEqual((webroot/'app.js').read_bytes(),before)
