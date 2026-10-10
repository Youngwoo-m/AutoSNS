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


def compose(title, summary="", url="", tags=(), limit=500, notice=""):
    """제목 + 요약 한 줄 + 링크 + 해시태그(최대 5개) + 고정 문구. '#Shorts' 는 유튜브용이라 뺀다.

    summary 는 글 종류에 따라 문자열일 수도 문단 리스트일 수도 있다. 요약은 첫 줄만 쓴다.
    notice 는 쿠팡 파트너스 고지처럼 반드시 실려야 하는 문구 — 요약 첫 줄만 쓰는 규칙과
    글자 수 자르기에서 빠지고, 넘치면 요약을 줄여 자리를 만든다(2026-10-10 저녁 메뉴
    앱 글에서 요약 둘째 줄에 둔 고지가 잘려 답글로 따로 달았다)."""
    if isinstance(summary, (list, tuple)):
        summary = next((str(x) for x in summary if str(x).strip()), "")
    summary = str(summary or "").strip().split("\n")[0]
    title = re.sub(r"\s*#shorts\b", "", str(title or ""), flags=re.I).strip()
    picked = [t for t in (tags or []) if t.lower() != "shorts"][:5]
    notice = str(notice or "").strip()
    tail = [("▶ " + url) if url else "", " ".join("#" + t for t in picked), notice]
    text = "\n\n".join(x for x in [title, summary] + tail if x)
    if len(text) > limit and summary:          # 넘치면 요약부터 줄인다(고지·링크는 그대로)
        cut = max(0, len(summary) - (len(text) - limit) - 1)
        summary = summary[:cut].rstrip() + "…" if cut else ""
        text = "\n\n".join(x for x in [title, summary] + tail if x)
    if len(text) > limit and notice:           # 그래도 넘치면 고지는 남기고 앞부분을 자른다
        rest = "\n\n".join(x for x in [title, summary] + tail[:2] if x)
        return rest[:max(0, limit - len(notice) - 2)].rstrip() + "\n\n" + notice
    return text[:limit]


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
