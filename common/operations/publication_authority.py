"""관리 자격 metadata와 별도 발행 사용 승인의 결속. 비밀값을 받지 않는다.

Grant 발급자는 실제 공급자 관측과 사용자 승인을 검증해야 한다. 이 모듈은 grant를
발급하거나 scope·계정 권한을 합성하지 않는다. 현재 등록을 조회해 세대/대상/앱 변경을
막으며 실제 콘텐츠 승인·실행 permit·STOP·공급자 비용 gate는 계속 별도로 필요하다.
"""
import hashlib
import json
from collections.abc import Mapping
from .oauth_models import OAuthClientRegistration
from .oauth_stage_models import OwnedCredentialRef,encode_stored_ref,logical_ref
from .publication_grants import PublicationGrantBinding
from .runtime_models import utc


def credential_fingerprint(ref):
    if type(ref) is not OwnedCredentialRef:raise ValueError('invalid_publication_binding')
    return hashlib.sha256(json.dumps(encode_stored_ref(ref),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class ManagedPublicationAuthorizer:
    def __init__(self,grant_store,registrations_supplier):
        if (not callable(getattr(grant_store,'current',None)) or not callable(registrations_supplier)):
            raise ValueError('invalid_publication_authorizer')
        self.store=grant_store;self.registrations=registrations_supplier

    def __repr__(self):return 'ManagedPublicationAuthorizer(<private>)'

    def _grant(self,*,reference,account_id,platform,snapshot,registry,connection,credential_ref,observed_scopes,now,target_id=None,**unused):
        logical=logical_ref(credential_ref)
        registrations=self.registrations()
        client=registrations.get(connection.get('provider_id')) if isinstance(registrations,Mapping) else None
        if (type(client) is not OAuthClientRegistration or type(credential_ref) is not OwnedCredentialRef
                or account_id!=logical.account_id or platform!=logical.platform
                or reference!=f'oauth:{account_id}:{platform}:{logical.connection_id}:{logical.generation}'
                or snapshot.workspace_owner!=self.store.context.owner
                or (credential_ref.workspace_id,credential_ref.root_binding)!=(self.store.context.owner.workspace_id,self.store.context.owner.root_binding)
                or connection.get('connection_id')!=logical.connection_id or connection.get('account_id')!=account_id
                or connection.get('platform')!=platform or connection.get('credential_generation')!=logical.generation
                or connection.get('credential_ref')!=credential_ref or snapshot.base_revision!=registry.revision
                or connection.get('base_revision')!=registry.revision
                or target_id is not None and target_id!=connection.get('target_id')
                or client.provider_id!=connection.get('provider_id')):
            return None
        binding=PublicationGrantBinding(owner=self.store.context.owner,registry_revision=registry.revision,
            connection_id=logical.connection_id,account_id=account_id,platform=platform,
            provider_id=client.provider_id,target_id=connection['target_id'],provider_subject=connection['provider_subject'],
            connection_revision=connection['revision'],credential_generation=logical.generation,
            credential_fingerprint=credential_fingerprint(credential_ref),client_revision=client.client_revision,
            evidence_revision=client.cost_evidence_revision)
        grant=self.store.current(binding,now=now)
        if (grant is None or set(grant.observed_scopes)!=set(observed_scopes)
                or not set(grant.observed_scopes)<=set(client.approved_scopes)
                or utc(grant.expires_at)>utc(connection['authorization']['credential_expires_at'])):return None
        return grant

    def precheck(self,**state):
        try:return self._grant(**state) is not None
        except Exception:return False

    def authorize(self,*,granted_scopes,credential_expires_at,**state):
        try:
            grant=self._grant(**state)
            return (grant is not None and set(grant.observed_scopes)<=set(granted_scopes)
                    and utc(grant.expires_at)<=utc(credential_expires_at))
        except Exception:return False
