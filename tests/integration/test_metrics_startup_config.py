"""성과 수집 기동 설정을 읽는 것은 인증·API·저장소 기동이 아니다."""
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import tempfile
import unittest
from common.operations.metrics_startup_config import MetricsCollectionSettings,load_metrics_collection_settings
from common.operations.models import ContractError

class MetricsStartupConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def file(self,**over):
        path=self.root/'metrics.json';path.write_text(json.dumps({**dict(schema_version=1,enabled=False,connection_ids=[]),**over}));return path
    def test_disabled_default_and_enabled_known_connections_are_frozen(self):
        settings=load_metrics_collection_settings(self.file());self.assertEqual(settings,MetricsCollectionSettings(False,()))
        settings=load_metrics_collection_settings(self.file(enabled=True,connection_ids=['personal.youtube','dept.youtube']))
        self.assertEqual(settings.connection_ids,('personal.youtube','dept.youtube'))
        with self.assertRaises(FrozenInstanceError):settings.enabled=False
    def test_exact_schema_and_enabled_registration_required(self):
        for over in (dict(schema_version=True),dict(schema_version=2),dict(enabled='true'),dict(command='native'),dict(enabled=True),dict(connection_ids='personal.youtube'),dict(connection_ids=['personal.youtube','personal.youtube']),dict(connection_ids=['other.youtube']),dict(connection_ids=[True]),dict(connection_ids=['personal.youtube','dept.youtube','personal.youtube'])):
            with self.assertRaises(ContractError):load_metrics_collection_settings(self.file(**over))
    def test_duplicate_keys_oversize_and_bad_paths_rejected(self):
        path=self.file();path.write_text(path.read_text()[:-1]+',"enabled":true}')
        with self.assertRaises(ContractError):load_metrics_collection_settings(path)
        path.write_bytes(b'x'*8193)
        with self.assertRaises(ContractError):load_metrics_collection_settings(path)
        path=self.file();alias=self.root/'alias';alias.symlink_to(path)
        for candidate in (alias,self.root/'missing',self.root,Path('relative.json')):
            with self.assertRaises(ContractError):load_metrics_collection_settings(candidate)
    def test_disabled_can_preserve_known_preferences_without_activation(self):
        settings=load_metrics_collection_settings(self.file(connection_ids=['dept.youtube']))
        self.assertFalse(settings.enabled);self.assertEqual(settings.connection_ids,('dept.youtube',))
    def test_actual_default_config_is_disabled(self):
        path=Path(__file__).resolve().parents[2]/'ax-console/config/metrics-collection.json'
        self.assertEqual(load_metrics_collection_settings(path),MetricsCollectionSettings(False,()))
