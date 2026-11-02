"""고정 launcher가 주입한 서버 bootstrap만 쓰는 자식 leaf 경계.

등록 launcher의 __main__ 예시::
    main(bootstrap=bridge_bootstrap, bootstrap_module=__spec__.name)

bootstrap은 서버 파일에서 registry/catalog/store/locks/handler를 조립한다.
stdin과 argv는 코드·저장소·credential 경로를 선택할 수 없다.
"""
from collections.abc import Mapping
from contextlib import redirect_stdout, redirect_stderr,contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from common.operations.admission_context import decode_bridge_context
from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext, SubmissionPermit, utc
from common.operations.publication_gate import fresh_lease, require_publication_approval, _time_valid
from .legacy_bridge import (MAX_JSON, READ_ACTIONS, _clear, _json_bytes, _registered_spec,
    _connection, prepared_digest, check_parent_evidence, resolve_registered_credentials, validate_job_binding)


class _Discard:
    """legacy의 print와 예외 원문을 파이프·로그로 내보내지 않는다."""
    def write(self,text):return len(text)
    def flush(self):pass


class BridgeHost:
    def __init__(self,registry,catalog,store,locks,handlers,*,credential_catalog=None,
                 credential_resolver=None,clock=None,module_root=None):
        self.registry=registry;self.catalog=catalog;self.store=store;self.locks=locks
        self.store.locks=locks
        self.module_root=module_root
        self.handlers=dict(handlers);self.credential_catalog=credential_catalog or {}
        self.credential_resolver=credential_resolver
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def execute(self,executor_id,action,request,nonce,*,bootstrap_module,parent_pid,secret_binding=None):
        spec=_registered_spec(self.catalog,executor_id,module_root=self.module_root)
        if (spec.module!=bootstrap_module or Path(sys.executable).resolve()!=Path(spec.interpreter).resolve() or
            Path.cwd().resolve()!=spec.cwd.resolve()):raise ContractError('bridge_executor_mismatch')
        if not isinstance(request,dict):raise ContractError('bridge_invalid_json')
        mutation=action in spec.mutation_actions
        keys={'context','payload','parent','permit','prepared_hash'} if mutation else {'context','payload','parent'}
        if set(request)!=keys or not isinstance(request['payload'],dict):raise ContractError('bridge_invalid_payload')
        if (not mutation and action not in READ_ACTIONS) or (mutation and 'submit' not in spec.phases):
            raise ContractError('bridge_action_unregistered')
        handler=self.handlers.get((executor_id,action))
        if not callable(handler):raise ContractError('bridge_unavailable')
        ctx=decode_bridge_context(request['context'],action)
        _connection(self.registry,ctx.to_dict())
        validate_job_binding(self.registry,self.store,spec,ctx.to_dict())
        check_parent_evidence(self.registry,self.locks,ctx.to_dict(),request['parent'],parent_pid=parent_pid)
        _clear(self.locks)
        if not mutation:
            if nonce:raise ContractError('bridge_invalid_permit')
            # 새 자격은 읽기 handler가 끝날 때까지 작업공간 소유·세대 guard 안에서 사용한다.
            with self._credential_scope(ctx,'read') as credentials:
                return handler(ctx.to_dict(),request['payload'],credentials)
        if not nonce or len(spec.mutation_actions)!=1:raise ContractError('bridge_invalid_permit')
        expected_binding=dict(executor_id=executor_id,action=action,context_hash=ctx.context_hash,prepared_hash=request['prepared_hash'])
        if secret_binding!=expected_binding:raise ContractError('bridge_invalid_permit')
        permit=SubmissionPermit(nonce=nonce,**request['permit'])
        if (permit.context_hash!=ctx.context_hash or permit.run_id!=ctx.run_id or
            prepared_digest(request['payload'])!=request['prepared_hash']):
            raise ContractError('bridge_invalid_permit')
        attempt=self.store.get_attempt(permit.attempt_id)
        run=self.store.get_run(ctx.run_id)
        if (not run or not attempt or (run.get('process_identity') or {}).get('pid')!=parent_pid or
            attempt['context_hash']!=ctx.context_hash):raise ContractError('bridge_invalid_attempt')
        occurrence=run.get('occurrence') or {}
        job=self.registry.jobs.get(occurrence.get('job_id'))
        connection_ids=(job.get('connection_ids') or (job.get('connection_id'),)) if job else ()
        if (occurrence.get('job_id') not in spec.job_ids or occurrence.get('phase')!='submit' or
            occurrence.get('mode')!='live' or not job or job.get('enabled') is not True or
            job.get('execution_owner')!='managed' or ctx.connection_id not in connection_ids or
            job.get('owner_account_id')!=ctx.owner_account_id or job.get('policy_revision')!=ctx.policy_revision):
            raise ContractError('bridge_job_mismatch')
        # credential 준비는 승인/STOP writer를 막지 않는 허가 이전 단계다.
        if callable(getattr(self.credential_resolver,'use',None)):
            raise ContractError('managed_publication_unverified')
        credentials=self._credentials(ctx,'publication')
        with self.locks.publication_guard(job='bridge-leaf',wait=10):
            _clear(self.locks)
            check_parent_evidence(self.registry,self.locks,ctx.to_dict(),request['parent'],parent_pid=parent_pid)
            checked=utc(self.clock())
            lease=fresh_lease(self.store,ctx.run_id,checked)
            _time_valid(self.store,ctx,lease,checked,permit)
            require_publication_approval(self.store,attempt['delivery_id'],ctx)
            # 새 heartbeat lease와 실제 gate/DB 대기 뒤 clock을 다시 사용한다.
            self.store.redeem_bridge(permit,executor_id,action,request['prepared_hash'],checked,clock=self.clock)
        # 허가는 redemption commit에서 선형화됐다. 이후 STOP/철회는 이미 시작된
        # 요청의 취소 성공을 뜻하지 않으며 외부 I/O 동안 gate를 잡지 않는다.
        return handler(ctx.to_dict(),request['payload'],credentials)

    @contextmanager
    def _credential_scope(self,ctx,scope):
        use=getattr(self.credential_resolver,'use',None)
        if not callable(use):
            yield self._credentials(ctx,scope)
            return
        scoped=resolve_registered_credentials(ctx.connection_id,registry=self.registry,
            credential_catalog=self.credential_catalog,
            resolver=lambda reference,**binding:use(reference,**binding,target_id=ctx.target_id),scope=scope)
        with scoped as credentials:
            yield credentials

    def _credentials(self,ctx,scope):
        return resolve_registered_credentials(ctx.connection_id,registry=self.registry,
            credential_catalog=self.credential_catalog,resolver=self.credential_resolver,scope=scope)


