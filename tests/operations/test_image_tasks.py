import hashlib
from pathlib import Path
import struct
import sqlite3
import threading
import tempfile
import unittest
from common.operations.content_store import ContentStore
from common.operations.models import ContractError
from common.operations.image_tasks import ImageTaskStore, ImageTaskService

PNG=b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',1080,1350)+b'\x08\x06\x00\x00\x00'+b'fake-crc'
SPEC=dict(template='card',title='제목',body=['본문'],footer='출처')

class ImageTaskTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)/'store'
        self.contents=ContentStore(self.root);self.contents.initialize()
        self.content=self.contents.create('personal',dict(title='제목',kind='card'))
        self.store=ImageTaskStore(self.root);self.calls=[]
        self.service=ImageTaskService(self.store,self.contents,runner=self.runner,enabled=True)
        self.store.initialize()
    def runner(self,spec,*,owner_account_id,artifact_root):
        self.calls.append((spec,owner_account_id));p=artifact_root/'card.png';p.write_bytes(PNG)
        return dict(path=str(p),sha256=hashlib.sha256(PNG).hexdigest(),size=len(PNG),width=1080,height=1350)
    def create(self,spec=None):return self.service.create(self.content['id'],self.content['revision'],SPEC if spec is None else spec)
    def test_completed_idempotent_and_generated_provenance(self):
        result=self.create();self.assertEqual(result['state'],'completed');self.assertEqual(result['review_status'],'not_checked')
        self.assertEqual(result['output_revision'],2)
        self.assertEqual(self.create(),result);self.assertEqual(len(self.calls),1)
        self.assertEqual(self.service.list_for_content(self.content['id']),[result])
        self.assertEqual(self.contents.get(self.content['id'])['assets'][0]['media_type'],'image/png')
    def test_disabled_inert_and_invalid_spec(self):
        root=self.root/'inert';store=ImageTaskStore(root);service=ImageTaskService(store,ContentStore(root))
        self.assertFalse(root.exists());self.assertFalse(service.capabilities()['execution_enabled']);self.assertEqual(service.list_for_content('missing'),[])
        with self.assertRaises(ContractError):service.create('missing',1,SPEC)
        self.assertFalse(root.exists())
        for spec in ({**SPEC,'title':''},{**SPEC,'body':[]},{**SPEC,'path':'/tmp/x'},{**SPEC,'template':'html'},{**SPEC,'body':['x'*121]},{**SPEC,'footer':'\ud800'}):
            with self.assertRaises(ContractError):self.create(spec)
        self.assertEqual(self.calls,[])
    def test_unknown_exception_never_rerenders(self):
        def runner(*a,**k):self.calls.append('unknown');raise RuntimeError('native stopped')
        self.service.runner=runner
        result=self.create();self.assertEqual(result['state'],'unknown')
        self.assertEqual(self.create(),result);self.assertEqual(self.service.resume(result['task_id']),result)
        self.assertEqual(len(self.calls),1);self.assertEqual(self.contents.get(self.content['id'])['revision'],1)
    def test_invalid_hash_dimensions_and_external_or_symlink_path_fail(self):
        for mode in ('hash','dimensions','outside','symlink'):
            with self.subTest(mode=mode):
                spec={**SPEC,'title':mode}
                def runner(*a,**kw):
                    result=self.runner(*a,**kw)
                    if mode=='hash':result['sha256']='0'*64
                    if mode=='dimensions':result['width']=500
                    if mode=='outside':result['path']=str(self.root/'outside.png');(self.root/'outside.png').write_bytes(PNG)
                    if mode=='symlink':
                        p=Path(result['path']);p.rename(p.with_suffix('.real'));p.symlink_to(p.with_suffix('.real'))
                    return result
                self.service.runner=runner
                self.assertEqual(self.create(spec)['state'],'failed')
        self.assertEqual(self.contents.get(self.content['id'])['revision'],1)
    def test_content_changes_during_native_are_not_overwritten(self):
        def runner(*a,**kw):
            result=self.runner(*a,**kw);self.contents.update(self.content['id'],1,dict(title='new',kind='card'));return result
        self.service.runner=runner
        result=self.create();self.assertEqual(result['state'],'content_changed');self.assertEqual(self.contents.get(self.content['id'])['assets'],[])
    def test_add_asset_crash_can_resume_without_rerender_or_duplicate(self):
        original=self.contents.add_asset
        def crash(*a,**kw):original(*a,**kw);raise OSError('crash after commit')
        self.contents.add_asset=crash
        result=self.create();self.assertEqual(result['state'],'rendered')
        self.contents.add_asset=original
        completed=self.service.resume(result['task_id']);self.assertEqual(completed['state'],'completed')
        self.assertEqual(len(self.calls),1);self.assertEqual(len(self.contents.get(self.content['id'])['assets']),1)

    def test_owner_is_server_bound_and_provenance_is_internal(self):
        dept=self.contents.create('dept',dict(title='학과',kind='card'))
        result=self.service.create(dept['id'],dept['revision'],SPEC)
        self.assertEqual(self.calls[-1][1],'dept')
        self.assertEqual(set(result),{'task_id','state','reason_code','content_id','input_revision','output_revision','asset_id','review_status'})
        row=self.store.get(result['task_id'])
        self.assertEqual(row['origin'],'generated');self.assertEqual(row['provider_id'],'local-card')
        self.assertEqual(row['spec_hash'],hashlib.sha256(row['spec'].encode()).hexdigest())
        self.assertEqual(self.service.list_for_content(self.content['id']),[])

    def test_concurrent_same_intent_returns_started_without_second_native(self):
        entered=threading.Event();release=threading.Event();results=[]
        def runner(*a,**kw):
            entered.set();release.wait(5);return self.runner(*a,**kw)
        self.service.runner=runner
        thread=threading.Thread(target=lambda:results.append(self.create()));thread.start()
        self.assertTrue(entered.wait(5))
        try:
            result=self.create();self.assertEqual(result['state'],'started')
        finally:release.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(len(self.calls),1);self.assertEqual(results[0]['state'],'completed')

    def test_rendered_artifact_tamper_prevents_resume_ingest(self):
        original=self.contents.add_asset
        def unavailable(*a,**kw):raise OSError('temporary storage failure')
        self.contents.add_asset=unavailable
        result=self.create();self.assertEqual(result['state'],'rendered')
        row=self.store.get(result['task_id']);(self.store.artifact_root(result['task_id'])/row['path']).write_bytes(PNG+b'tamper')
        self.contents.add_asset=original
        self.assertEqual(self.service.resume(result['task_id'])['state'],'failed')
        self.assertEqual(self.contents.get(self.content['id'])['assets'],[]);self.assertEqual(len(self.calls),1)

    def test_foreign_and_symlink_stores_fail_closed(self):
        other=self.root/'foreign';other.mkdir()
        db=sqlite3.connect(other/'image-tasks.sqlite3');db.execute('CREATE TABLE keep(value)');db.commit();db.close()
        with self.assertRaises(ContractError):ImageTaskStore(other).initialize()
        target=self.root/'target';target.mkdir();link=self.root/'linked';link.symlink_to(target)
        with self.assertRaises(ContractError):ImageTaskStore(link).initialize()
