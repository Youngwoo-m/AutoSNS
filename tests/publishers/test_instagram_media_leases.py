"""실제 전송 없이 임대 저장소와 Instagram 준비물·문맥의 결속을 확인한다."""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest

from common.operations.media_leases import MediaLeaseStore
from common.operations.models import ContractError
from common.publishers.instagram_media_leases import BoundInstagramMediaStager,InstagramLeaseAuthorityGuard
from common.publishers.instagram_media_sources import InstagramMediaSourceFactory
from tests.publishers.test_instagram_media_sources import NOW,JPEG,context,prepared,metadata


class InstagramMediaLeasesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'leases';self.store=MediaLeaseStore(self.root)
        self.ctx=context();self.prepared=prepared(self.ctx)
        self.allowed=True;self.clock=lambda:NOW

    def guard(self,ctx,payload):return self.allowed

    def stager(self,**over):
        args=dict(public_host='media.example.com',clock=self.clock,write_guard=self.guard)
        args.update(over)
        return BoundInstagramMediaStager(self.ctx,self.prepared,self.store,**args)

    def sources(self,stager=None):
        return InstagramMediaSourceFactory(lambda cid,rev,aid:(metadata(aid),JPEG),
            stager=stager or self.stager(),approval_guard=self.guard,
            allowed_hosts=('media.example.com',),clock=self.clock)

    def test_inert_default_no_guard_or_plan_context_never_creates_storage(self):
        stager=self.stager(write_guard=None)
        self.assertFalse(self.root.exists())
        with self.assertRaises(ContractError):self.sources(stager).prepare(self.ctx,self.prepared)
        self.assertFalse(self.root.exists())
        self.assertFalse(InstagramLeaseAuthorityGuard()({}))
        self.assertNotIn(self.tmp.name,repr(stager))

    def test_frozen_selection_preserves_order_bytes_and_reuses_exact_active_urls(self):
        self.store.initialize()
        source=self.sources();first=source.prepare(self.ctx,self.prepared)
        second=source.prepare(self.ctx,self.prepared)
        self.assertEqual(first,second)
        self.assertNotEqual(first[0].url,first[1].url)
        for index,receipt in enumerate(first):
            token=receipt.url.rsplit('/',1)[-1]
            row=self.store.lookup(token,now=NOW)
            self.assertEqual(row['request']['position'],index)
            self.assertEqual(row['authority']['prepared']['caption'],self.prepared['caption'])
            with self.store.open_payload(row['lease_id'],now=NOW) as stream:
                self.assertEqual(stream.read(),JPEG)
            self.assertTrue(InstagramLeaseAuthorityGuard(self.guard)(row))
        public=self.store.list_status(destination_account_id='dept',now=NOW)
        self.assertEqual(len(public),2)
        self.assertNotIn(first[0].url,str(public))
        self.assertNotIn(first[0].url.rsplit('/',1)[-1],str(public))
        self.assertEqual(self.store.list_status(destination_account_id='personal',now=NOW),[])

    def test_foreign_request_extra_fields_bool_indices_and_tampered_bytes_never_issue(self):
        class Store:
            def issue(self,**kwargs):raise AssertionError('must not issue')
        self.store=Store()
        stager=self.stager();captured=[]
        def capture(request,raw):
            captured.append((dict(request),raw));raise ContractError('fixture')
        with self.assertRaises(ContractError):self.sources(capture).prepare(self.ctx,self.prepared)
        request,raw=captured[0]
        for changes in (dict(position=True),dict(asset_size=True),dict(content_revision=True),
                dict(owner_account_id='dept'),dict(target_id='999'),dict(extra='x'),dict(context_hash='b'*64)):
            with self.assertRaises(ContractError):stager({**request,**changes},raw)
        with self.assertRaises(ContractError):stager(request,raw+b'changed')

    def test_current_review_revocation_is_distinct_from_spent_write_permission(self):
        self.store.initialize()
        receipt=self.sources().prepare(self.ctx,self.prepared)[0]
        row=self.store.lookup(receipt.url.rsplit('/',1)[-1],now=NOW)
        fetch=InstagramLeaseAuthorityGuard(self.guard)
        self.assertTrue(fetch(row))
        # GET 검토 guard는 이미 사용한 발행 permit을 재사용하지 않는다.
        self.allowed=False
        self.assertFalse(fetch(row))
        with self.assertRaises(ContractError):self.sources().prepare(self.ctx,self.prepared)

    def test_changed_private_context_or_prepared_request_never_passes_fetch_guard(self):
        self.store.initialize()
        receipt=self.sources().prepare(self.ctx,self.prepared)[0]
        row=self.store.lookup(receipt.url.rsplit('/',1)[-1],now=NOW)
        guard=InstagramLeaseAuthorityGuard(self.guard)
        for change in ('caption','context','request','size','extra'):
            changed=deepcopy(row)
            if change=='caption':changed['authority']['prepared']['caption']+='changed'
            elif change=='context':changed['authority']['context']['run_id']='foreign'
            elif change=='request':changed['request']['position']=True
            elif change=='size':changed['asset_size']+=1
            else:changed['authority']['extra']='secret'
            self.assertFalse(guard(changed),change)

    def test_auth_expiry_blocks_new_exposure_even_with_allowing_guard(self):
        self.clock=lambda:NOW+timedelta(hours=2)
        with self.assertRaises(ContractError):self.sources().prepare(self.ctx,self.prepared)
        self.assertFalse(self.root.exists())

    def test_authority_lost_during_issue_revokes_before_url_return(self):
        self.store.initialize();actual=self.store
        class Store:
            def issue(inner,**kwargs):
                result=actual.issue(**kwargs);self.allowed=False;return result
            def revoke(inner,*args,**kwargs):return actual.revoke(*args,**kwargs)
        self.store=Store()
        with self.assertRaises(ContractError):self.sources().prepare(self.ctx,self.prepared)
        statuses=actual.list_status(destination_account_id='dept',now=NOW)
        self.assertEqual(len(statuses),1)
        self.assertEqual(statuses[0]['status'],'revoked')


if __name__=='__main__':unittest.main()
