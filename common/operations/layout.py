"""파일 접근이나 이동 없이 계산하는 계정 경로와 이행 제안."""
from pathlib import Path


def absolute_root(root):
    """cwd와 링크 해석에 의존하지 않는 명시 절대경로만 허용한다."""
    if not isinstance(root, (str, Path)) or not str(root):
        raise ValueError('명시 절대경로 필요')
    path = Path(root)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('상대경로·상위 탈출 금지')
    return path


def resolve_layout(account_id, root) -> dict:
    if account_id not in ('dept', 'personal'):
        raise ValueError('알 수 없는 계정')
    root = absolute_root(root)
    base = root / account_id
    return {'schema_version': 1, 'account_id': account_id, 'root': str(root),
            **{key + '_root': str(base / folder) for key, folder in
               (('config', 'config'), ('content', 'content'), ('media', 'media'), ('history', 'history'))},
            'proposed_paths': {'blog_auto': str(base / 'blog-auto'),
                               'shorts_auto': str(base / 'shorts-auto')},
            'proposal_only': True}


def can_remove_alias(alias, callers) -> bool:
    """정적 검색의 caller 0만으로는 제거를 승인하지 않는다."""
    return (isinstance(alias, dict) and isinstance(callers, (list, tuple)) and len(callers) == 0
            and alias.get('status') == 'resolved'
            and alias.get('observation_confirmed') is True
            and alias.get('caller_inventory_complete') is True)


def build_path_migration(baseline) -> dict:
    source = absolute_root(baseline['source_root'])
    code = absolute_root(baseline['code_root'])
    workspace = baseline.get('workspace_root')
    if workspace is not None:
        workspace = absolute_root(workspace)
        if (workspace == source or workspace.is_relative_to(source) or source.is_relative_to(workspace)
                or workspace == code or workspace.is_relative_to(code) or code.is_relative_to(workspace)):
            raise ValueError('R/W/code_root 저장 영역 겹침 금지')
    blockers = ['정적 보고서만 생성: 물리 이행 실행은 이번 범위에 없음',
                'T10 실행 규칙 단일화의 승인·검증 근거 미확인',
                'T11 adapter 계약의 승인·검증 근거 미확인',
                'T12 제작 계약의 승인·검증 근거 미확인',
                '전체 wrapper/launchd/지시문/console/자동화 caller 관측 미완료',
                '환경별 interpreter/cwd/자격증명·프로필 참조 관측 미완료']
    if workspace is None:
        blockers.append('명시 관리 저장 루트 W 미지정')
    proposals = [
        {'source': str(source / 'dept/naver-blog-auto'),
         'destination': str(source / 'personal/blog-auto'),
         'scope': '개인 geoai 코드만 제안; 폴더 전체 이동 아님'},
        {'source': str(source / 'dept/youtube-shorts-auto'),
         'destination': str(source / 'personal/shorts-auto'),
         'scope': '개인 geoai 코드만 제안; 폴더 전체 이동 아님'}]
    rows = []
    for entry in baseline.get('files', []):
        relative = entry['path']
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('원본 상대경로 탈출 금지')
        destination = None
        if relative.startswith('dept/naver-blog-auto/geoai_'):
            destination = str(source / 'personal/blog-auto' / path.name)
        elif relative.startswith('dept/youtube-shorts-auto/geoai_'):
            destination = str(source / 'personal/shorts-auto' / path.name)
        rows.append({'source': str(source / path), 'original_path': relative,
                     'original_id': entry.get('original_id'), 'destination': destination,
                     'callers': entry.get('callers', []), 'hash': entry.get('hash'),
                     'alias': entry.get('alias', []), 'environment_ref': entry.get('environment_ref', []),
                     'blockers': list(blockers)})
    return {'schema_version': 1, 'source_root': str(source), 'code_root': str(code),
            'workspace_root': str(workspace) if workspace else None,
            'physical_migration_ready': False, 'proposal_only': True,
            'preserve_original_ids': True, 'preserve_original_paths': True,
            'identity_policy': '기존 ID·원래 상대경로를 보존하며 경로 변경으로 재발급하지 않음',
            'ledger_policy': 'shared', 'ledger_path': str(workspace / 'operations.sqlite3') if workspace else None,
            'excluded_from_moves': ['운영 원장', '비밀값 저장소', '.venv', '로그인 프로필', '공용 코드·자산'],
            'proposals': proposals, 'entries': rows, 'aliases': baseline.get('aliases', []),
            'environment_manifest': baseline.get('environment_manifest', {}),
            'incomplete_callers': ['wrapper', 'launchd', '지시문', 'console', '자동화'],
            'incomplete_environments': [e.get('id') for e in baseline.get('environments', [])],
            'blockers': blockers, 'inventory_scope': '명시 코드 allowlist만; 전체 운영 인벤토리 아님'}
