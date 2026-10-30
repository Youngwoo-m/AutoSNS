"""정적 인벤토리에서 실행 환경의 기호 참조만 복사한다."""
import re


def build_environment_manifest(inventory) -> dict:
    environments = []
    for entry in inventory.get('environments', []):
        # 입력의 임의 환경변수 값이나 credential 객체를 통째로 복사하지 않는다.
        row = {key: entry.get(key) if isinstance(entry.get(key), str) else None
               for key in ('id', 'interpreter', 'cwd', 'entrypoint', 'profile_ref', 'credential_ref')}
        row['environment_variable_names'] = sorted({name for name in entry.get('environment_variable_names', [])
            if isinstance(name, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name)})
        row['callers'] = list(entry.get('callers', []))
        row['status'] = 'static_unverified'
        environments.append(row)
    return {'schema_version': 1, 'environments': environments,
            'environment_values_included': False, 'credentials_read': False,
            'execution_verified': False}
