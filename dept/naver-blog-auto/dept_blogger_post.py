"""완성된 HTML 원고 한 편을 학과 Blogger(smuds2026.blogspot.com)에 올린다 — 클로드 자동 작업용(dept-crosspost).

blogger_post.py(개인 Blogger)와 같은 사용법·같은 결과 JSON. 블로그 id·위치는 config.json 의 blogger 절(post_blogger.py 와 같은 곳)을 쓴다.
토큰: 기본은 config.blogger.token_file(post_blogger.py 가 실제로 학과 블로그에 올릴 때 쓰는 것).
  2026-09-20 부터 학과 계정 토큰(BLOGGER_TOKEN_DEPT)은 API 신규 게시가 403 이라 config 가 다른 계정 토큰을 가리킨다.
  --token dept 를 주면 학과 계정 토큰(token_blogger.json → BLOGGER_TOKEN_DEPT)을 강제로 쓴다.
하루 발행 한도는 post_blogger.py 의 주간 브리핑과 따로 센다(crosspost_state.json, 기본 3편 — config.blogger.crosspost_daily_limit).
quota:blogger-dept 잠금(shared/axlock.py)을 잡고 올린다. 그림·링크는 공개 https 주소만.

    ./.venv/bin/python dept_blogger_post.py --html 요약.html --title "제목" --labels "토목시공기술사" --dry
    ./.venv/bin/python dept_blogger_post.py --html 요약.html --title "제목" --labels "토목시공기술사" --go --job dept-crosspost

결과는 마지막 줄에 JSON 한 줄: {"status": "published"|"dry"|"duplicate"|"error", "url": …, "message": …}
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
sys.path.insert(0, os.path.dirname(os.path.dirname(BASE)))

STATE = os.path.join(BASE, "crosspost_state.json")
DEPT_TOKEN = "token_blogger.json"          # blogger_token.NAMES → BLOGGER_TOKEN_DEPT


def out(status, url="", message=""):
    print(json.dumps({"status": status, "url": url, "message": message}, ensure_ascii=False))
    return 0 if status in ("published", "dry", "duplicate") else 1


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _count(add=0):
    try:
        with open(STATE, encoding="utf-8") as f:
            n = int(json.load(f).get(_today(), 0))
    except Exception:
        n = 0
    if add:
        with open(STATE, "w", encoding="utf-8") as f:
            json.dump({_today(): n + add}, f, ensure_ascii=False)
    return n + add


def managed_state(connection="dept.blogger"):
    """관리 OAuth(dept-oauth-service 브랜치) 준비 상태 — 읽기만. 없으면 not_installed.
    발행 범위가 열리기(publication_verified) 전까지 실제 발행은 옛 토큰으로 한다."""
    try:
        from common.publishers.managed_assembly import managed_readiness
        from common.operations.bootstrap_config import default_bootstrap_config
        from common.operations.managed_connections import ManagedConnectionStore
        snap = ManagedConnectionStore(default_bootstrap_config().workspace_root).snapshot()
        r = managed_readiness(snap, (connection,))[connection]
        return f"{r['read']}/{r['publication']}"
    except ImportError:
        return "not_installed"
    except Exception as e:  # noqa: BLE001
        return f"unavailable:{type(e).__name__}"


def _dept_cfg():
    import json as _j
    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
        return (_j.load(f).get("blogger") or {})


def main():
    ap = argparse.ArgumentParser(description="학과 Blogger(smuds2026) 교차 발행기")
    ap.add_argument("--html", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--labels", default="", help="쉼표로 구분. 첫 라벨이 대표 카테고리")
    ap.add_argument("--token", default="config", choices=["config", "dept"])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry", action="store_true")
    g.add_argument("--go", action="store_true")
    ap.add_argument("--job", default="claude")
    a = ap.parse_args()
    from shared.owner_fence import require_legacy_cli
    require_legacy_cli(("dept", "blogger", "dept-blogger-post-cli"))
    if os.environ.get("AX_DRY") == "1":
        a.go = False
    try:
        body_html = open(a.html, encoding="utf-8").read()
    except OSError as e:
        return out("error", message=f"원고를 읽지 못했습니다: {e}")
    if re.search(r'(src|href)="(?!https?://)[^"#]', body_html):
        return out("error", message="본문에 http(s) 가 아닌 그림·링크 주소가 있습니다 — 공개 https 주소로 바꾸세요")
    if len(a.title) > 150 or not a.title.strip():
        return out("error", message="제목이 비었거나 너무 깁니다")
    bcfg = _dept_cfg()
    blog_id = str(bcfg.get("blog_id", "")).strip()
    if not blog_id:
        return out("error", message="config.json blogger.blog_id 가 없습니다")
    if a.go:
        # 사람이 쓴 것처럼 문체만 한 번 더 다듬는다(2026-11-08 사용자 지정 — shared/humanize.py).
        # 문단 안쪽 글만 고치고 숫자·주소·인용·태그가 달라진 문단은 원문으로 둔다. 실패해도 원고 그대로 올린다.
        try:
            import json as _j
            from shared.humanize import polish_html
            with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
                _cfg = _j.load(f)
            body_html = polish_html(body_html, cfg=_cfg, log=lambda m: print(m, file=sys.stderr))
        except Exception as e:  # noqa: BLE001
            print(f"윤문 건너뜀: {type(e).__name__}", file=sys.stderr)
    labels = list(dict.fromkeys(x.strip() for x in a.labels.split(",") if x.strip()))[:int(bcfg.get("max_labels", 1)) or 1]
    post = {"kind": "blogger#post", "title": a.title.strip(), "content": body_html, "labels": labels}
    loc = bcfg.get("location") or {}
    if loc.get("name"):
        post["location"] = {k: v for k, v in loc.items() if v is not None}
    limit = int(bcfg.get("crosspost_daily_limit", 3))
    token_file = DEPT_TOKEN if a.token == "dept" else bcfg.get("token_file", DEPT_TOKEN)

    if not a.go:
        return out("dry", message=f"blog {blog_id} · 라벨: {', '.join(labels) or '없음'} · {len(body_html)}자 · "
                                  f"토큰 {token_file} · 오늘 {_count()}/{limit}편 · 관리 OAuth {managed_state()}")
    from shared.axlock import Timeout, hold, stopped
    if stopped():
        return out("error", message="비상 정지 중이라 발행하지 않았습니다")
    if _count() >= limit:
        return out("error", message=f"오늘 학과 Blogger 교차 발행 한도 {limit}편을 채웠습니다 — 내일 다시")

    def go():
        import blogger_token
        from googleapiclient.discovery import build
        from post_blogger import SCOPES, _already_posted
        creds = blogger_token.load(os.path.join(BASE, token_file), SCOPES, "학과 Blogger")
        svc = build("blogger", "v3", credentials=creds, cache_discovery=False)
        if _already_posted(svc, blog_id, post["title"]):
            return out("duplicate", message="같은 제목 글이 이미 학과 블로그에 있습니다")
        r = svc.posts().insert(blogId=blog_id, body=post, isDraft=False).execute()
        _count(1)
        return out("published", r.get("url", ""))
    try:
        with hold(["quota:blogger-dept"], job=f"{a.job}:dept_blogger_post", wait=2400):
            return go()
    except Timeout:
        return out("error", message="40분 기다려도 quota:blogger-dept 잠금이 비지 않았습니다")
    except Exception as e:  # noqa: BLE001
        return out("error", message=f"{type(e).__name__}: {str(e)[:300]}")


if __name__ == "__main__":
    sys.exit(main())
