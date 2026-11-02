"""읽기 전용 성과 수집 기동 설정. 로딩은 자격·네트워크·저장소에 접근하지 않는다."""
from dataclasses import dataclass
import json
from pathlib import Path
from .models import ContractError

_CONNECTION_IDS=('personal.youtube','dept.youtube')


@dataclass(frozen=True)
class MetricsCollectionSettings:
    enabled: bool
    connection_ids: tuple[str,...]


def _unique(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError()
        result[key]=value
    return result


def load_metrics_collection_settings(path):
    path=Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ContractError('metrics_configuration_required')
    try:
        with path.open('rb') as stream:raw=stream.read(8193)
        if len(raw)>8192:raise ValueError()
        value=json.loads(raw,object_pairs_hook=_unique)
        if (type(value) is not dict or set(value)!={'schema_version','enabled','connection_ids'}
                or type(value['schema_version']) is not int or value['schema_version']!=1
                or type(value['enabled']) is not bool):
            raise ValueError()
        ids=value['connection_ids']
        if (type(ids) is not list or len(ids)>2 or any(type(item) is not str or item not in _CONNECTION_IDS for item in ids)
                or len(set(ids))!=len(ids) or (value['enabled'] and not ids)):
            raise ValueError()
        return MetricsCollectionSettings(value['enabled'],tuple(ids))
    except (ValueError,OSError,UnicodeError,KeyError):
        raise ContractError('invalid_metrics_configuration') from None
