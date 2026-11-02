import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from common.operations import production_media
from common.operations.installed_remotion import InstalledRemotion
from common.operations.models import ContractError
from common.operations.video_startup import VideoRegistration, validate_video_registration

FONT = b'OTTO' + b'fake-font-body'
VERSION = '4.0.535'


class FakeRunner:
    created = []

    def __init__(self, template_root, **kwargs):
        self.template_root, self.kwargs = template_root, kwargs
        FakeRunner.created.append(self)

    def __call__(self, **kwargs):
        raise AssertionError('registration must not render')


def package(version=VERSION, dependencies=True):
    body = {'name': 'fake'}
    if dependencies:
        body['dependencies'] = {'remotion': version, '@remotion/cli': version}
    return json.dumps(body)


def make_project(base, *, package_text=None, deps=True, font=FONT):
    root = Path(base)/'common'/'remotion-shorts'
    for relative, text in {'src/survey-short/index.ts': 'index', 'src/survey-short/Root.tsx': 'root',
                           'src/survey-short/SurveyShort.tsx': 'short', 'package-lock.json': '{}',
                           'package.json': package() if package_text is None else package_text}.items():
        (root/relative).parent.mkdir(parents=True, exist_ok=True)
        (root/relative).write_text(text)
    if font is not None:
        (root/'public').mkdir()
        (root/'public'/'Pretendard-Bold.otf').write_bytes(font)
    if deps:
        modules = root/'node_modules'
        for name in ('remotion', '@remotion/cli'):
            (modules/name).mkdir(parents=True)
            (modules/name/'package.json').write_text(json.dumps({'version': VERSION}))
        (modules/'@remotion'/'cli'/'remotion-cli.js').write_text('//')
        (modules/'.bin').mkdir()
        os.symlink('../@remotion/cli/remotion-cli.js', modules/'.bin'/'remotion')
    return root


def installed(base, **kwargs):
    root = Path(base)/'common'/'remotion-shorts'
    return InstalledRemotion(base, expected_template_hash=production_media.template_hash(root),
                             expected_font_hash=hashlib.sha256(FONT).hexdigest(), runner_class=FakeRunner, **kwargs)


