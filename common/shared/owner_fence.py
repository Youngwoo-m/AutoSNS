"""legacy common.py와 관리 common namespace를 섞지 않는 격리된 owner 조회."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def route_legacy_action(action_key, *, services=None):
    # legacy 모듈은 프로젝트 common.py를 먼저 import한다. 별도 -I 조회 프로세스는
    # 그 모듈/환경 경로를 물려받지 않으며 config 외에는 아무것도 실행하지 않는다.
    if services is not None:
        raise ValueError('legacy CLI에는 서버 서비스 객체를 전달할 수 없습니다')
    done = subprocess.run([sys.executable, '-I', str(ROOT / 'common/operations/legacy_fences.py'),
                           *action_key], capture_output=True, text=True, timeout=30)
    try:
        result = json.loads(done.stdout.strip())
    except (ValueError, TypeError):
        return {'route': 'blocked', 'status': 'error', 'detail': 'owner_fence_unavailable'}
    if done.returncode or result.get('route') != 'legacy':
        return {'route': 'blocked', 'status': 'error', 'detail': result.get('error', 'legacy_not_allowed')}
    return result


def require_legacy_cli(action_key):
    result = route_legacy_action(action_key)
    if result.get('route') != 'legacy':
        print(json.dumps({'status': 'error', 'detail': result.get('detail', 'legacy_not_allowed')}, ensure_ascii=False))
        raise SystemExit(1)
    return result
