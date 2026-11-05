"""원고·음성 작업의 서버 소유 계정에 따른 음성 공급자 선택. 네트워크·실합성 없음."""
from pathlib import Path
import tempfile
import unittest

from common.operations.account_voice_service import AccountVoiceTaskService
from common.operations.content_store import ContentStore
from common.operations.models import ContractError
from common.operations.voice_tasks import VoiceTaskService,VoiceTaskStore
from tests.operations import test_voice_tasks as base


class AccountVoiceServiceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.env=base.Env(self.root/'fixture')
        self.personal=self.env.item
        self.dept=self.env.content.create('dept',dict(title='학과 숏츠',kind='short',original='대본'))
        self.clients={owner:base.FakeClient() for owner in ('personal','dept')}
        self.services={owner:VoiceTaskService(self.env.store,self.env.content,self.clients[owner],profile_id='voice-'+owner,enabled=True,probe=self.env.probe) for owner in self.clients}

    def facade(self,mapping=None):
        return AccountVoiceTaskService(self.env.store,self.env.content,self.services if mapping is None else mapping)

    def assert_code(self,code,call):
        with self.assertRaises(ContractError) as caught:call()
        self.assertEqual(caught.exception.code,code)

    def test_constructor_and_capabilities_are_inert_and_hide_profiles(self):
        root=self.root/'never-created';content=ContentStore(root);store=VoiceTaskStore(root)
        service=AccountVoiceTaskService(store,content,{})
        self.assertFalse(root.exists());self.assertFalse(service.enabled)
        expected=dict(provider_id='voicebox-local',service_available=False,execution_enabled=False,readiness='not_checked',external_fallback=False)
        self.assertEqual(service.capabilities(),expected)
        self.assertEqual(service.capabilities('personal'),expected)
        facade=self.facade({'personal':self.services['personal']})
        self.assertTrue(facade.capabilities()['execution_enabled']);self.assertTrue(facade.capabilities('personal')['execution_enabled'])
        self.assertEqual(facade.capabilities('dept'),expected);self.assertEqual(facade.capabilities('unknown'),expected)
        self.assertNotIn('profile',str(facade.capabilities()))
        self.assertTrue(all(c.ready_calls==0 and not c.generate_calls for c in self.clients.values()))

    def test_owner_is_resolved_from_content_and_each_client_uses_registered_profile(self):
        facade=self.facade();rows={}
        for owner,item in [('personal',self.personal),('dept',self.dept)]:
            rows[owner]=facade.create(item['id'],1,base.SCRIPT)
            self.assertEqual(rows[owner]['state'],'pending')
            self.assertEqual(self.clients[owner].generate_calls[0]['profile_id'],'voice-'+owner)
        self.assertNotEqual(rows['personal']['task_id'],rows['dept']['task_id'])
        with self.assertRaises(TypeError):facade.create(self.personal['id'],1,base.SCRIPT,owner_account_id='dept')
        self.assertEqual(len(self.clients['personal'].generate_calls),1);self.assertEqual(len(self.clients['dept'].generate_calls),1)

    def test_unmapped_owner_is_disabled_without_any_native_calls(self):
        facade=self.facade({'personal':self.services['personal']})
        self.assert_code('voicebox_disabled',lambda:facade.create(self.dept['id'],1,base.SCRIPT))
        self.assertTrue(all(c.ready_calls==0 and not c.generate_calls for c in self.clients.values()))
        self.assertEqual(self.env.store.list_for_content(self.dept['id']),[])

    def test_resume_dispatches_by_persisted_task_owner_not_view_context(self):
        facade=self.facade();row=facade.create(self.dept['id'],1,base.SCRIPT)
        done=facade.resume(row['task_id']);self.assertEqual(done['state'],'completed')
        self.assertEqual(self.clients['dept'].wait_calls,['gen-1']);self.assertEqual(self.clients['personal'].wait_calls,[])
        self.assertEqual(self.env.content.get(self.dept['id'])['revision'],2)
        self.assertEqual(self.env.content.get(self.personal['id'])['revision'],1)

    def test_recovery_methods_dispatch_to_persisted_owner(self):
        from tests.operations import test_voice_recovery as recovery
        client=recovery.RecoveryClient();client.overrides={'profile_id':'voice-dept'}
        self.services['dept']=VoiceTaskService(self.env.store,self.env.content,client,profile_id='voice-dept',enabled=True,probe=self.env.probe)
        facade=self.facade();client.generate_error=TimeoutError();row=facade.create(self.dept['id'],1,base.SCRIPT)
        preview=facade.inspect_recovery(row['task_id'],'existing1')
        linked=facade.confirm_recovery(row['task_id'],'existing1',preview['recovery_fingerprint'])
        self.assertEqual(linked['state'],'pending');self.assertEqual(client.inspect_calls,['existing1','existing1'])
        self.assertEqual(self.clients['personal'].generate_calls,[])

    def test_mapping_is_immutable_copy_and_shared_profile_is_explicitly_supported(self):
        mapping=dict(self.services);facade=self.facade(mapping);mapping.clear()
        self.assertTrue(facade.capabilities('dept')['execution_enabled'])
        with self.assertRaises(TypeError):facade.services['dept']=self.services['personal']
        self.services['dept']=VoiceTaskService(self.env.store,self.env.content,self.clients['dept'],profile_id='voice-personal',enabled=True,probe=self.env.probe)
        shared=self.facade();shared.create(self.dept['id'],1,base.SCRIPT)
        self.assertEqual(self.clients['dept'].generate_calls[0]['profile_id'],'voice-personal')

    def test_invalid_mappings_and_store_initialization_aliases_are_rejected(self):
        other=self.root/'other';other_store=VoiceTaskStore(other);other_content=ContentStore(other)
        alias_store=VoiceTaskStore(self.env.store.root)
        bad_services=[None,{'other':self.services['personal']},{'personal':object()},
            {'personal':VoiceTaskService(self.env.store,self.env.content,self.clients['personal'],profile_id='p',enabled=False)},
            {'personal':VoiceTaskService(other_store,self.env.content,self.clients['personal'],profile_id='p',enabled=True)},
            {'personal':VoiceTaskService(alias_store,self.env.content,self.clients['personal'],profile_id='p',enabled=True)},
            {'personal':VoiceTaskService(self.env.store,other_content,self.clients['personal'],profile_id='p',enabled=True)}]
        for mapping in bad_services:
            self.assert_code('invalid_voicebox_registration',lambda:AccountVoiceTaskService(self.env.store,self.env.content,mapping))
        self.assertFalse(other.exists())

    def test_changed_account_profile_preserves_existing_profile_guard(self):
        first=self.facade();row=first.create(self.personal['id'],1,base.SCRIPT)
        changed=VoiceTaskService(self.env.store,self.env.content,self.clients['personal'],profile_id='different',enabled=True,probe=self.env.probe)
        facade=self.facade({'personal':changed})
        before=self.env.store.get_row(row['task_id'])
        self.assert_code('voice_recovery_mismatch',lambda:facade.resume(row['task_id']))
        self.assertEqual(self.env.store.get_row(row['task_id']),before)
        self.assertEqual(self.clients['personal'].wait_calls,[]);self.assertEqual(self.clients['personal'].audio_calls,[])
        self.assertEqual(self.env.content.get(self.personal['id'])['revision'],1)