class InstalledRemotionTests(unittest.TestCase):
    def setUp(self):
        FakeRunner.created = []
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = self.tmp.name

    def register(self, item):
        return item.create_registration(reuse_authorization=lambda *a, **k: True, inspect_video=lambda *a, **k: {},
                                        probe=lambda *a, **k: {})

    def test_constructor_does_no_io_and_validates_hashes(self):
        with mock.patch('os.lstat', side_effect=AssertionError), mock.patch('os.stat', side_effect=AssertionError), \
                mock.patch('builtins.open', side_effect=AssertionError):
            InstalledRemotion('/nonexistent/code', expected_template_hash='a'*64, expected_font_hash='b'*64)
        for bad in ('A'*64, 'a'*63, None):
            with self.assertRaises(ContractError):
                InstalledRemotion(self.base, expected_template_hash=bad, expected_font_hash='b'*64)

    def test_verify_positive_has_exact_shape_without_paths(self):
        make_project(self.base)
        item = installed(self.base)
        result = item.verify()
        self.assertEqual(set(result), {'provider_id', 'template_id', 'verified', 'reason_code', 'template_hash',
                                       'font_sha256', 'dependencies_available'})
        self.assertEqual((result['provider_id'], result['template_id'], result['verified'], result['reason_code'],
                          result['dependencies_available']), ('remotion-local', 'SurveyShort', True, 'ok', True))
        self.assertEqual(result['font_sha256'], hashlib.sha256(FONT).hexdigest())
        self.assertNotIn(self.base, json.dumps(result))

    def test_missing_font_dependencies_and_bin_fail_closed(self):
        with tempfile.TemporaryDirectory() as base:
            make_project(base, font=None)
            result = InstalledRemotion(base, expected_template_hash='a'*64, expected_font_hash='b'*64).verify()
            self.assertEqual((result['verified'], result['reason_code']), (False, 'font_missing'))
        with tempfile.TemporaryDirectory() as base:
            make_project(base, deps=False)
            result = installed(base).verify()
            self.assertEqual((result['verified'], result['reason_code'], result['dependencies_available']),
                             (False, 'dependencies_missing', False))
        root = make_project(self.base)
        item = installed(self.base)
        (root/'node_modules'/'.bin'/'remotion').unlink()
        result = item.verify()
        self.assertEqual((result['verified'], result['reason_code'], result['dependencies_available']),
                         (False, 'dependencies_missing', False))

    def test_changed_template_or_font_is_rejected(self):
        root = make_project(self.base)
        item = installed(self.base)
        (root/'src'/'survey-short'/'SurveyShort.tsx').write_text('changed')
        self.assertEqual(item.verify()['reason_code'], 'template_changed')
        (root/'src'/'survey-short'/'SurveyShort.tsx').write_text('short')
        self.assertTrue(item.verify()['verified'])
        (root/'public'/'Pretendard-Bold.otf').write_bytes(b'OTTO' + b'other')
        self.assertEqual(item.verify()['reason_code'], 'font_changed')
        (root/'public'/'Pretendard-Bold.otf').write_bytes(b'junk')
        self.assertEqual(item.verify()['reason_code'], 'font_invalid')

    def test_symlinks_outside_are_rejected(self):
        outside = Path(self.base)/'outside'
        outside.mkdir()
        (outside/'x.tsx').write_text('x')
        (outside/'evil.js').write_text('//')
        root = make_project(self.base)
        item = installed(self.base)
        source = root/'src'/'survey-short'/'Root.tsx'
        source.unlink()
        os.symlink(outside/'x.tsx', source)
        result = item.verify()
        self.assertEqual((result['verified'], result['reason_code']), (False, 'source_unsafe'))
        self.assertNotIn(self.base, json.dumps(result))
        source.unlink()
        source.write_text('root')
        self.assertTrue(item.verify()['verified'])
        binary = root/'node_modules'/'.bin'/'remotion'
        binary.unlink()
        os.symlink(outside/'evil.js', binary)
        self.assertEqual(item.verify()['reason_code'], 'dependencies_unsafe')

    def test_version_mismatch_and_unknown_schema_fail(self):
        root = make_project(self.base)
        item = installed(self.base)
        (root/'node_modules'/'@remotion'/'cli'/'package.json').write_text(json.dumps({'version': '4.0.1'}))
        self.assertEqual(item.verify()['reason_code'], 'dependency_version_mismatch')
        with tempfile.TemporaryDirectory() as base:
            make_project(base, package_text=package(dependencies=False))
            self.assertEqual(installed(base).verify()['reason_code'], 'package_schema_unknown')
        with tempfile.TemporaryDirectory() as base:
            make_project(base, package_text=package(version='^4.0.535'))
            self.assertEqual(installed(base).verify()['reason_code'], 'package_schema_unknown')

    def test_registration_requires_successful_verify_and_callables(self):
        root = make_project(self.base)
        item = installed(self.base)
        with self.assertRaises(ContractError):
            self.register(item)
        item.verify()
        with self.assertRaises(ContractError):
            item.create_registration(reuse_authorization=None, inspect_video=lambda: 1, probe=lambda: 1)
        (root/'src'/'survey-short'/'index.ts').write_text('changed')
        item.verify()
        with self.assertRaises(ContractError):
            self.register(item)

    def test_registration_does_not_construct_or_spawn_anything(self):
        make_project(self.base)
        item = installed(self.base)
        item.verify()
        with mock.patch('subprocess.run', side_effect=AssertionError), mock.patch('subprocess.Popen', side_effect=AssertionError):
            registration = self.register(item)
        self.assertIsInstance(registration, VideoRegistration)
        validate_video_registration(registration)
        self.assertEqual(FakeRunner.created, [])

    def test_factory_revalidates_and_builds_fixed_runner_only(self):
        root = make_project(self.base)
        item = installed(self.base)
        item.verify()
        registration = self.register(item)
        authorizer = registration.reuse_authorization
        runner = registration.runner_factory(scene_assets={'a': 1}, reuse_authorization=authorizer)
        self.assertEqual(runner.template_root, item.root)
        self.assertEqual(runner.kwargs, dict(template_hash=item.expected_template_hash,
                                             font_path=root/'public'/'Pretendard-Bold.otf',
                                             scene_assets={'a': 1}, reuse_authorization=authorizer))
        (root/'src'/'survey-short'/'Root.tsx').write_text('changed')
        with self.assertRaises(ContractError):
            registration.runner_factory(scene_assets={}, reuse_authorization=authorizer)
        self.assertEqual(len(FakeRunner.created), 1)


if __name__ == '__main__':
    unittest.main()
