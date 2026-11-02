"""발행 자격의 논리적 계정·채널 결속만 순수 검증한다(backend 접근 없음)."""
from dataclasses import replace
from types import SimpleNamespace,MappingProxyType
from uuid import uuid4
import unittest
from common.operations.models import Connection,ContractError
from common.operations.oauth_models import CredentialRef
from common.operations.oauth_stage_models import OwnedCredentialRef
from common.publishers.credential_bindings import validate_publication_credential_binding,build_managed_bridge_credential_catalog


class CredentialBindingTests(unittest.TestCase):
    def owned(self,account='personal',platform='youtube',connection_id=None,generation=3,kind='token'):
        return OwnedCredentialRef(CredentialRef('autosns.oauth',account,platform,connection_id or account+'.youtube',generation,kind),uuid4().hex,'a'*64,'stage-owned')
    def managed(self,account='personal',platform='youtube',connection_id=None,generation=3):
        identifier=connection_id or account+'.youtube';ref=self.owned(account,platform,identifier,generation)
        key=f'oauth:{account}:{platform}:{identifier}:{generation}'
        conn=Connection(identifier,account,platform,credential_ref=key)
        entry=dict(account_id=account,platform=platform,credential_ref=ref)
        return SimpleNamespace(credentials=MappingProxyType({key:MappingProxyType(entry)})),conn,entry
    def rejected(self,registry,connection):
        with self.assertRaises(ContractError) as exc:validate_publication_credential_binding(registry,connection)
        self.assertEqual(exc.exception.code,'credential_owner_mismatch')
    def test_legacy_exact_entries_and_both_account_aliases_remain_valid(self):
        for account in ('personal','dept'):
            for platform in ('youtube','blogger'):
                identifier=account+'.'+platform;key=identifier+'.credential'
                conn=Connection(identifier,account,platform,credential_ref=key)
                registry=SimpleNamespace(credentials={key:dict(account_id=account,platform=platform)})
                self.assertIs(validate_publication_credential_binding(registry,conn),True)
                self.rejected(registry,replace(conn,credential_ref=key+'.other'))
    def test_managed_owned_token_generation_and_dotted_ids_validate(self):
        for account in ('personal','dept'):
            for platform in ('youtube','blogger'):
                registry,conn,_=self.managed(account,platform,account+'.'+platform+'.topic-name')
                self.assertIs(validate_publication_credential_binding(registry,conn),True)
    def test_unknown_entry_wrong_owner_platform_and_forged_key_refuse(self):
        registry,conn,entry=self.managed()
        self.rejected(SimpleNamespace(credentials={}),conn)
        for changes in (dict(account_id='dept'),dict(platform='blogger'),dict(credential_ref='/tmp/token'),dict(credential_ref=None)):
            self.rejected(SimpleNamespace(credentials={conn.credential_ref:{**entry,**changes}}),conn)
        for key in ('oauth:personal:youtube:personal.youtube:4','oauth:dept:youtube:personal.youtube:3','oauth:personal:youtube:personal.youtube:03','/tmp/token'):
            changed=replace(conn,credential_ref=key)
            self.rejected(SimpleNamespace(credentials={key:entry}),changed)
    def test_bare_logical_ref_or_other_kind_is_never_managed_token_fallback(self):
        registry,conn,entry=self.managed()
        for ref in (entry['credential_ref'].ref,self.owned(kind='client'),self.owned(account='dept'),self.owned(platform='blogger'),self.owned(connection_id='personal.youtube.other')):
            self.rejected(SimpleNamespace(credentials={conn.credential_ref:{**entry,'credential_ref':ref}}),conn)
    def test_invalidated_generation_and_owned_workspace_identity_fail_intrinsic_validation(self):
        for field,value in (('generation',0),('generation',True),('connection_id','../path'),('namespace','other')):
            registry,conn,entry=self.managed();object.__setattr__(entry['credential_ref'].ref,field,value)
            self.rejected(registry,conn)
        registry,conn,entry=self.managed();object.__setattr__(entry['credential_ref'],'root_binding','bad')
        self.rejected(registry,conn)
    def test_legacy_entry_wrong_owner_platform_and_nonmapping_are_rejected(self):
        conn=Connection('personal.youtube','personal','youtube',credential_ref='personal.youtube.credential')
        for entry in ({'account_id':'dept','platform':'youtube'},{'account_id':'personal','platform':'blogger'},'file:///token',None):
            self.rejected(SimpleNamespace(credentials={conn.credential_ref:entry}),conn)
        self.rejected(SimpleNamespace(credentials=None),conn)
        self.rejected(SimpleNamespace(credentials={}),replace(conn,credential_ref=None))

    def test_bridge_catalog_contains_only_symbolic_refs_and_public_binding_labels(self):
        registry,conn,entry=self.managed()
        legacy=Connection('dept.youtube','dept','youtube',credential_ref='dept.youtube.credential')
        credentials={conn.credential_ref:entry,legacy.credential_ref:dict(account_id='dept',platform='youtube')}
        combined=SimpleNamespace(credentials=credentials,connections={conn.id:conn,legacy.id:legacy,'dept.naver':Connection('dept.naver','dept','naver_blog')})
        catalog=build_managed_bridge_credential_catalog(combined)
        self.assertEqual(catalog,{conn.credential_ref:dict(credential_ref=conn.credential_ref,account_id='personal',platform='youtube'),legacy.credential_ref:dict(credential_ref=legacy.credential_ref,account_id='dept',platform='youtube')})
        for row in catalog.values():self.assertTrue(all(type(value) is str for value in row.values()))
        bad=SimpleNamespace(credentials={conn.credential_ref:{**entry,'account_id':'dept'}},connections={conn.id:conn})
        with self.assertRaises(ContractError):build_managed_bridge_credential_catalog(bad)

    def test_explicit_bridge_subset_checks_only_known_server_selected_connections(self):
        registry,conn,entry=self.managed()
        legacy=Connection('dept.youtube','dept','youtube',credential_ref='dept.youtube.credential')
        combined=SimpleNamespace(credentials={conn.credential_ref:entry,legacy.credential_ref:{'id':legacy.credential_ref}},connections={conn.id:conn,legacy.id:legacy})
        with self.assertRaises(ContractError):build_managed_bridge_credential_catalog(combined)
        expected={conn.credential_ref:dict(credential_ref=conn.credential_ref,account_id='personal',platform='youtube')}
        self.assertEqual(build_managed_bridge_credential_catalog(combined,connection_ids=[conn.id]),expected)
        self.assertEqual(build_managed_bridge_credential_catalog(combined,connection_ids=(conn.id,)),expected)
        for subset in ([],(),[conn.id,conn.id],['unknown'],[True],conn.id,{'connection':conn.id}):
            with self.assertRaises(ContractError):build_managed_bridge_credential_catalog(combined,connection_ids=subset)
