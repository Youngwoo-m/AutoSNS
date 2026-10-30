"""운영 조회는 유지하고 별도 관리 저장소의 요약만 덧붙인다."""
from pathlib import Path
import sqlite3

from common.operations.content_store import ContentStore, StoreError
from common.operations.database import connect_database
from read_model import build_snapshot
from web_content import content_summary


def workspace_available(root):
    if root is None:
        return False
    try:
        connection = connect_database(Path(root))
        connection.close()
        return True
    except FileNotFoundError:
        return False
    except (OSError, sqlite3.Error) as exc:
        raise StoreError('storage_error') from exc


def compose_workspace_snapshot(snapshot, workspace_root, account='all', *, ledger=None):
    result = {**snapshot, 'read_only': True, 'workspace_writable': False,
              'contents': [{**item, 'source': 'legacy'} for item in snapshot.get('contents', [])],
              'warnings': list(snapshot.get('warnings', []))}
    try:
        available = workspace_available(workspace_root)
        if available:
            store = ContentStore(workspace_root)
            managed = store.list(account)
            result['contents'].extend(content_summary(item) for item in managed)
            result['workspace_writable'] = True
            if ledger is not None:
                try:
                    plans = ledger.list_deliveries(account)
                    known = {c['id'] for c in managed}
                    for plan in plans:
                        if plan['content_id'] not in known:
                            content = store.get(plan['content_id'])
                            if content is not None:
                                managed.append(content)
                                result['contents'].append(content_summary(content))
                                known.add(content['id'])
                    result['deliveries'] = list(result.get('deliveries', [])) + plans
                    titles = {c['id']: c.get('title', '') for c in managed}
                    result['schedule'] = list(result.get('schedule', [])) + [{**p, 'title': titles.get(p['content_id'], ''), 'channel': p['platform'], 'kind': 'local_plan'} for p in plans]
                    for item in result['contents']:
                        if item.get('source') == 'managed':
                            item['deliveries'] = [p for p in plans if p['content_id'] == item['id']]
                            item['target_accounts'] = list(dict.fromkeys(item['target_accounts'] + [p['destination_account_id'] for p in item['deliveries']]))
                            item['channels'] = list(dict.fromkeys(item['channels'] + [p['platform'] for p in item['deliveries']]))
                except StoreError:
                    result['warnings'].append('배포 계획 저장소의 명시적 초기화가 필요합니다.')
        else:
            result['warnings'].append('관리 저장소가 초기화되지 않아 조회 전용으로 표시합니다.')
    except StoreError:
        result['warnings'].append('관리 저장소를 읽지 못했습니다. 잠시 뒤 다시 확인하세요.')
    return result


def build_workspace_snapshot(source_root, workspace_root, account='all', **kwargs):
    return compose_workspace_snapshot(build_snapshot(source_root, account, **kwargs), workspace_root, account)
