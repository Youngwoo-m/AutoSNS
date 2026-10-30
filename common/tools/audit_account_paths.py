"""허용 코드만 정적으로 읽는 경로 보고서. collector/publisher를 import하지 않는다."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat

from common.operations.layout import absolute_root, build_path_migration
from common.operations.environment_manifest import build_environment_manifest


# glob/rglob/os.walk를 사용하지 않는다. config/token/profile/.venv는 포함하지 않는다.
CODE_ALLOWLIST = (
    'ax-console/app/server.py', 'ax-console/app/web_server.py',
    'ax-console/app/publishers.py', 'ax-console/app/read_model.py',
    'common/shared/paths.py', 'common/shared/axlock.py', 'common/shared/secret_config.py',
    'common/analytics/common.py', 'common/analytics/collect_youtube.py',
    'dept/naver-blog-auto/common.py', 'dept/naver-blog-auto/run_geoai.sh',
    'dept/naver-blog-auto/run_geoai_evening.sh', 'dept/naver-blog-auto/setup_geoai_schedule.sh',
    'dept/naver-blog-auto/geoai_daily.py', 'dept/naver-blog-auto/geoai_series.py',
    'dept/naver-blog-auto/geoai_auth_setup.py', 'dept/naver-blog-auto/geoai_shots_apply.py',
    'dept/naver-blog-auto/geoai_cards.py', 'dept/naver-blog-auto/geoai_script.py',
    'dept/naver-blog-auto/geoai_banner.py', 'dept/naver-blog-auto/geoai_backfill_media.py',
    'dept/naver-blog-auto/geoai_blogger.py', 'dept/naver-blog-auto/geoai_steps.py',
    'dept/naver-blog-auto/geoai_shots.py', 'dept/naver-blog-auto/geoai_assets.py',
    'dept/youtube-shorts-auto/common.py', 'dept/youtube-shorts-auto/geoai_video.py',
    'dept/youtube-shorts-auto/geoai_youtube_auth.py', 'dept/youtube-shorts-auto/geoai_short_post.py',
    'dept/youtube-shorts-auto/geoai_community_login.py', 'dept/youtube-shorts-auto/geoai_community.py',
    'personal/naver-blog-auto/common.py',
)
ALIAS_ALLOWLIST = ('GeoAI_NA', 'shared', 'analytics', 'assets', 'remotion-shorts', 'tools',
    'engineer-video-output', 'channels/naver-blog-auto', 'channels/youtube-shorts-auto',
    'channels/insta-cardnews', 'personal/youtube-shorts-auto', 'personal/shared', 'personal/remotion-shorts')
PATH_REFERENCES = ('dept/naver-blog-auto', 'dept/youtube-shorts-auto', 'channels/naver-blog-auto',
    'channels/youtube-shorts-auto', 'naver-blog-auto', 'youtube-shorts-auto', 'insta-cardnews',
    'GeoAI_NA', '../../shared', '.venv', 'BASE_DIR', 'POSTS_DIR', 'token.json', 'secrets.env.enc')
MAX_CODE_BYTES = 2 * 1024 * 1024


def _check_components(path, *, allow_missing=False):
    """모든 기존 상위 구성요소에서 링크를 거부한다. 내용은 읽지 않는다."""
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            if allow_missing:
                return
            raise
        if stat.S_ISLNK(mode):
            raise ValueError('경로 구성요소의 symlink 금지')


def _read_code(root, relative):
    """dir_fd와 O_NOFOLLOW로 부모와 최종 파일의 링크 경쟁도 거부한다."""
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    directory = root_fd
    file_fd = None
    try:
        for part in Path(relative).parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            if directory != root_fd:
                os.close(directory)
            directory = next_fd
        file_fd = os.open(Path(relative).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CODE_BYTES:
            raise ValueError('정규 코드 파일 크기 제한')
        chunks = []
        size = 0
        while chunk := os.read(file_fd, min(65536, MAX_CODE_BYTES + 1 - size)):
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_CODE_BYTES:
                raise ValueError('정규 코드 파일 크기 제한')
        return b''.join(chunks), info
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if directory != root_fd:
            os.close(directory)
        os.close(root_fd)


def _alias(root, name):
    """디렉터리를 열거하지 않고 링크 구성요소의 문자열만 해석한다."""
    original = root / name
    candidate = original
    seen = set()
    chain = []
    while True:
        if not candidate.is_relative_to(root):
            return dict(name=name, link_target=chain[0]['target'] if chain else None,
                        canonical_path=str(candidate), exists=None, status='external', chain=chain)
        found = False
        current = root
        for part in candidate.relative_to(root).parts:
            current /= part
            try:
                info = current.lstat()
            except (FileNotFoundError, NotADirectoryError):
                return dict(name=name, link_target=chain[0]['target'] if chain else None,
                            canonical_path=str(candidate), exists=False, status='dangling', chain=chain)
            if stat.S_ISLNK(info.st_mode):
                if str(current) in seen or len(chain) >= 40:
                    return dict(name=name, link_target=chain[0]['target'] if chain else None,
                                canonical_path=None, exists=None, status='cycle', chain=chain)
                seen.add(str(current))
                target = os.readlink(current)
                chain.append({'path': str(current), 'target': target})
                tail = candidate.relative_to(current)
                target_path = Path(target) if os.path.isabs(target) else current.parent / target
                candidate = Path(os.path.normpath(str(target_path / tail)))
                found = True
                break
        if not found:
            return dict(name=name, link_target=chain[0]['target'] if chain else None,
                        canonical_path=str(candidate), exists=True,
                        status='resolved' if chain else 'not_alias', chain=chain)


def _env_names(text, suffix):
    names = set()
    if suffix == '.py':
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                func = node.func
                is_getenv = (func.attr == 'getenv' and isinstance(func.value, ast.Name) and func.value.id == 'os')
                is_envget = (func.attr == 'get' and isinstance(func.value, ast.Attribute)
                             and func.value.attr == 'environ' and isinstance(func.value.value, ast.Name)
                             and func.value.value.id == 'os')
                if (is_getenv or is_envget) and node.args and isinstance(node.args[0], ast.Constant):
                    names.add(node.args[0].value)
            if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)
                    and isinstance(node.value.value, ast.Name) and node.value.value.id == 'os'
                    and node.value.attr == 'environ' and isinstance(node.slice, ast.Constant)):
                names.add(node.slice.value)
    else:
        names.update(re.findall(r'\$\{?([A-Za-z_][A-Za-z0-9_]*)', text))
    return sorted(n for n in names if isinstance(n, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', n))


def audit_inventory(root, *, code_root, workspace_root=None):
    root, code_root = absolute_root(root), absolute_root(code_root)
    _check_components(root)
    _check_components(code_root)
    if workspace_root is not None:
        _check_components(absolute_root(workspace_root), allow_missing=True)
    inventory = {'schema_version': 1, 'source_root': str(root), 'code_root': str(code_root),
                 'workspace_root': str(absolute_root(workspace_root)) if workspace_root else None,
                 'files': [], 'aliases': [], 'environments': [], 'unread': [],
                 'code_allowlist': list(CODE_ALLOWLIST), 'secret_contents_read': False,
                 'scope_complete': False}
    # R/W 불변식을 내용을 읽기 전에 검증한다.
    build_path_migration(inventory)
    texts = {}
    for relative in CODE_ALLOWLIST:
        try:
            data, info = _read_code(root, relative)
        except (OSError, ValueError):
            inventory['unread'].append({'path': relative, 'status': 'missing_or_unsafe'})
            continue
        text = data.decode('utf-8', errors='replace')
        texts[relative] = text
        refs = [{'reference': token, 'line': index} for index, line in enumerate(text.splitlines(), 1)
                for token in PATH_REFERENCES if token in line]
        inventory['files'].append({'path': relative, 'hash': hashlib.sha256(data).hexdigest(),
            'size': len(data), 'mtime_ns': info.st_mtime_ns, 'references': refs,
            'environment_ref': [relative], 'callers': [], 'alias': []})
        project = str(Path(relative).parent)
        # 디렉터리 이름만으로 개인/학과 소유권을 추정하지 않는다.
        # geoai_*는 조사 문서가 명시한 개인 코드이며 참조는 실행 검증이 아니다.
        personal_geoai = (relative.startswith(('dept/naver-blog-auto/geoai_', 'dept/youtube-shorts-auto/geoai_'))
                          or relative in ('dept/naver-blog-auto/run_geoai.sh', 'dept/naver-blog-auto/run_geoai_evening.sh'))
        inventory['environments'].append({'id': relative, 'entrypoint': str(root / relative),
            'interpreter': str(root / project / '.venv/bin/python') if project.startswith(('dept/', 'personal/')) else None,
            'cwd': str(root / project), 'profile_ref': 'profile:acct-personal' if personal_geoai else None,
            'credential_ref': 'credential:personal:legacy-unverified' if personal_geoai else None,
            'environment_variable_names': _env_names(text, Path(relative).suffix), 'callers': []})
    for row in inventory['files']:
        row['callers'] = sorted(name for name, text in texts.items()
                                if name != row['path'] and row['path'] in text)
    for name in ALIAS_ALLOWLIST:
        alias = _alias(root, name)
        alias['callers'] = sorted(path for path, text in texts.items() if name in text)
        alias['observation_confirmed'] = False
        alias['caller_inventory_complete'] = False
        inventory['aliases'].append(alias)
    inventory['environment_manifest'] = build_environment_manifest(inventory)
    return inventory


def _write_report(output, payload, forbidden_roots):
    output = absolute_root(output)
    for root in forbidden_roots:
        if output == root or output.is_relative_to(root):
            raise ValueError('보고서는 source/code/managed 저장 영역 밖에 지정')
    _check_components(output.parent)
    # 부모 링크를 거부한 뒤에도 dir_fd + O_NOFOLLOW로 최종 링크/덮어쓰기를 거부한다.
    directory = os.open(output.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in output.parent.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = next_fd
        fd = os.open(output.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
    finally:
        os.close(directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description='허용 코드 경로의 정적 이행 보고서만 생성')
    parser.add_argument('--root', required=True)
    parser.add_argument('--code-root', default=str(Path(__file__).absolute().parents[2]))
    parser.add_argument('--workspace-root')
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    roots = [absolute_root(args.root), absolute_root(args.code_root)]
    if args.workspace_root:
        roots.append(absolute_root(args.workspace_root))
    output = absolute_root(args.output)
    # 출력 경계 오류는 원본 코드 읽기 전에 거부한다.
    if any(output == root or output.is_relative_to(root) for root in roots):
        raise ValueError('보고서는 source/code/managed 저장 영역 밖에 지정')
    _check_components(output.parent)
    inventory = audit_inventory(args.root, code_root=args.code_root, workspace_root=args.workspace_root)
    report = build_path_migration(inventory)
    report['inventory'] = inventory
    _write_report(output, report, roots)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
