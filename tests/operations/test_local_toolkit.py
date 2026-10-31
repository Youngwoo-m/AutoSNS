import base64
import hashlib
import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from common.operations.local_toolkit import LocalToolkitService
from common.operations.tool_cost_policy import ToolkitPolicy
from common.operations.content_store import StoreError, ConflictError
from common.operations.models import Registry, Connection
from common.operations.metrics_store import MetricsStore

NOW = datetime(2026, 10, 31, tzinfo=timezone.utc)
CSV = 'platform,target_id,remote_id,metric_name,value,observed_at,basis\nyoutube,target,remote,views,0,2026-01-01T00:00:00Z,lifetime\n'
class ToolkitTests(unittest.TestCase):
    def setUp(self):
        self.registry = Registry('r1', {'personal': {}, 'dept': {}}, {}, {}, {'c': Connection('c','personal','youtube',target_id='target'), 'd': Connection('d','dept','youtube',target_id='dept-target'), 'n': Connection('n','personal','youtube',target_id=None)}, {}, {}, {})
        self.snapshot = dict(id='content', revision=2, owner_account_id='personal', title='제목', variants=[dict(destination_account_id='personal', platform='youtube', text='본문')], sources=[], assets=[])
        self.content = Mock(); self.content.get.return_value = self.snapshot
        self.service = LocalToolkitService(registry=self.registry, content_store=self.content, policy=ToolkitPolicy(True), clock=lambda: NOW)
    def packaging(self, **changes):
        return dict(content_id='content', revision=2, connection_id='c', keywords=['키워드'], **changes)
    def test_exact_fields_and_disabled_before_asset_read(self):
        self.service.policy=ToolkitPolicy()
        result=self.service.thumbnail_inspect(dict(content_id='content',revision=2,asset_id='asset'))
        self.assertEqual(result['status'],'blocked'); self.content.read_asset.assert_not_called()
        for body in (dict(self.packaging(), path='/private/secret'),dict(self.packaging(),revision=True),dict(self.packaging(),keywords=['a','a'])):
            with self.assertRaises(StoreError): self.service.packaging_preview(body)
        self.content.ingest.assert_not_called()
    def test_wrong_account_connection_revision_and_target(self):
        with self.assertRaises(ConflictError): self.service.packaging_preview(dict(self.packaging(),revision=1))
        with self.assertRaises(StoreError): self.service.packaging_preview(dict(self.packaging(),connection_id='unknown'))
        result=self.service.packaging_preview(dict(self.packaging(),connection_id='d'))
        self.assertEqual(result['status'],'blocked')
        result=self.service.packaging_preview(dict(self.packaging(),connection_id='n'))
        self.assertIsNone(result['target_id']); self.assertFalse(result['connection_confirmed'])
    def test_registered_cross_account_local_analysis_and_forgery_fences(self):
        self.snapshot['variants'].append(dict(destination_account_id='dept',platform='youtube',text='학과 변환문'))
        rules={'route':dict(owner_account_id='personal',source_connection_id='c',destination_connection_id='d',enabled=False)}
        self.service.registry=Registry('cross',self.registry.accounts,{},{},self.registry.connections,{},{},rules)
        body=dict(self.packaging(),connection_id='d')
        result=self.service.packaging_preview(body)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['destination_account_id'],'dept')
        self.assertFalse(self.service.registry.crossposts['route']['enabled'])
        self.snapshot['variants']=[]
        self.assertEqual(self.service.packaging_preview(body)['reason_codes'],['destination_variant_missing'])
        self.snapshot['variants']=[dict(destination_account_id='dept',platform='youtube',text='변환문')]
        self.service.registry=Registry('bad',self.registry.accounts,{},{},self.registry.connections,{},{},{'route':dict(rules['route'],source_connection_id='d')})
        self.assertIn('account_mismatch',self.service.packaging_preview(body)['reason_codes'])
        for field in ('owner_account_id','target_id','cross_account_local_authorized','rule_id'):
            with self.assertRaises(StoreError):self.service.packaging_preview(dict(body,**{field:'forged'}))
        runtime=Mock();runtime.get_delivery.return_value=dict(state='unknown',context=dict(owner_account_id='personal',destination_account_id='dept',connection_id='d',target_id='dept-target',platform='youtube'))
        self.service.registry=Registry('cross',self.registry.accounts,{},{},self.registry.connections,{},{},rules)
        self.service.runtime_store=runtime
        observed=self.service.schedule_inspect(dict(delivery_id='delivery'))
        self.assertNotIn('account_mismatch',observed['reason_codes'])
        self.assertFalse(observed['execution_enabled'])

    def test_credit_and_unknown_cost_never_call_leaf(self):
        with patch('common.operations.local_toolkit.evaluate_tool_action',return_value=dict(allowed=False,reason_codes=['cost_not_zero'],evidence_refs=[])):
            with patch('common.operations.local_toolkit.build_packaging_preview') as leaf:
                self.assertEqual(self.service.packaging_preview(self.packaging())['status'],'blocked'); leaf.assert_not_called()
        for field in ('provider','cost','actor','credential','command','path'):
            with self.assertRaises(StoreError): self.service.packaging_preview(dict(self.packaging(),**{field:'untrusted'}))
    def test_thumbnail_returns_bytes_without_ingest_or_review(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow 미설치: 기존 Pillow 환경에서 별도 실행')
        stream=io.BytesIO(); Image.new('RGB',(1280,720)).save(stream,format='PNG'); data=stream.getvalue()
        renderer=Mock(return_value=dict(status='completed',reason_code='rendered',asset=dict(data=data,sha256=hashlib.sha256(data).hexdigest(),path='/secret',credential_ref='secret',width=1280,height=720)))
        self.service.thumbnail_renderer=renderer
        body=dict(content_id='content',revision=2,asset_id=None,preset_id='landscape.v1',title='제목')
        with patch('common.operations.local_toolkit.validate_registered_font',return_value=True): result=self.service.thumbnail_render(body)
        self.assertEqual(base64.b64decode(result['png_base64']),data)
        self.assertNotIn('secret',str(result)); self.content.ingest.assert_not_called(); self.content.add_review.assert_not_called()
        self.snapshot['assets']=[dict(id='asset',sha256='a'*64)]
        self.assertEqual(self.service.thumbnail_render(dict(body,asset_id='asset'))['status'],'blocked')
        self.content.read_asset.assert_not_called()
    def test_csv_changes_only_metrics_store(self):
        with tempfile.TemporaryDirectory() as root:
            from common.operations.content_store import ContentStore
            content=ContentStore(Path(root)); content.initialize()
            original=content.create('personal',{'title':'보존 원고','kind':'article'})
            approval_hash_before=original['manifest_hash']
            before={str(p):p.read_bytes() for p in Path(root).rglob('*') if p.is_file()}
            metrics=MetricsStore(root); metrics.initialize(); self.service.metrics_store=metrics
            preview=self.service.csv_preview(dict(account_id='personal',csv_text=CSV))
            self.assertNotIn('plan',preview); self.assertNotIn('source',preview['rows'][0])
            result=self.service.csv_import(dict(account_id='personal',csv_text=CSV,preview_digest=preview['preview_digest'],request_key='request'))
            self.assertEqual(result['imported'],1); self.assertEqual(metrics.list_observations()[0]['status'],'legacy_reported')
            self.assertEqual(self.content.mock_calls,[])
            for path,data in before.items(): self.assertEqual(Path(path).read_bytes(),data)
            self.assertTrue(any('sqlite' in path for path in before))
            self.assertEqual(content.get(original['id'])['manifest_hash'],approval_hash_before)
            again=self.service.csv_import(dict(account_id='personal',csv_text=CSV,preview_digest=preview['preview_digest'],request_key='other'))
            self.assertEqual(again['unchanged'],1)
    def test_schedule_read_only_and_public(self):
        runtime=Mock(); runtime.get_delivery.return_value=dict(id='delivery',state='unknown',context=dict(owner_account_id='personal',destination_account_id='personal',connection_id='c',target_id='target',credential_ref='secret'),remote_id='remote',scheduled_at=None)
        self.service.runtime_store=runtime
        result=self.service.schedule_inspect(dict(delivery_id='delivery'))
        self.assertEqual(set(result),{'delivery_id','state','target_id','remote_id','scheduled_at','execution_enabled','reason_codes'})
        self.assertFalse(result['execution_enabled']); self.assertEqual([c[0] for c in runtime.mock_calls],['get_delivery'])

    def test_no_external_calls_and_public_provenance(self):
        self.snapshot['sources']=[{'url':'file:///private/secret'},{'url':'https://user:secret@example.com/a'}, {'url':'https://example.com/a?credential_ref=secret#private'}]
        with patch('socket.socket',side_effect=AssertionError('외부 호출 금지')), patch('subprocess.Popen',side_effect=AssertionError('프로세스 금지')):
            result=self.service.packaging_preview(self.packaging())
            capabilities=self.service.capabilities('all')
        self.assertEqual(result['evidence_refs'],[{'url':'https://example.com/a'}])
        self.assertNotIn('secret',str(result)+str(capabilities))
        self.assertNotIn('credential_ref',str(capabilities))
        self.content.read_asset.assert_not_called()

    def test_each_operation_rechecks_disabled_and_font_validation(self):
        self.service.policy=ToolkitPolicy()
        for method,body in ((self.service.packaging_preview,self.packaging()),(self.service.research_preview,{'account_id':'all'}),(self.service.csv_preview,{'account_id':'personal','csv_text':CSV}),(self.service.csv_import,{'account_id':'personal','csv_text':CSV,'preview_digest':'a'*64,'request_key':'r'}),(self.service.thumbnail_render,{'content_id':'content','revision':2,'asset_id':None,'preset_id':'portrait.v1','title':'제목'})):
            self.assertEqual(method(body)['status'],'blocked')
        self.service.policy=ToolkitPolicy(True)
        renderer=Mock(font_sha256='0'*64)
        self.service.thumbnail_renderer=renderer
        result=self.service.thumbnail_render({'content_id':'content','revision':2,'asset_id':None,'preset_id':'portrait.v1','title':'제목'})
        self.assertEqual(result['status'],'unavailable'); renderer.assert_not_called()
        self.content.read_asset.assert_not_called()

    def test_csv_invalid_size_and_conflict(self):
        with self.assertRaises(StoreError) as caught: self.service.csv_preview({'account_id':'personal','csv_text':'x'*(256*1024+1)})
        self.assertEqual(caught.exception.code,'too_large')
        with self.assertRaises(StoreError): self.service.csv_preview({'account_id':'personal','csv_text':'bad'})
        with tempfile.TemporaryDirectory() as root:
            self.service.metrics_store=MetricsStore(root); self.service.metrics_store.initialize()
            with self.assertRaises(ConflictError): self.service.csv_import({'account_id':'personal','csv_text':CSV,'preview_digest':'0'*64,'request_key':'r'})

    def test_real_registered_font_render_and_asset_reuse(self):
        from common.operations.thumbnail_layout import REGISTERED_FONT, PillowThumbnailRenderer
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow 미설치: 기존 Pillow 환경에서 별도 실행')
        if not REGISTERED_FONT.is_file(): self.skipTest('등록 폰트 미가용')
        self.service.thumbnail_renderer=PillowThumbnailRenderer(REGISTERED_FONT,font_sha256=hashlib.sha256(REGISTERED_FONT.read_bytes()).hexdigest())
        body=dict(content_id='content',revision=2,asset_id=None,preset_id='landscape.v1',title='안전한 작업')
        rendered=self.service.thumbnail_render(body)
        self.assertEqual(rendered['status'],'completed',rendered)
        data=base64.b64decode(rendered['png_base64'])
        self.snapshot['assets']=[dict(id='asset',sha256=hashlib.sha256(data).hexdigest(),media_type='image/png')]
        self.content.read_asset.return_value=(self.snapshot['assets'][0],data)
        self.service.thumbnail_authorizer=lambda snapshot,asset: True
        reused=self.service.thumbnail_render(dict(body,asset_id='asset'))
        self.assertEqual(reused['status'],'completed',reused)
        self.content.read_asset.assert_called_once_with('content',2,'asset')
        self.content.ingest.assert_not_called()
