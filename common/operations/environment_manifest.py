"""정적 인벤토리에서 실행 환경의 기호 참조만 복사한다."""
import re


def path_references(values):
    """caller는 값 객체가 아닌 저장소 상대 Python/shell 경로만 허용한다."""
    if not isinstance(values, (list, tuple)):
        return []
    return sorted({value for value in values if isinstance(value, str)
                   and re.fullmatch(r'(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:py|sh)', value)
                   and not any(part in ('.', '..') for part in value.split('/'))})


def reference_observation(values, *, unknown=False):
    """관측 0은 제한된 정적 범위의 0이며 전체 확인과 구별한다."""
    return {'status': 'partial' if values else ('unknown' if unknown else 'observed_zero_in_scope'),
            'scope': 'code_allowlist', 'complete': False}


def build_environment_manifest(inventory) -> dict:
    environments = []
    for entry in inventory.get('environments', []):
        # 입력의 임의 환경변수 값이나 credential 객체를 통째로 복사하지 않는다.
        row = {key: entry.get(key) if isinstance(entry.get(key), str) else None
               for key in ('id', 'interpreter', 'cwd', 'entrypoint', 'profile_ref', 'credential_ref')}
        row['environment_variable_names'] = sorted({name for name in entry.get('environment_variable_names', [])
            if isinstance(name, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name)})
        raw_callers = entry.get('callers')
        row['callers'] = path_references(raw_callers)
        observation = entry.get('callers_observation')
        unknown = (not isinstance(observation, dict)
                   or observation.get('status') == 'unknown'
                   or not isinstance(raw_callers, (list, tuple))
                   or len(row['callers']) != len(raw_callers))
        row['callers_observation'] = reference_observation(row['callers'], unknown=unknown)
        row['status'] = 'static_unverified'
        environments.append(row)
    return {'schema_version': 1, 'environments': environments,
            'environment_values_included': False, 'credentials_read': False,
            'execution_verified': False}