def _arguments(argv):
    if len(argv)!=6:raise ContractError('bridge_invalid_arguments')
    result={}
    for offset in range(0,6,2):
        key,value=argv[offset:offset+2]
        if key not in ('--executor','--action','--secret-fd') or key in result or not value:
            raise ContractError('bridge_invalid_arguments')
        result[key]=value
    if len(result)!=3:raise ContractError('bridge_invalid_arguments')
    try:fd=int(result['--secret-fd'])
    except ValueError as exc:raise ContractError('bridge_invalid_arguments') from exc
    if fd<3:raise ContractError('bridge_invalid_arguments')
    return result['--executor'],result['--action'],fd


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ContractError('bridge_invalid_json')
        result[key]=value
    return result


def main(argv=None,*,bootstrap=None,bootstrap_module=None):
    """등록 모듈만 callable bootstrap을 전달한다. 기본값은 사용 불가다."""
    out=sys.stdout;err=sys.stderr
    try:
        if not callable(bootstrap) or not isinstance(bootstrap_module,str):raise ContractError('bridge_unavailable')
        executor,action,fd=_arguments(list(sys.argv[1:] if argv is None else argv))
        try:
            secret=os.read(fd,2049)
            if len(secret)>2048:raise ContractError('bridge_invalid_permit')
        finally:os.close(fd)
        binding=json.loads(secret,object_pairs_hook=_unique) if secret else {}
        if not isinstance(binding,dict):raise ContractError('bridge_invalid_permit')
        nonce=binding.pop('nonce','')
        if not isinstance(nonce,str):raise ContractError('bridge_invalid_permit')
        raw=sys.stdin.buffer.read(MAX_JSON+1)
        if len(raw)>MAX_JSON:raise ContractError('bridge_size_limit')
        request=json.loads(raw,object_pairs_hook=_unique)
        with redirect_stdout(_Discard()),redirect_stderr(_Discard()):
            host=bootstrap()
            if not isinstance(host,BridgeHost):raise ContractError('bridge_unavailable')
            result=host.execute(executor,action,request,nonce,bootstrap_module=bootstrap_module,parent_pid=os.getppid(),secret_binding=binding)
        if not isinstance(result,Mapping):raise ContractError('bridge_invalid_result')
        encoded=_json_bytes(result)
        if nonce and nonce.encode() in encoded:raise ContractError('bridge_secret_output')
        out.write(encoded.decode());out.flush()
        return 0
    except BaseException:
        # argv/credentials/예외 원문은 상위로 전달하지 않는다.
        err.write('bridge_child_failed\n');err.flush()
        return 2


if __name__=='__main__':
    raise SystemExit(main())
