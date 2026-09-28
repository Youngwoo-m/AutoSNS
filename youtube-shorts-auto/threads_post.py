"""스레드(Threads) 텍스트 크로스포스트 헬퍼.

스레드 발행은 insta-cardnews 쪽 로그인 세션으로만 되므로 그 venv 의 threads_cli.py
를 subprocess 로 부른다. 부가 채널이라 예외를 올리지 않고 상태 문자열만 돌려준다.
"""
import json
import os
import re
import subprocess

from common import BASE_DIR, log

IG_DIR = os.path.join(os.path.dirname(BASE_DIR), "insta-cardnews")
IG_PY = os.path.join(IG_DIR, ".venv", "bin", "python")
TIMEOUT = 300


def compose(title, summary="", url="", tags=(), limit=500):
    """제목 + 요약 한 줄 + 링크 + 해시태그(최대 5개). '#Shorts' 는 유튜브용이라 뺀다."""
    title = re.sub(r"\s*#shorts\b", "", title or "", flags=re.I).strip()
    picked = [t for t in (tags or []) if t.lower() != "shorts"][:5]
    parts = [title, (summary or "").strip(), ("▶ " + url) if url else "",
             " ".join("#" + t for t in picked)]
    return "\n\n".join(x for x in parts if x)[:limit]


def crosspost(text):
    cli = os.path.join(IG_DIR, "threads_cli.py")
    if not (os.path.exists(IG_PY) and os.path.exists(cli)):
        return "skipped: threads_cli 없음"
    if not (text or "").strip():
        return "skipped: 본문 없음"
    env = {k: v for k, v in os.environ.items() if k != "SMUDS_EDITION"}
    try:
        p = subprocess.run([IG_PY, "threads_cli.py"], cwd=IG_DIR,
                           input=json.dumps({"text": text}), text=True,
                           capture_output=True, timeout=TIMEOUT, env=env)
    except subprocess.TimeoutExpired:
        return "error: timeout"
    out = [ln for ln in (p.stdout or "").strip().splitlines() if ln.startswith("{")]
    try:
        status = json.loads(out[-1]).get("status", "unknown") if out else "no_output"
    except Exception:
        status = f"unparsed(rc={p.returncode})"
    log(f"쓰레드: {status}"
        + (f" (stderr: {(p.stderr or '')[-200:]})" if status not in ("published", "dry_run") else ""))
    return status
