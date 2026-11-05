"""신뢰된 로컬 이미지 제작기 등록. 조립은 저장소 초기화·렌더·외부 호출을 하지 않는다."""
from dataclasses import dataclass
from .bootstrap_config import BootstrapConfig
from .content_store import ContentStore
from .image_tasks import ImageTaskService, ImageTaskStore
from .models import ContractError


@dataclass(frozen=True)
class ImageRegistration:
    runner: object


def validate_image_registration(registration):
    """HTTP의 경로·명령이 아닌 서버 소유 callable만 등록으로 인정한다."""
    if not isinstance(registration, ImageRegistration) or not callable(registration.runner):
        raise ContractError('image_registration_required')
    return registration


def build_image_task_service(*, config, content_store, registration=None, activate=False):
    if activate is not True:
        raise ContractError('image_activation_required')
    registration = validate_image_registration(registration)
    if (not isinstance(config, BootstrapConfig) or not isinstance(content_store, ContentStore)
            or content_store.root.resolve() != config.workspace_root.resolve()):
        raise ContractError('image_workspace_mismatch')
    # /var와 /private/var 별칭 확인 후 모든 하위 저장소는 ContentStore 표기를 공유한다.
    return ImageTaskService(ImageTaskStore(content_store.root), content_store,
                            runner=registration.runner, enabled=True)
