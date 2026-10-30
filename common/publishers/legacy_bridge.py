"""등록된 Python 자식만 실행하는 서버 경계. import는 I/O를 하지 않는다."""
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import time

from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext, SubmissionPermit, serial, utc
from common.shared.axlock import _canon, read_control_state

READ_ACTIONS = frozenset(('inspect_target', 'lookup', 'verify'))
MAX_JSON = 1024 * 1024
SAFE_ENV = frozenset(('LANG', 'LC_ALL', 'LC_CTYPE', 'TZ', 'PATH'))


def _json_bytes(value):
    try:
        raw=json.dumps(serial(value),ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    except (ValueError,TypeError) as exc:
        raise ContractError('bridge_invalid_json') from exc
    if len(raw)>MAX_JSON:raise ContractError('bridge_size_limit')
    return raw


def prepared_digest(value):
    if not isinstance(value,Mapping):raise ContractError('bridge_invalid_payload')
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def resolve_registered_credentials(connection_id, *, registry, credential_catalog, resolver, scope='read'):
    """참조 소유와 플랫폼을 검증한 뒤에만 고정 resolver를 호출한다."""
    if scope not in ('read','publication'):raise ContractError('credential_scope')
    connection=registry.connections.get(connection_id)
    if connection is None:raise ContractError('unknown_connection')
    reference=connection.credential_ref
    if reference is None:return None
    registered=registry.credentials.get(reference)
    catalog=credential_catalog.get(reference) if isinstance(credential_catalog,Mapping) else None
    if (not isinstance(registered,Mapping) or not isinstance(catalog,Mapping) or
        registered.get('account_id')!=connection.account_id or
        registered.get('platform')!=connection.platform or
        catalog.get('account_id')!=connection.account_id or catalog.get('platform')!=connection.platform or
        catalog.get('credential_ref')!=reference or not callable(resolver)):
        raise ContractError('credential_owner_mismatch')
    return resolver(reference,account_id=connection.account_id,platform=connection.platform,scope=scope)


def _registered_spec(catalog,executor_id):
    spec=catalog.executors.get(executor_id)
    if spec is None:raise ContractError('bridge_unregistered_executor')
    if not Path(spec.interpreter).is_file() or not os.access(spec.interpreter,os.X_OK) or not spec.cwd.is_dir():
        raise ContractError('bridge_unavailable')
    module_path=spec.cwd.joinpath(*spec.module.split('.'))
    if not module_path.with_suffix('.py').is_file() and not (module_path/'__init__.py').is_file():
        raise ContractError('bridge_unavailable')
    return spec


def _connection(registry,ctx):
    if not isinstance(ctx,Mapping):raise ContractError('publication_context_required')
    connection=registry.connections.get(ctx.get('connection_id'))
    if (not connection or connection.account_id!=ctx.get('destination_account_id') or
        connection.target_id!=ctx.get('target_id') or connection.platform!=ctx.get('platform') or
        ctx.get('registry_revision')!=registry.revision):
        raise ContractError('bridge_context_mismatch')
    profile=registry.profiles.get(connection.profile_ref)
    if (not isinstance(profile,Mapping) or profile.get('account_id')!=connection.account_id or
        not isinstance(profile.get('lock_resource'),str) or not profile['lock_resource'].startswith('profile:')):
        raise ContractError('profile_lock_required')
    return connection,_canon(profile['lock_resource'])


def _process_start(pid):
    """PID 시작시각을 OS에서 읽는다. 외부 명령과 환경값은 쓰지 않는다."""
    try:
        import sys
        if sys.platform=='darwin':
            import ctypes
            class BSDInfo(ctypes.Structure):
                _fields_=[('ids',ctypes.c_uint32*12),('comm',ctypes.c_char*16),
                    ('name',ctypes.c_char*32),('tail',ctypes.c_uint32*6),
                    ('seconds',ctypes.c_uint64),('microseconds',ctypes.c_uint64)]
            info=BSDInfo();lib=ctypes.CDLL('/usr/lib/libproc.dylib',use_errno=True)
            read=lib.proc_pidinfo(pid,3,0,ctypes.byref(info),ctypes.sizeof(info))
            if read!=ctypes.sizeof(info) or not info.seconds:raise ValueError()
            return str(info.seconds)+':'+str(info.microseconds)
        if sys.platform.startswith('linux'):
            stat=Path('/proc')/str(pid)/'stat'
            return stat.read_text().rsplit(')',1)[1].split()[19]
    except (OSError,ValueError,IndexError) as exc:raise ContractError('bridge_parent_identity') from exc
    raise ContractError('bridge_parent_identity')


def parent_evidence(registry,locks,context):
    _,resource=_connection(registry,context)
    holder=locks.holder_of(resource)
    if (not isinstance(holder,dict) or holder.get('resource')!=resource or holder.get('pid')!=os.getpid() or
        not isinstance(holder.get('job'),str) or not holder['job'] or
        not isinstance(holder.get('since'),str) or not holder['since']):
        raise ContractError('bridge_parent_lock_required')
    try:fd=locks.owned_descriptor(resource)
    except (OSError,ValueError,AttributeError) as exc:raise ContractError('bridge_parent_lock_required') from exc
    return dict(holder,process_started_at=_process_start(os.getpid()),lock_fd=fd)


def check_parent_evidence(registry,locks,context,evidence,*,parent_pid):
    _,resource=_connection(registry,context)
    if (not isinstance(evidence,dict) or set(evidence)!={'resource','pid','job','since','process_started_at','lock_fd'} or
        evidence.get('resource')!=resource or evidence.get('pid')!=parent_pid or
        evidence.get('process_started_at')!=_process_start(parent_pid)):
        raise ContractError('bridge_parent_identity')
    holder=locks.holder_of(resource)
    if not isinstance(holder,dict) or holder!={k:evidence[k] for k in ('resource','pid','job','since')}:
        raise ContractError('bridge_parent_lock_required')
    try:locks.verify_descriptor(resource,evidence['lock_fd'])
    except (OSError,ValueError,AttributeError) as exc:raise ContractError('bridge_parent_lock_required') from exc


def validate_job_binding(registry,store,spec,context):
    run=store.get_run(context.get('run_id'))
    occurrence=(run or {}).get('occurrence') or {}
    job=registry.jobs.get(occurrence.get('job_id'))
    connections=(job.get('connection_ids') or (job.get('connection_id'),)) if job else ()
    if (occurrence.get('job_id') not in spec.job_ids or occurrence.get('phase') not in spec.phases or
        occurrence.get('mode')!='live' or not job or job.get('enabled') is not True or
        job.get('execution_owner')!='managed' or context.get('connection_id') not in connections or
        job.get('owner_account_id')!=context.get('owner_account_id') or
        job.get('policy_revision')!=context.get('policy_revision')):
        raise ContractError('bridge_job_mismatch')
    return run


def _clear(locks):
    if read_control_state(locks.paths)['state']!='clear':raise ContractError('control_blocked')


class LegacyBridge:
    def __init__(self,registry,catalog,store,locks,*,spawn=subprocess.Popen,clock=None):
        self.registry=registry;self.catalog=catalog;self.store=store;self.locks=locks
        self.spawn=spawn;self.clock=clock or (lambda:datetime.now(timezone.utc));self.timeout=60

    def read(self,executor_id,action,context,payload):
        if action not in READ_ACTIONS:raise ContractError('bridge_read_action_required')
        spec=_registered_spec(self.catalog,executor_id)
        if not set(spec.phases)&{'submit','verify'}:raise ContractError('bridge_action_unregistered')
        if isinstance(context,PublicationContext):context=context.to_dict()
        if not isinstance(payload,Mapping):raise ContractError('bridge_invalid_payload')
        if not isinstance(context,Mapping):raise ContractError('publication_context_required')
        validate_job_binding(self.registry,self.store,spec,context)
        _clear(self.locks)
        evidence=parent_evidence(self.registry,self.locks,context)
        return self._call(spec,action,dict(context=context,payload=payload,parent=evidence),None)

    def submit(self,executor_id,ctx,prepared,permit):
        spec=_registered_spec(self.catalog,executor_id)
        if len(spec.mutation_actions)!=1 or 'submit' not in spec.phases:raise ContractError('bridge_action_unregistered')
        if (not isinstance(ctx,PublicationContext) or not isinstance(permit,SubmissionPermit) or
            permit.context_hash!=ctx.context_hash or permit.run_id!=ctx.run_id or permit.expires_at<=utc(self.clock())):
            raise ContractError('bridge_invalid_permit')
        prepared_hash=prepared_digest(prepared)
        attempt=self.store.get_attempt(permit.attempt_id)
        run=self.store.get_run(ctx.run_id)
        if (not attempt or attempt['context_hash']!=ctx.context_hash or not attempt['request_started'] or
            attempt['resolved'] or attempt['outcome'] is not None or not run or
            (run.get('process_identity') or {}).get('pid')!=os.getpid()):
            raise ContractError('bridge_invalid_attempt')
        occurrence=run.get('occurrence') or {}
        if (occurrence.get('job_id') not in spec.job_ids or occurrence.get('phase')!='submit' or
            occurrence.get('mode')!='live'):
            raise ContractError('bridge_job_mismatch')
        _clear(self.locks)
        evidence=parent_evidence(self.registry,self.locks,ctx.to_dict())
        return self._call(spec,spec.mutation_actions[0],dict(context=ctx.to_dict(),payload=prepared,
            prepared_hash=prepared_hash,permit=permit.to_dict(),parent=evidence),permit.nonce)

    def _call(self,spec,action,request,nonce):
        raw=_json_bytes(request)
        env={key:os.environ[key] for key in spec.environment_names if key in SAFE_ENV and key in os.environ}
        # 코드 위치는 서버가 결정한다. caller의 PYTHONPATH/AX_LOCKED는 계승하지 않는다.
        env['PYTHONPATH']=str(Path(__file__).resolve().parents[2])
        read_fd,write_fd=os.pipe()
        process=None
        try:
            if nonce is not None:
                encoded=_json_bytes(dict(nonce=nonce,executor_id=spec.id,action=action,
                    context_hash=request['permit']['context_hash'],prepared_hash=request['prepared_hash']))
                if len(encoded)>2048:raise ContractError('bridge_invalid_permit')
                os.write(write_fd,encoded)
            os.close(write_fd);write_fd=None
            argv=[spec.interpreter,'-m',spec.module,'--executor',spec.id,'--action',action,'--secret-fd',str(read_fd)]
            process=self.spawn(argv,cwd=str(spec.cwd),env=env,pass_fds=(read_fd,request['parent']['lock_fd']),stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            os.close(read_fd);read_fd=None
            stdout=self._exchange(process,raw)
            if process.returncode:raise ContractError('bridge_child_failed')
            try:result=json.loads(stdout)
            except (ValueError,UnicodeDecodeError) as exc:raise ContractError('bridge_invalid_result') from exc
            if not isinstance(result,dict):raise ContractError('bridge_invalid_result')
            if nonce is not None and nonce in _json_bytes(result).decode():raise ContractError('bridge_secret_output')
            return result
        finally:
            if read_fd is not None:os.close(read_fd)
            if write_fd is not None:os.close(write_fd)
            if process is not None:
                if process.poll() is None:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    process.wait()
                for pipe in (process.stdin,process.stdout,process.stderr):
                    if pipe is not None:pipe.close()

    def _exchange(self,process,raw):
        deadline=time.monotonic()+self.timeout
        output=bytearray();errors=0;offset=0
        with selectors.DefaultSelector() as selector:
            for stream,event,kind in ((process.stdin,selectors.EVENT_WRITE,'in'),
                                      (process.stdout,selectors.EVENT_READ,'out'),
                                      (process.stderr,selectors.EVENT_READ,'err')):
                os.set_blocking(stream.fileno(),False);selector.register(stream,event,kind)
            while selector.get_map():
                remaining=deadline-time.monotonic()
                if remaining<=0:raise ContractError('bridge_timeout')
                for key,_ in selector.select(min(.05,remaining)):
                    stream=key.fileobj
                    if key.data=='in':
                        try:offset+=os.write(stream.fileno(),raw[offset:offset+65536])
                        except BrokenPipeError:offset=len(raw)
                        if offset==len(raw):selector.unregister(stream);stream.close()
                        continue
                    chunk=os.read(stream.fileno(),65536)
                    if not chunk:selector.unregister(stream);continue
                    if key.data=='out':
                        output.extend(chunk)
                        if len(output)>MAX_JSON:raise ContractError('bridge_size_limit')
                    else:
                        errors+=len(chunk)
                        if errors>4096:raise ContractError('bridge_size_limit')
            try:process.wait(timeout=max(.001,deadline-time.monotonic()))
            except subprocess.TimeoutExpired as exc:raise ContractError('bridge_timeout') from exc
        return bytes(output)
