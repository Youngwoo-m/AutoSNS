"""운영 자료·소켓 없이 임시 원장만 검증한다."""
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch
from common.operations.content_store import ContentStore, StoreError
from common.operations.database import DDL, initialize_database, connect_database
from common.operations.ledger import Ledger
from common.operations.registry import load_registry
from common.operations.models import ContractError

REGISTRY=Path(__file__).resolve().parents[1]/'ax-console/config/operations.json'

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'workspace'; self.store=ContentStore(self.root)
        self.ledger=Ledger(self.root,REGISTRY,self.store)

    def setup_content(self,asset=False):
        self.store.initialize(); self.ledger.initialize()
        self.content=self.store.create('personal',{'title':'계획','kind':'article','original':'원문'})
        if asset: self.content=self.store.add_asset(self.content['id'],1,'a.png','image/png',b'\x89PNG\r\n\x1a\nfixture')
        c=self.content
        return dict(content_id=c['id'],revision=c['revision'],manifest_hash=c['manifest_hash'],connection_id='personal.youtube',publication_purpose='initial',schedule_slot='test-slot',scheduled_at='2026-11-01T10:00:00+09:00',timezone='Asia/Seoul',schedule_condition={'kind':'window','from':'2026-11-01T09:00:00+09:00','to':'2026-11-01T12:00:00+09:00'})

    def error(self,code,fn,*args):
        with self.assertRaises(StoreError) as caught: fn(*args)
        self.assertEqual(caught.exception.code,code)

    def test_reads_and_construction_do_not_initialize(self):
        self.error('storage_error',self.ledger.list_deliveries)
        self.assertFalse(self.root.exists())

    def test_v1_read_compatible_migration_preserves_rows_and_assets(self):
        body=self.setup_content(True)
        conn=sqlite3.connect(self.root/'operations.sqlite3')
        for table in ('delivery_events','approvals','deliveries','runs','triggers','jobs'): conn.execute('DROP TABLE '+table)
        conn.execute('PRAGMA user_version=1');conn.commit();conn.close()
        before={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file() and p.name!='operations.sqlite3'}
        self.assertEqual(self.store.get(body['content_id']),self.content)
        self.error('storage_error',self.ledger.list_deliveries)
        conn=connect_database(self.root)
        try: self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],1)
        finally: conn.close()
        self.ledger.initialize()
        self.assertEqual(self.store.get(body['content_id']),self.content)
        self.assertEqual(before,{p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file() and p.name!='operations.sqlite3'})

    def test_migration_rollback_and_future_version(self):
        self.root.mkdir(); conn=sqlite3.connect(self.root/'operations.sqlite3')
        for ddl in DDL: conn.execute(ddl)
        conn.execute('PRAGMA user_version=1');conn.commit();conn.close()
        with patch('common.operations.database.OPERATIONS_DDL',('CREATE TABLE added(id INTEGER)','BROKEN SQL')):
            with self.assertRaises(sqlite3.Error): initialize_database(self.root)
        conn=sqlite3.connect(self.root/'operations.sqlite3')
        self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],1)
        self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name='added'").fetchone())
        conn.execute('PRAGMA user_version=99'); conn.commit();conn.close()
        with self.assertRaises(sqlite3.Error): initialize_database(self.root)
        with self.assertRaises(sqlite3.Error): connect_database(self.root)

    def test_create_idempotency_conflict_and_scope(self):
        body=self.setup_content(); r=self.ledger.create_or_get_delivery(body)
        self.assertEqual(r,self.ledger.create_or_get_delivery(body))
        self.error('conflict',self.ledger.create_or_get_delivery,dict(body,scheduled_at='2026-11-01T11:00:00+09:00'))
        self.assertFalse(r['execution_enabled']); self.assertEqual(r['remote_state'],'unavailable')
        self.assertNotIn('context',r);self.assertNotIn('credential_ref',json.dumps(r))
        with self.ledger._db() as conn:
            context=json.loads(conn.execute('SELECT payload FROM deliveries').fetchone()[0])['context']
            self.assertEqual(context['scope'],'plan');self.assertIs(context['dry_run'],True)
        self.assertEqual(len(self.ledger.events(r['id'])),1)
        self.assertEqual(self.ledger.preview_delivery(body)['id'],None)
        self.assertEqual(len(self.ledger.list_deliveries()),1)

    def test_approval_and_schedule_window_outside_preserve_history(self):
        r=self.ledger.create_or_get_delivery(self.setup_content())
        r=self.ledger.record_approval(r['id'],1,r['subject_hash'],'approved','확인')
        self.assertEqual(r['status'],'ready'); self.assertEqual(r['approval']['scope'],'plan')
        p=self.ledger.preview_schedule(r['id'],2,'2026-11-01T11:00:00+09:00','Asia/Seoul')
        self.assertTrue(p['approval_retained'])
        moved=self.ledger.reschedule(r['id'],2,'2026-11-01T11:00:00+09:00','Asia/Seoul',p['preview_hash'])
        self.assertEqual(moved['subject_hash'],r['subject_hash']);self.assertEqual(moved['id'],r['id'])
        self.error('conflict',self.ledger.reschedule,r['id'],2,'2026-11-01T11:00:00+09:00','Asia/Seoul',p['preview_hash'])
        p=self.ledger.preview_schedule(r['id'],3,'2026-11-01T13:00:00+09:00','Asia/Seoul')
        self.assertFalse(p['approval_retained']);self.assertEqual(p['schedule_condition']['kind'],'fixed')
        moved=self.ledger.reschedule(r['id'],3,'2026-11-01T13:00:00+09:00','Asia/Seoul',p['preview_hash'])
        self.assertEqual(moved['status'],'pending');self.assertEqual(moved['approval'],r['approval'])
        cancelled=self.ledger.cancel(r['id'],4);self.assertEqual(cancelled['status'],'cancelled')

    def test_asset_actual_bytes_and_approval_atomic_rollback(self):
        body=self.setup_content(True); r=self.ledger.create_or_get_delivery(body)
        with patch.object(self.ledger,'_event',side_effect=RuntimeError('fixture')):
            with self.assertRaises(RuntimeError): self.ledger.record_approval(r['id'],1,r['subject_hash'],'approved','')
        self.assertEqual(self.ledger.get_delivery(r['id'])['version'],1)
        with self.ledger._db() as conn: self.assertEqual(conn.execute('SELECT count(*) FROM approvals').fetchone()[0],0)
        asset=self.content['assets'][0]; path=next(self.root.rglob(asset['id']));path.write_bytes(b'tampered')
        self.error('storage_error',self.ledger.record_approval,r['id'],1,r['subject_hash'],'approved','')

    def test_two_writers_and_cas(self):
        body=self.setup_content(); result=[]
        def create(): result.append(self.ledger.create_or_get_delivery(body))
        threads=[threading.Thread(target=create) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(len(result),2);self.assertEqual(result[0]['id'],result[1]['id'])
        r=result[0];self.ledger.cancel(r['id'],1)
        self.error('conflict',self.ledger.cancel,r['id'],1)

    def test_unverified_target_draft_and_no_approval(self):
        body=self.setup_content();body['connection_id']='personal.tistory'
        r=self.ledger.create_or_get_delivery(body)
        self.assertIsNone(r['subject_hash']);self.assertEqual(r['target_status'],'unverified');self.assertTrue(r['blockers'])
        self.error('conflict',self.ledger.record_approval,r['id'],1,None,'approved','')

    def test_registry_update_read_view_invalidates_ready_without_writing(self):
        body=self.setup_content(); source=Path(self.tmp.name)/'registry.json';source.write_bytes(REGISTRY.read_bytes())
        ledger=Ledger(self.root,source,self.store);ledger.initialize()
        r=ledger.create_or_get_delivery(body)
        r=ledger.record_approval(r['id'],1,r['subject_hash'],'approved','')
        before=(self.root/'operations.sqlite3').read_bytes()
        data=json.loads(source.read_text());data['revision']='new-policy';source.write_text(json.dumps(data))
        current=ledger.get_delivery(r['id'])
        self.assertEqual(current['status'],'pending')
        self.assertNotEqual(current['subject_hash'],r['subject_hash'])
        self.assertEqual(before,(self.root/'operations.sqlite3').read_bytes())
        r=ledger.record_approval(r['id'],2,current['subject_hash'],'approved','새 정책 확인')
        self.assertEqual(r['status'],'ready')

    def test_registry_reload_invalidates_approval_and_preview(self):
        body=self.setup_content(); source=Path(self.tmp.name)/'registry.json';source.write_bytes(REGISTRY.read_bytes())
        ledger=Ledger(self.root,source,self.store);ledger.initialize()
        r=ledger.create_or_get_delivery(body)
        p=ledger.preview_schedule(r['id'],1,'2026-11-01T11:00:00+09:00','Asia/Seoul')
        data=json.loads(source.read_text());data['revision']='changed';source.write_text(json.dumps(data))
        self.error('conflict',ledger.record_approval,r['id'],1,r['subject_hash'],'approved','')
        self.error('conflict',ledger.reschedule,r['id'],1,'2026-11-01T11:00:00+09:00','Asia/Seoul',p['preview_hash'])

if __name__=='__main__':unittest.main()
