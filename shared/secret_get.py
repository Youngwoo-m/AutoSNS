"""암호화 저장소(secrets.env.enc) 값 하나를 꺼내고 넣는다 — 표준 라이브러리만 쓴다.

shared/secret_env.py 는 cryptography 가 있어야 열린다. 시스템 파이썬(/usr/bin/python3)으로
도는 스크립트(리포트 메일 발송 등)는 그게 없으니, 그때는 cryptography 가 있는
naver-blog-auto 의 venv 파이썬에게 대신 시킨다. 어느 파이썬에서든 get/put 이 같게 동작한다.

    from shared.secret_get import get
    key = get("DATA_GO_KR_KEY")          # 없으면 None
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PY = os.path.join(ROOT, "channels", "naver-blog-auto", ".venv", "bin", "python")


def _direct():
    try:
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)
        from shared import secret_env
        return secret_env
    except ImportError:                      # cryptography 없음 → venv 에게 맡긴다
        return None


def get(name, default=None):
    v = os.environ.get(name)
    if v:
        return v
    se = _direct()
    if se:
        return se.read().get(name, default)
    r = subprocess.run([VENV_PY, "-c", "import sys;from shared import secret_env as s;"
                        "v=s.read().get(sys.argv[1]);sys.stdout.write(v if v is not None else '')",
                        name], cwd=ROOT, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise SystemExit(f"암호화 저장소를 열지 못했습니다({name}): {r.stderr.strip()[-200:]}")
    return r.stdout or default


def put(name, value):
    """값을 저장한다(값은 표준입력으로 넘겨 명령줄·셸 기록에 남지 않게)."""
    se = _direct()
    if se:
        se.update({name: value})
        return
    subprocess.run([VENV_PY, "-c", "import sys;from shared import secret_env as s;"
                    "s.update({sys.argv[1]: sys.stdin.read()})", name],
                   cwd=ROOT, input=value, text=True, check=True, timeout=60)
