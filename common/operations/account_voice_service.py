"""서버 원고·작업 소유 계정으로 등록 음성 서비스를 선택한다. 생성자는 I/O를 하지 않는다.

계정/프로필을 HTTP 입력으로 받거나 비등록 계정에 다른 목소리로 fallback하지 않는다.
개별 서비스가 기존 intent·프로필·CAS·작업 잠금 검증을 그대로 수행한다.
"""
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from .content_store import ContentStore
from .models import ContractError
from .voice_tasks import VoiceTaskService,VoiceTaskStore,_content_id,_revision,_task_id

_ACCOUNTS=('personal','dept')


def _invalid():
    raise ContractError('invalid_voicebox_registration')


class AccountVoiceTaskService(VoiceTaskService):
    """공통 HTTP 계약을 유지하는 facade. base의 private 실행 메서드는 사용하지 않는다."""
    def __init__(self,store,content_store,services):
        if (not isinstance(store,VoiceTaskStore) or not isinstance(content_store,ContentStore)
                or not isinstance(services,Mapping)):
            _invalid()
        registered={}
        for account,service in services.items():
            if (account not in _ACCOUNTS or not isinstance(service,VoiceTaskService)
                    or isinstance(service,AccountVoiceTaskService)
                    or service.enabled is not True or service.store is not store
                    or not isinstance(service.content_store,ContentStore)
                    or Path(service.content_store.root).resolve()!=Path(content_store.root).resolve()):
                _invalid()
            # 같은 프로필을 두 계정에 명시 등록하는 것은 허용한다.
            registered[account]=service
        self.store,self.content_store=store,content_store
        self.services=MappingProxyType(registered)
        self.enabled=bool(registered)

    def capabilities(self,account=None):
        enabled=bool(self.services) if account is None else account in _ACCOUNTS and account in self.services
        return dict(provider_id='voicebox-local',service_available=bool(enabled),execution_enabled=bool(enabled),
                    readiness='not_checked',external_fallback=False)

    def _for_owner(self,owner):
        service=self.services.get(owner) if isinstance(owner,str) else None
        if service is None:
            raise ContractError('voicebox_disabled')
        return service

    def create(self,content_id,expected_revision,script,seed=14005):
        content_id,revision=_content_id(content_id),_revision(expected_revision)
        snapshot=self._snapshot(content_id,revision)
        if snapshot is None:
            raise ContractError('content_not_found')
        return self._for_owner(snapshot['owner_account_id']).create(content_id,revision,script,seed)

    def _for_task(self,task_id):
        row=self.store.get_row(_task_id(task_id))
        if row is None:
            raise ContractError('task_not_found')
        return self._for_owner(row['owner_account_id'])

    def resume(self,task_id):
        return self._for_task(task_id).resume(task_id)

    def inspect_recovery(self,task_id,generation_id):
        return self._for_task(task_id).inspect_recovery(task_id,generation_id)

    def confirm_recovery(self,task_id,generation_id,recovery_fingerprint):
        return self._for_task(task_id).confirm_recovery(task_id,generation_id,recovery_fingerprint)
