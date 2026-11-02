"""고정 설정·수동 이미지 확인으로 로컬 Remotion 등록을 조립한다. 기본 비활성."""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from .content_store import ContentStore
from .media_plans import MediaPlanStore
from .models import ContractError
from .installed_remotion import InstalledRemotion
from .production_media import probe_media
from .reuse_approvals import ReuseApprovalStore,ReuseApprovalService,ManagedReuseAuthorizer


@dataclass(frozen=True)
class InstalledVideoSettings:
    enabled: bool
    template_hash: str
    font_sha256: str


def _unique_settings(pairs):
    value={}
    for key,item in pairs:
        if key in value:
            raise ValueError('duplicate setting')
        value[key]=item
    return value


def load_installed_video_settings(path):
    path=Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ContractError('video_configuration_required')
    try:
        with path.open('rb') as stream:raw=stream.read(8193)
        if len(raw)>8192:raise ValueError()
        value=json.loads(raw,object_pairs_hook=_unique_settings)
        if (not isinstance(value,dict) or set(value)!={'schema_version','template_id','enabled','template_hash','font_sha256'}
            or type(value['schema_version']) is not int or value['schema_version']!=1 or value['template_id']!='SurveyShort'
            or type(value['enabled']) is not bool or not all(isinstance(value[k],str) and re.fullmatch(r'[0-9a-f]{64}',value[k]) for k in ('template_hash','font_sha256'))):
            raise ValueError()
        return InstalledVideoSettings(value['enabled'],value['template_hash'],value['font_sha256'])
    except (ValueError,OSError,UnicodeError,KeyError):
        raise ContractError('invalid_video_configuration') from None


def pending_manual_video_review(**kwargs):
    """미실시 검사를 완료로 표시하지 않고 사람의 명시적 영상 확인을 기다린다."""
    return {}


def build_installed_video_registration(*,config,settings,installed_factory=InstalledRemotion):
    if not isinstance(settings,InstalledVideoSettings) or settings.enabled is not True:
        raise ContractError('video_configuration_required')
    installed=installed_factory(config.code_root,expected_template_hash=settings.template_hash,
        expected_font_hash=settings.font_sha256)
    result=installed.verify()
    if not isinstance(result,dict) or result.get('verified') is not True:
        raise ContractError('installed_video_unavailable')
    content=ContentStore(config.workspace_root)
    service=ReuseApprovalService(ReuseApprovalStore(content.root),content,MediaPlanStore(content.root,content))
    return installed.create_registration(reuse_authorization=ManagedReuseAuthorizer(service),
        inspect_video=pending_manual_video_review,probe=probe_media,defer_video_review=True)
