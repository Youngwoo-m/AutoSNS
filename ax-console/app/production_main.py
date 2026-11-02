"""저장한 계정별 제작 설정을 사용하는 명시적 기동 명령. 기본은 무변이 점검."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import ipaddress
import json
import re
import signal
import sys

_APP=Path(__file__).resolve().parent
for root in (_APP.parents[1],_APP):
    if str(root) not in sys.path:sys.path.insert(0,str(root))
from common.operations.bootstrap_config import BootstrapConfig
from common.operations.models import ContractError
from common.operations.content_store import StoreError
from common.operations.production_settings import ProductionSettingsStore,compile_production_settings
from common.operations.production_startup import build_production_runtime
from common.operations.installed_claude import InstalledClaudeRunner
from common.operations.registry import load_registry
from common.operations.tool_cost_policy import ToolkitPolicy
from common.operations.voicebox_client import LocalVoiceboxClient
from common.operations.voice_tasks import VoiceTaskService,VoiceTaskStore
from common.operations.video_startup import build_video_task_service,validate_video_registration
from production_application import build_production_application

_VOICEBOX_PROFILE=re.compile(r'[A-Za-z0-9_-]{1,128}')


def parser():
    p=argparse.ArgumentParser(description='계정별 제작 웹 기동. 기본은 무변이 설정 점검입니다.')
    p.add_argument('--source-root',required=True,type=Path)
    p.add_argument('--workspace-root',required=True,type=Path)
    p.add_argument('--registry',type=Path,default=_APP.parent/'config/operations.json')
    mode=p.add_mutually_exclusive_group();mode.add_argument('--check',action='store_true');mode.add_argument('--serve',action='store_true')
    p.add_argument('--enable-production',action='store_true')
    p.add_argument('--enable-voicebox',action='store_true')
    p.add_argument('--enable-video',action='store_true',help='신뢰된 서버 제작기·검사기 등록이 있을 때 영상 worker를 활성화합니다')
    p.add_argument('--voicebox-profile-id');p.add_argument('--voicebox-port',type=int,default=17493)
    p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8769)
    p.add_argument('--local-toolkit',action='store_true')
    p.add_argument('--claude-executable',type=Path);p.add_argument('--claude-home',type=Path);p.add_argument('--claude-user')
    p.add_argument('--model',default='sonnet')
    return p


def _validate(args):
    for path in (args.source_root,args.workspace_root,args.registry):
        if not path.is_absolute():raise ContractError('invalid_bootstrap_config')
    source,workspace=args.source_root.resolve(),args.workspace_root.resolve()
    if source.is_relative_to(workspace) or workspace.is_relative_to(source):raise ContractError('invalid_bootstrap_config')
    try:address=ipaddress.ip_address('127.0.0.1' if args.host=='localhost' else args.host)
    except ValueError:raise ContractError('invalid_bootstrap_config') from None
    if not address.is_loopback or not 0<=args.port<=65535:raise ContractError('invalid_bootstrap_config')
    if args.enable_production and not args.serve:raise ContractError('activation_requires_serve')
    if args.enable_video and not args.serve:raise ContractError('activation_requires_serve')
    if args.enable_production and not (args.claude_executable and args.claude_home and args.claude_user):
        raise ContractError('subscription_configuration_required')
    # Voicebox 옵션: 비활성이어도 값이 주어지면 형식은 검증하지만 활성화하지 않는다.
    profile,port=args.voicebox_profile_id,args.voicebox_port
    if profile is not None and _VOICEBOX_PROFILE.fullmatch(profile) is None:raise ContractError('invalid_voicebox_registration')
    if type(port) is not int or not 1<=port<=65535:raise ContractError('invalid_voicebox_registration')
    if args.enable_voicebox:
        if not args.serve:raise ContractError('activation_requires_serve')
        if profile is None:raise ContractError('voicebox_profile_required')
    return BootstrapConfig(source_root=source,workspace_root=workspace,registry_path=args.registry)


def run(args,*,runner_factory=InstalledClaudeRunner,runtime_builder=build_production_runtime,
        application_builder=build_production_application,quota_preparer=None,clock=None,
        voice_client_factory=LocalVoiceboxClient,voice_service_factory=VoiceTaskService,
        video_registration=None):
    """check는 읽기만 한다. serve/enable은 CLI에서 명시적으로 선택해야 한다."""
    config=_validate(args);clock=clock or (lambda:datetime.now(timezone.utc))
    if args.enable_video:validate_video_registration(video_registration)
    planning=load_registry(args.registry)
    settings=ProductionSettingsStore(config.workspace_root)
    rows=[settings.get(account) for account in ('personal','dept')]
    compiled=compile_production_settings(rows,accounts=planning.accounts,code_root=config.code_root,
        interpreter=Path(sys.executable).absolute(),activate=args.enable_production)
    summary=dict(mode='check',execution_enabled=False,settings_revision=compiled.registry.revision,
        accounts=[dict(account_id=row['account_id'],enabled_preference=row['enabled_preference'],daily_limit=row['daily_limit']) for row in rows],
        native_probe_performed=False,quota_modified=False,voicebox_enabled=False,video_enabled=False)
    if not args.serve:return summary
    runner=None
    if args.enable_production:
        if not compiled.policy.enabled:raise ContractError('production_settings_required')
        runner=runner_factory(args.claude_executable,args.claude_home,args.claude_user,args.model)
        verified=runner.verify()
        if verified.get('verified') is not True:raise ContractError('subscription_verification_failed')
    if compiled.policy.enabled and quota_preparer is None:
        from common.operations.production_quota import prepare_managed_text_quota
        quota_preparer=prepare_managed_text_quota
    runtime=runtime_builder(config=config,registry=compiled.registry,catalog=compiled.catalog,
        policy=compiled.policy,subscription_runner=runner,quota_preparer=quota_preparer if compiled.policy.enabled else None,clock=clock,initialize=False)
    extra={}
    if args.enable_video:
        extra['video_task_service']=build_video_task_service(config=config,
            content_store=runtime.service.store.content_store,registration=video_registration,activate=True)
    if args.enable_voicebox:
        # 생성자는 I/O가 없다. ready 조회/합성/앱 기동은 하지 않고 저장소 초기화는 application이 맡는다.
        client=voice_client_factory(args.voicebox_profile_id,port=args.voicebox_port)
        extra['voice_task_service']=voice_service_factory(VoiceTaskStore(config.workspace_root),
            runtime.service.store.content_store,client,profile_id=args.voicebox_profile_id,enabled=True)
    app=application_builder(runtime=runtime,config=config,planning_registry=planning,host=args.host,port=args.port,
        web_root=_APP/'web',toolkit_policy=ToolkitPolicy(enabled=args.local_toolkit),**extra)
    previous={};requested=False
    def stop(signum,frame):
        nonlocal requested
        requested=True
        if app.state=='serving':app.request_shutdown()
    try:
        app.initialize_storage()
        if compiled.policy.enabled:
            quota_preparer(runtime.service.store,compiled.registry,clock())
        if __import__('threading').current_thread() is __import__('threading').main_thread():
            for signum in (signal.SIGTERM,signal.SIGINT):previous[signum]=signal.signal(signum,stop)
        if not requested:app.serve_forever()
        return dict(summary,mode='serve',execution_enabled=compiled.policy.enabled,
                    native_probe_performed=runner is not None,quota_modified=compiled.policy.enabled,
                    voicebox_enabled=bool(args.enable_voicebox),video_enabled=bool(args.enable_video))
    finally:
        for signum,handler in previous.items():signal.signal(signum,handler)
        if app.state=='built':app.close()


def main(argv=None):
    args=parser().parse_args(argv)
    try:result=run(args)
    except (ContractError,StoreError,OSError) as error:
        print(json.dumps(dict(ok=False,reason_code=getattr(error,'code','startup_failed')),ensure_ascii=False))
        return 1
    print(json.dumps(dict(ok=True,**result),ensure_ascii=False))
    return 0

if __name__=='__main__':raise SystemExit(main())
