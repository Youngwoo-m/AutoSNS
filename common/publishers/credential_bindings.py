"""발행 자격의 논리적 계정·플랫폼·연결·세대 결속만 확인하는 순수 검증기.

워크스페이스의 실제 소유권과 비밀값은 여기서 판정하지 않는다. 실제 자격 resolver가
OwnedCredentialRef의 워크스페이스 증명을 검증해야 한다. backend·파일·네트워크 접근은 없다.
"""
from collections.abc import Mapping
from common.operations.credential_backend import validate_ref
from common.operations.models import Connection,ContractError
from common.operations.oauth_stage_models import OwnedCredentialRef


def _mismatch():
    raise ContractError('credential_owner_mismatch')


def validate_publication_credential_binding(registry,connection):
    """기존 고정 자격 별칭 또는 소유 증명 참조의 정확한 관리 키만 허용한다."""
    try:
        if not isinstance(connection,Connection) or connection.account_id not in ('personal','dept'):
            _mismatch()
        credentials=getattr(registry,'credentials',None)
        key=connection.credential_ref
        if (not isinstance(credentials,Mapping) or type(key) is not str or not key
                or type(connection.id) is not str or not connection.id
                or type(connection.platform) is not str or not connection.platform):
            _mismatch()
        entry=credentials.get(key)
        if (not isinstance(entry,Mapping) or entry.get('account_id')!=connection.account_id
                or entry.get('platform')!=connection.platform):
            _mismatch()
        # 운영 중인 기존 자격 별칭의 계약을 그대로 유지한다.
        if key==connection.id+'.credential':
            return True
        owned=entry.get('credential_ref')
        if type(owned) is not OwnedCredentialRef:
            _mismatch()
        # frozen 외피와 변경 가능한 논리 참조 모두 현재 상태를 다시 검증한다.
        owned.__post_init__()
        ref=owned.ref
        validate_ref(ref,connection.account_id)
        if (ref.namespace!='autosns.oauth' or ref.kind!='token'
                or ref.account_id!=connection.account_id or ref.platform!=connection.platform
                or ref.connection_id!=connection.id
                or key!=f'oauth:{ref.account_id}:{ref.platform}:{ref.connection_id}:{ref.generation}'):
            _mismatch()
        return True
    except ContractError:
        raise
    except Exception:
        raise ContractError('credential_owner_mismatch') from None


def build_managed_bridge_credential_catalog(registry,*,connection_ids=None):
    """BridgeHost용 심볼 목록. subset은 서버가 명시 선택한 등록 연결만 검증한다."""
    connections=getattr(registry,'connections',None)
    if not isinstance(connections,Mapping):
        _mismatch()
    if connection_ids is None:
        selected=tuple(connections)
    else:
        if (type(connection_ids) not in (list,tuple) or not connection_ids
                or any(type(identifier) is not str or not identifier or identifier not in connections for identifier in connection_ids)
                or len(set(connection_ids))!=len(connection_ids)):
            _mismatch()
        selected=tuple(connection_ids)
    result={}
    for identifier in selected:
        connection=connections[identifier]
        if not isinstance(connection,Connection) or identifier!=connection.id:
            _mismatch()
        if connection.credential_ref is None:
            continue
        validate_publication_credential_binding(registry,connection)
        reference=connection.credential_ref
        result[reference]=dict(credential_ref=reference,account_id=connection.account_id,platform=connection.platform)
    return result
