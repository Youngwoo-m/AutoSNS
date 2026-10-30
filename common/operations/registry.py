"""파일을 변경하거나 기호 참조를 해석하지 않는 등록부 판독기."""
import json
from pathlib import Path
from dataclasses import fields
from .models import Connection, Registry, ContractError


def _records(value, name):
    if isinstance(value, dict):
        if not all(isinstance(key, str) and key and isinstance(row, dict) for key, row in value.items()):
            raise ContractError('invalid_registry', name)
        if any('id' in row and row['id'] != key for key, row in value.items()):
            raise ContractError('invalid_registry', name)
        return {key: dict(row, id=key) for key, row in value.items()}
    if isinstance(value, list):
        result = {}
        for row in value:
            if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id'] or row['id'] in result:
                raise ContractError('invalid_registry', name)
            result[row['id']] = row
        return result
    raise ContractError('invalid_registry', name)


def load_registry(path: Path) -> Registry:
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
        if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data['schema_version'] != 1 or not isinstance(data.get('revision'), str) or not data['revision']:
            raise ContractError('invalid_registry')
        tables = {name: _records(data.get(name, {}), name) for name in
                  ('accounts', 'credentials', 'profiles', 'connections', 'jobs', 'policies', 'crossposts')}
        rule_path = Path(path).parent / 'crossposts.json'
        if rule_path.exists():
            external = json.loads(rule_path.read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
            if not isinstance(external, dict) or type(external.get('schema_version')) is not int or external['schema_version'] != 1:
                raise ContractError('invalid_registry')
            rules = _records(external.get('rules'), 'rules')
            if tables['crossposts'].keys() & rules.keys():
                raise ContractError('invalid_registry', '중복 교차 규칙')
            tables['crossposts'] = dict(tables['crossposts'], **rules)
        accounts = tables['accounts']
        for group in ('credentials', 'profiles'):
            for row in tables[group].values():
                if row.get('account_id') not in accounts:
                    raise ContractError('unknown_account')
        connections = {}
        allowed = {field.name for field in fields(Connection)}
        for key, row in tables['connections'].items():
            owner = row.get('account_id')
            if owner not in ('dept', 'personal') or owner not in accounts:
                raise ContractError('unknown_account')
            if not isinstance(row.get('platform'), str) or not row['platform']:
                raise ContractError('invalid_registry')
            if row.get('target_id') is not None and (not isinstance(row['target_id'], str) or not row['target_id']):
                raise ContractError('invalid_registry')
            for field, group, code in [('credential_ref', 'credentials', 'credential_owner_mismatch'), ('profile_ref', 'profiles', 'profile_owner_mismatch')]:
                reference = row.get(field)
                if reference is not None:
                    if reference not in tables[group]:
                        raise ContractError('invalid_registry')
                    if tables[group][reference]['account_id'] != owner:
                        raise ContractError(code)
            for flag in ('enabled', 'planning_enabled'):
                if flag in row and type(row[flag]) is not bool:
                    raise ContractError('invalid_registry')
            if not isinstance(row.get('capabilities', []), (list, tuple)):
                raise ContractError('invalid_registry')
            connections[key] = Connection(**{k: v for k, v in dict(row, id=key).items() if k in allowed})
        tables['connections'] = connections
        for row in tables['jobs'].values():
            if row.get('execution_owner') not in ('managed', 'legacy'):
                raise ContractError('invalid_registry')
            if row.get('kind') not in (None, 'publication', 'production'):
                raise ContractError('invalid_registry')
            # 콘텐츠별 binding job은 서버가 저장 binding을 검증한 뒤에만 추가한다.
            if 'base_job_id' in row or 'binding_id' in row:
                raise ContractError('invalid_registry')
            if row.get('schedule_owner') not in ('launchd', 'console'):
                if not (row.get('schedule_owner') is None and row.get('execution_owner') == 'legacy' and row.get('planning_enabled') is False):
                    raise ContractError('invalid_registry')
            if row.get('owner_account_id') not in accounts:
                raise ContractError('unknown_account')
            if row.get('policy_revision') not in tables['policies']:
                raise ContractError('invalid_registry')
            for flag in ('enabled', 'planning_enabled'):
                if flag in row and type(row[flag]) is not bool:
                    raise ContractError('invalid_registry')
        for rule in tables['crossposts'].values():
            source = connections.get(rule.get('source_connection_id'))
            destination = connections.get(rule.get('destination_connection_id'))
            if source is None or destination is None:
                raise ContractError('invalid_registry')
            if rule.get('owner_account_id') != source.account_id:
                raise ContractError('owner_mismatch')
        return Registry(revision=data['revision'], schema_version=1, **tables)
    except ContractError:
        raise
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise ContractError('invalid_registry') from error


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError('invalid_registry', '중복 키')
        result[key] = value
    return result
