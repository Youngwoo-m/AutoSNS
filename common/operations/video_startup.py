"""서버 코드가 명시 등록한 영상 제작기만 조립한다. 생성·검증 중에는 실행하지 않는다."""
from dataclasses import dataclass
from .bootstrap_config import BootstrapConfig
from .content_store import ContentStore
from .media_plans import MediaPlanStore
from .models import ContractError
from .video_tasks import VideoTaskService,VideoTaskStore


@dataclass(frozen=True)
class VideoRegistration:
    runner_factory: object
    reuse_authorization: object
    probe: object
    inspect_video: object


def validate_video_registration(registration):
    """웹의 경로·명령·검토 플래그를 등록으로 취급하지 않는다."""
    if not isinstance(registration,VideoRegistration) or not all(callable(getattr(registration,key)) for key in
            ('runner_factory','reuse_authorization','probe','inspect_video')):
        raise ContractError('video_registration_required')
    return registration


def build_video_task_service(*,config,content_store,registration=None,activate=False):
    if type(activate) is not bool:raise ContractError('invalid_video_activation')
    if not activate:return None
    registration=validate_video_registration(registration)
    if (not isinstance(config,BootstrapConfig) or not isinstance(content_store,ContentStore) or
            content_store.root.resolve()!=config.workspace_root.resolve()):
        raise ContractError('video_workspace_mismatch')
    # /var와 /private/var 같은 별칭을 허용한 뒤에는 ContentStore의 표기를 공유한다.
    root=content_store.root
    return VideoTaskService(VideoTaskStore(root),content_store,
        MediaPlanStore(root,content_store),enabled=True,
        runner_factory=registration.runner_factory,reuse_authorization=registration.reuse_authorization,
        probe=registration.probe,inspect_video=registration.inspect_video)
