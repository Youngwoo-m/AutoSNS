"""고정 LocalCard 설정을 읽고 검증된 제작기를 명시 등록한다. 조립은 부수효과가 없다."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from .bootstrap_config import BootstrapConfig
from .image_startup import ImageRegistration
from .local_card_renderer import LocalCardRenderer
from .models import ContractError


@dataclass(frozen=True)
class InstalledImageSettings:
    enabled: bool
    template_hash: str
    font_sha256: str
    browser_executable: str | None


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError()
        result[key]=value
    return result


def load_installed_image_settings(path):
    path=Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ContractError('image_configuration_required')
    try:
        with path.open('rb') as stream:raw=stream.read(8193)
        if len(raw)>8192:raise ValueError()
        value=json.loads(raw,object_pairs_hook=_unique)
        if (not isinstance(value,dict) or set(value)!={'schema_version','template_id','enabled','template_hash','font_sha256','browser_executable'}
                or type(value['schema_version']) is not int or value['schema_version']!=1
                or value['template_id']!='LocalCard' or type(value['enabled']) is not bool
                or not all(type(value[key]) is str and re.fullmatch(r'[0-9a-f]{64}',value[key]) for key in ('template_hash','font_sha256'))):
            raise ValueError()
        browser=value['browser_executable']
        if browser is not None and (type(browser) is not str or '\x00' in browser or not Path(browser).is_absolute()):raise ValueError()
        return InstalledImageSettings(value['enabled'],value['template_hash'],value['font_sha256'],browser)
    except (ValueError,OSError,UnicodeError,KeyError):
        raise ContractError('invalid_image_configuration') from None


def build_installed_image_registration(*,config,settings,renderer_factory=LocalCardRenderer):
    if not isinstance(config,BootstrapConfig) or not isinstance(settings,InstalledImageSettings) or settings.enabled is not True:
        raise ContractError('image_configuration_required')
    value=settings.browser_executable
    if not isinstance(value,(str,Path)) or not str(value):raise ContractError('image_browser_required')
    browser=Path(value)
    if not browser.is_absolute() or browser.is_symlink() or not browser.is_file() or not os.access(browser,os.X_OK):
        raise ContractError('image_browser_required')
    renderer=renderer_factory(config.code_root,expected_template_hash=settings.template_hash,
        expected_font_hash=settings.font_sha256,browser_executable=browser)
    result=renderer.verify()
    if not isinstance(result,dict) or result.get('verified') is not True:
        raise ContractError('installed_image_unavailable')
    return ImageRegistration(renderer)
