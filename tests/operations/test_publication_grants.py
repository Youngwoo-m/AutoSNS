"""임시 owner와 SQLite만으로 발행 승인 결속·CAS·기본 거부를 확인한다."""
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from common.operations.content_store import StoreError
from common.operations.oauth_catalog import provider_catalog
from common.operations.oauth_workspace import initialize_workspace_owner, oauth_write_guard, require_oauth_write_guard
from common.operations.publication_grants import (DB_NAME,PublicationGrantStore,PublicationGrantBinding,
    PublicationGrantPolicy,VerifiedPublicationEvidence)

NOW=datetime(2026,11,4,tzinfo=timezone.utc)
STATUS_KEYS={'connection_id','account_id','platform','provider_id','target_id','revision','status','approved_at','expires_at','policy_revision'}


class PublicationGrantTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'workspace';self.context=initialize_workspace_owner(self.root)
        self.policy=PublicationGrantPolicy('trusted-policy-v1',('youtube','threads','x'))
        self.binding=PublicationGrantBinding(owner=self.context.owner,registry_revision='registry-v1',
            connection_id='personal.youtube',account_id='personal',platform='youtube',provider_id='youtube',
            target_id='channel-id',provider_subject='provider-principal',connection_revision=1,credential_generation=1,
            credential_fingerprint='a'*64,client_revision=1,evidence_revision='provider-audit-v1')
        self.evidence=self.evidence_for(self.binding)
        self.store=PublicationGrantStore(self.context,policy=self.policy)

    def evidence_for(self,binding,**changes):
        provider=next(p for p in provider_catalog() if p.id==binding.provider_id)
        args=dict(binding=binding,observed_scopes=provider.read_scopes+provider.publication_scopes,
                  checked_at=NOW,credential_expires_at=NOW+timedelta(hours=2),can_publish=True,
                  verification_method='trusted_provider_probe_v1')
        return VerifiedPublicationEvidence(**{**args,**changes})

    def issue(self,**changes):
        args=dict(expected_revision=0,actor='trusted-server-user',expires_at=NOW+timedelta(hours=1),now=NOW)
        args.update(changes)
        return self.store.issue(self.evidence,**args)

    def assert_error(self,call,code=None):
        with self.assertRaises(StoreError) as caught:call()
        if code:self.assertEqual(caught.exception.code,code)

    def test_constructor_inert_no_database_and_default_policy_denies(self):
        before={p.name for p in self.root.iterdir()}
        denied=PublicationGrantStore(self.context)
        self.assertEqual({p.name for p in self.root.iterdir()},before)
        self.assertIsNone(denied.current(self.binding,now=NOW))
        self.assertEqual(denied.status(self.binding,now=NOW)['status'],'blocked')
        self.assertFalse((self.root/DB_NAME).exists())
        denied.initialize()
        self.assert_error(lambda:denied.issue(self.evidence,expected_revision=0,actor='user',expires_at=NOW+timedelta(minutes=1),now=NOW),
                          'publication_grant_unverified')

    def test_explicit_initialize_private_status_and_grant_serialization(self):
        self.assert_error(self.issue,'publication_grant_storage_error')
        self.store.initialize();saved=self.issue()
        self.assertEqual(set(saved),STATUS_KEYS);self.assertEqual(saved['status'],'granted');self.assertEqual(saved['revision'],1)
        self.assertEqual((self.root/DB_NAME).stat().st_mode&0o777,0o600)
        grant=self.store.current(self.binding,now=NOW)
        self.assertEqual(grant.binding,self.binding);self.assertEqual(set(grant.observed_scopes),set(self.evidence.observed_scopes))
        self.assertEqual(grant.expires_at,NOW+timedelta(hours=1))
        for private in (self.binding,self.evidence,self.policy,self.store,grant):
            self.assertEqual(private.to_dict(),{})
            self.assertNotIn(str(self.root),repr(private));self.assertNotIn(self.binding.credential_fingerprint,repr(private))
            self.assert_error(lambda:private.to_dict(public=False),'publication_grant_private_serialization_forbidden')
        with self.assertRaises(FrozenInstanceError):grant.revision=5
        public=json.dumps(saved)
        for secret in ('workspace_id','root_binding','fingerprint','observed_scopes','actor','verification_method',
                       'provider-principal','credential','https://',str(self.root)):
            self.assertNotIn(secret,public)

    def test_all_binding_dimensions_policy_and_expiry_fail_closed(self):
        self.store.initialize();self.issue()
        changes=[dict(registry_revision='next'),dict(connection_id='other.youtube'),dict(account_id='dept'),dict(target_id='other'),
                 dict(provider_subject='other'),dict(connection_revision=2),dict(credential_generation=2),
                 dict(credential_fingerprint='b'*64),dict(client_revision=2),dict(evidence_revision='other')]
        for change in changes:
            with self.subTest(change=change):
                self.assertIsNone(self.store.current(replace(self.binding,**change),now=NOW))
                self.assertEqual(self.store.status(replace(self.binding,**change),now=NOW)['status'],'blocked')
        changed=PublicationGrantStore(self.context,policy=replace(self.policy,revision='policy-v2'))
        self.assertIsNone(changed.current(self.binding,now=NOW))
        self.assertIsNone(self.store.current(self.binding,now=NOW+timedelta(hours=1)))
        self.assertEqual(self.store.status(self.binding,now=NOW+timedelta(hours=1))['status'],'expired')

    def test_cas_revoke_append_history_and_new_generation_approval(self):
        self.store.initialize();self.issue()
        self.assert_error(self.issue,'conflict')
        self.assert_error(lambda:self.store.revoke(self.binding.connection_id,expected_revision=2,actor='user',now=NOW),'conflict')
        status=self.store.revoke(self.binding.connection_id,expected_revision=1,actor='reviewer',now=NOW)
        self.assertEqual((status['revision'],status['status']),(2,'revoked'));self.assertIsNone(self.store.current(self.binding,now=NOW))
        binding=replace(self.binding,credential_generation=2,credential_fingerprint='b'*64)
        evidence=self.evidence_for(binding)
        saved=self.store.issue(evidence,expected_revision=2,actor='user',expires_at=NOW+timedelta(minutes=30),now=NOW)
        self.assertEqual(saved['revision'],3);self.assertIsNotNone(self.store.current(binding,now=NOW))
        self.assertIsNone(self.store.current(self.binding,now=NOW))
        with sqlite3.connect(self.root/DB_NAME) as db:
            self.assertEqual(db.execute('SELECT decision FROM publication_grants ORDER BY revision').fetchall(),[('granted',),('revoked',),('granted',)])
            for statement in ('UPDATE publication_grants SET revision=9','DELETE FROM publication_grants',
                              "UPDATE publication_grant_meta SET workspace_id='changed'"):
                with self.assertRaises(sqlite3.IntegrityError):db.execute(statement)

    def test_fresh_observation_ttl_token_expiry_can_publish_and_typed_only(self):
        self.store.initialize()
        for changes in (dict(checked_at=NOW-timedelta(seconds=61)),dict(checked_at=NOW+timedelta(microseconds=1)),dict(can_publish=False),
                        dict(credential_expires_at=NOW+timedelta(minutes=20))):
            with self.subTest(changes=changes):
                evidence=self.evidence_for(self.binding,**changes)
                self.assert_error(lambda:self.store.issue(evidence,expected_revision=0,actor='user',expires_at=NOW+timedelta(hours=1),now=NOW),
                                  'publication_grant_unverified')
        for changes in (dict(expires_at=NOW),dict(expires_at=NOW+timedelta(hours=1,seconds=1)),dict(actor=''),dict(expected_revision=True)):
            with self.subTest(changes=changes):self.assert_error(lambda:self.issue(**changes),'publication_grant_unverified')
        self.assert_error(lambda:self.store.issue({'can_publish':True},expected_revision=0,actor='user',expires_at=NOW+timedelta(minutes=5),now=NOW))
        self.assert_error(lambda:replace(self.evidence,checked_at=NOW.replace(tzinfo=None)))

    def test_required_read_and_publication_scopes_unknown_extra_and_hard_denied_providers(self):
        self.store.initialize()
        for scopes in ((self.evidence.observed_scopes[0],),()):
            with self.subTest(scopes=scopes):
                evidence=self.evidence_for(self.binding,observed_scopes=scopes)
                self.assert_error(lambda:self.store.issue(evidence,expected_revision=0,actor='user',expires_at=NOW+timedelta(minutes=5),now=NOW),
                                  'publication_grant_unverified')
        self.assert_error(lambda:self.evidence_for(self.binding,observed_scopes=(*self.evidence.observed_scopes,'unknown.scope')),
                          'publication_grant_scope_unverified')
        for provider_id in ('tiktok','naver','tistory'):
            provider=next(p for p in provider_catalog() if p.id==provider_id)
            binding=replace(self.binding,provider_id=provider.id,platform=provider.platform,connection_id='personal.'+provider.platform)
            store=PublicationGrantStore(self.context,policy=PublicationGrantPolicy('explicit', (provider_id,)));store.initialize()
            evidence=self.evidence_for(binding)
            self.assert_error(lambda:store.issue(evidence,expected_revision=0,actor='user',expires_at=NOW+timedelta(minutes=5),now=NOW),
                              'publication_grant_unverified')

    def test_foreign_owner_copied_database_symlinks_and_permissions(self):
        self.store.initialize();self.issue()
        other=initialize_workspace_owner(Path(self.temp.name)/'other')
        foreign=replace(self.binding,owner=other.owner)
        self.assert_error(lambda:self.store.current(foreign,now=NOW),'publication_grant_owner_mismatch')
        (other.root/DB_NAME).write_bytes((self.root/DB_NAME).read_bytes());(other.root/DB_NAME).chmod(0o600)
        copied=PublicationGrantStore(other,policy=self.policy)
        self.assert_error(copied.initialize,'publication_grant_owner_mismatch')
        (other.root/DB_NAME).unlink();(other.root/DB_NAME).symlink_to(self.root/DB_NAME)
        self.assert_error(copied.initialize,'publication_grant_storage_error')
        (self.root/DB_NAME).chmod(0o644)
        self.assert_error(lambda:self.store.current(self.binding,now=NOW),'publication_grant_storage_error')

    def test_foreign_schema_rejected_unchanged_and_internal_lock_order_reentrant(self):
        with sqlite3.connect(self.root/DB_NAME) as db:db.execute('CREATE TABLE unrelated(secret TEXT)')
        (self.root/DB_NAME).chmod(0o600)
        self.assert_error(self.store.initialize,'publication_grant_storage_error')
        with sqlite3.connect(self.root/DB_NAME) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name='unrelated'").fetchone(),('unrelated',))
        (self.root/DB_NAME).unlink();self.store.initialize()
        original=self.store._verify;calls=[]
        def verify(db):
            require_oauth_write_guard(self.root,self.context.owner);calls.append('guard-before-db');return original(db)
        with patch.object(self.store,'_verify',side_effect=verify),oauth_write_guard(self.context):
            self.issue();self.assertIsNotNone(self.store.current(self.binding,now=NOW))
            self.store.revoke(self.binding.connection_id,expected_revision=1,actor='user',now=NOW)
        self.assertEqual(len(calls),3)

    def test_concurrent_same_revision_approval_has_one_winner(self):
        self.store.initialize()
        other=PublicationGrantStore(self.context,policy=self.policy);other.initialize()
        barrier=threading.Barrier(2);results=[]
        def approve(store):
            barrier.wait(timeout=3)
            try:
                value=store.issue(self.evidence,expected_revision=0,actor='server-user',
                                  expires_at=NOW+timedelta(minutes=10),now=NOW)
                results.append(value['status'])
            except StoreError as error:
                results.append(error.code)
        threads=[threading.Thread(target=approve,args=(store,)) for store in (self.store,other)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=5)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sorted(results),['conflict','granted'])
        self.assertEqual(self.store.status(self.binding,now=NOW)['revision'],1)
