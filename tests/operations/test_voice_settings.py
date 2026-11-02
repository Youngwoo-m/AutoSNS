"""계정별 음성 설정은 다음 명시 기동용이며 저장 자체가 실행은 아니다."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from common.operations.content_store import ConflictError, StoreError
from common.operations.models import ContractError
from common.operations.voice_settings import VoiceSettingsStore,compile_voice_settings,DB_NAME,APPLICATION_ID

class VoiceSettingsTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)/'managed';self.store=VoiceSettingsStore(self.root)
    def test_inert_defaults_and_explicit_initialize(self):
        expected=dict(account_id='personal',revision=0,enabled_preference=False,profile_id=None,applies_to='next_startup',execution_enabled=False)
        self.assertEqual(self.store.get('personal'),expected);self.assertFalse(self.root.exists())
        with self.assertRaises(StoreError):self.store.save('personal',0,dict(enabled_preference=True,profile_id='voice1'))
        self.assertFalse(self.root.exists());self.store.initialize();self.store.initialize()
        self.assertEqual(self.store.get('personal'),expected)
        db=sqlite3.connect(self.root/DB_NAME)
        try:self.assertEqual(db.execute('pragma application_id').fetchone()[0],APPLICATION_ID);self.assertEqual(db.execute('pragma user_version').fetchone()[0],1)
        finally:db.close()
    def test_cas_account_isolation_and_shared_profile_are_allowed(self):
        self.store.initialize();payload=dict(enabled_preference=True,profile_id='same-local-profile')
        personal=self.store.save('personal',0,payload);dept=self.store.save('dept',0,payload)
        self.assertEqual(personal['revision'],1);self.assertEqual(dept['revision'],1)
        self.assertEqual(compile_voice_settings([personal,dept]),{'personal':'same-local-profile','dept':'same-local-profile'})
        with self.assertRaises(ConflictError):self.store.save('personal',0,payload)
        disabled=self.store.save('personal',1,dict(enabled_preference=False,profile_id='same-local-profile'))
        self.assertEqual(compile_voice_settings([disabled,dept]),{'dept':'same-local-profile'})
        self.assertEqual(self.store.get('dept'),dept);self.assertEqual(self.store.get('personal'),disabled)
    def test_invalid_payload_account_and_revision_do_not_write(self):
        self.store.initialize()
        for account in ('all','',None,True):
            with self.assertRaises(StoreError):self.store.get(account)
        for payload in ({'enabled_preference':True,'profile_id':None},{'enabled_preference':1,'profile_id':'x'}, {'enabled_preference':False,'profile_id':'a/b'}, {'enabled_preference':False,'profile_id':'x'*129},{'enabled_preference':False,'profile_id':'é'}, {'enabled_preference':False,'profile_id':True},{'enabled_preference':False,'profile_id':''},{'enabled_preference':False,'profile_id':None,'token':'never'}):
            with self.assertRaises(StoreError):self.store.save('personal',0,payload)
        for revision in (-1,True,0.0,'0',None):
            with self.assertRaises(StoreError):self.store.save('personal',revision,dict(enabled_preference=False,profile_id=None))
        self.assertEqual(self.store.get('personal')['revision'],0)
    def test_foreign_schema_and_symlinks_are_rejected_without_repair(self):
        self.root.mkdir();db=sqlite3.connect(self.root/DB_NAME);db.execute('CREATE TABLE keep(value)');db.execute("INSERT INTO keep VALUES('preserve')");db.commit();db.close()
        with self.assertRaises(StoreError):self.store.initialize()
        with self.assertRaises(StoreError):self.store.get('personal')
        db=sqlite3.connect(self.root/DB_NAME)
        try:self.assertEqual(db.execute('SELECT value FROM keep').fetchone()[0],'preserve')
        finally:db.close()
        (self.root/DB_NAME).unlink();target=self.root.parent/'elsewhere';(self.root/DB_NAME).symlink_to(target)
        with self.assertRaises(StoreError):self.store.initialize()
        self.assertFalse(target.exists())
        actual=self.root.parent/'actual';actual.mkdir();link=self.root.parent/'linked';link.symlink_to(actual)
        with self.assertRaises(StoreError):VoiceSettingsStore(link).initialize()
    def test_compile_rejects_unknown_duplicate_and_forged_runtime_flags(self):
        personal=self.store.get('personal');dept=self.store.get('dept');self.assertEqual(compile_voice_settings([personal,dept]),{})
        invalid=[[],[personal],[personal,personal],[personal,{**dept,'account_id':'other'}],[personal,{**dept,'execution_enabled':True}],[personal,{**dept,'applies_to':'immediate'}],[personal,{**dept,'revision':True}],[personal,{**dept,'enabled_preference':True}],[personal,{**dept,'extra':'x'}]]
        for rows in invalid:
            with self.assertRaises(ContractError):compile_voice_settings(rows)
        self.assertFalse(self.root.exists())
    def test_corrupt_persisted_row_and_extra_table_fail_closed(self):
        self.store.initialize();db=sqlite3.connect(self.root/DB_NAME)
        try:
            db.execute("INSERT INTO voice_settings VALUES('personal',1,1,NULL,'now')");db.commit()
        finally:db.close()
        with self.assertRaises(StoreError):self.store.get('personal')
        db=sqlite3.connect(self.root/DB_NAME)
        try:db.execute('CREATE TABLE extra(value)');db.commit()
        finally:db.close()
        with self.assertRaises(StoreError):self.store.get('dept')

    def test_compiler_is_pure_and_profile_boundaries_are_validated(self):
        self.store.initialize()
        personal=self.store.save('personal',0,dict(enabled_preference=True,profile_id='A_'+'-'*126))
        dept=self.store.get('dept')
        with patch('sqlite3.connect',side_effect=AssertionError('compiler database access')),patch('socket.socket',side_effect=AssertionError('compiler network access')):
            self.assertEqual(compile_voice_settings([personal,dept]),{'personal':personal['profile_id']})
        reader=VoiceSettingsStore(self.root)
        self.assertEqual(reader.get('personal'),personal)
        with self.assertRaises(StoreError):reader.save('personal',1,dict(enabled_preference=False,profile_id=None))
        self.assertEqual(reader.root,self.root.absolute())

    def test_changed_schema_or_application_id_is_not_migrated_on_read(self):
        self.store.initialize()
        for pragma in ('user_version','application_id'):
            db=sqlite3.connect(self.root/DB_NAME)
            try:db.execute('PRAGMA '+pragma+'=42');db.commit()
            finally:db.close()
            with self.assertRaises(StoreError):self.store.get('personal')
            with self.assertRaises(StoreError):self.store.initialize()
            db=sqlite3.connect(self.root/DB_NAME)
            try:
                self.assertEqual(db.execute('PRAGMA '+pragma).fetchone()[0],42)
                db.execute('PRAGMA '+pragma+'='+str(1 if pragma=='user_version' else APPLICATION_ID));db.commit()
            finally:db.close()
