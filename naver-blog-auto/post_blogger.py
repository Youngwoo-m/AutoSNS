"""같은 주간 브리핑을 Blogger(smusafety.blogspot.com)에도 올린다.

왜 블로그를 하나 더 쓰나: 네이버 블로그는 구글 검색 색인이 약하다. Blogger 는
구글 자산이라 구글·생성형 AI 검색에 잘 잡혀서, 같은 글로 노출 경로를 하나 더 얻는다.

인증: Blogger API v3 (scope=blogger). 유튜브와 같은 client_secret.json 을 쓰되
      토큰 파일은 따로 둔다(token_blogger.json). 최초 1회 인증은 사람이 해야 하므로
      blogger_auth_setup.py 를 사용자가 직접 실행한다.

중복 방지: 같은 제목의 글이 이미 있으면 올리지 않는다.
"""
import html
import json
import os
from datetime import datetime
import re
import urllib.parse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from common import BASE_DIR, load_config, log

SCOPES = ["https://www.googleapis.com/auth/blogger"]
# 어느 구글 계정으로 올릴지는 config.blogger.token_file 이 정한다.
# (학과 계정은 2026-09-20 부터 API 신규 게시가 403 으로 막혀, 게시가 되는 계정 토큰을 쓴다.
#  블로그 소유는 그대로 학과 블로그이고, 글쓴이 계정만 다르다.)
DEFAULT_TOKEN = "token_blogger.json"
CLIENT_SECRET = os.path.join(os.path.dirname(BASE_DIR), "youtube-shorts-auto",
                             "client_secret.json")


def _token_path(cfg=None):
    name = ((cfg or load_config()).get("blogger", {}) or {}).get("token_file", DEFAULT_TOKEN)
    return os.path.join(BASE_DIR, name)


def _creds(cfg=None):
    path = _token_path(cfg)
    if not os.path.exists(path):
        raise RuntimeError(
            f"Blogger 토큰이 없습니다({os.path.basename(path)}) — 해당 계정으로 1회 인증이 필요합니다.")
    c = Credentials.from_authorized_user_file(path, SCOPES)
    if not c.valid and c.expired and c.refresh_token:
        c.refresh(Request())
        with open(path, "w", encoding="utf-8") as f:
            f.write(c.to_json())
        log("Blogger 토큰 자동 갱신됨.")
    return c


def _esc(t):
    return html.escape((t or "").strip())


def _url(u):
    """URL 의 한글 등 비ASCII 를 퍼센트 인코딩한다.

    Blogger API 는 href 에 인코딩되지 않은 한글이 들어가면 400(invalid argument)을 낸다.
    (config.blog.cta 의 유튜브 검색 링크가 한글이라 첫 발행이 여기서 막혔다)"""
    return _esc(urllib.parse.quote((u or "").strip(), safe=":/?&=#%+@!$,;~*'()[]"))


def _para(text):
    """빈 줄로 나뉜 덩어리를 <p> 로. 줄바꿈은 <br>."""
    out = []
    for chunk in re.split(r"\n\s*\n", (text or "").strip()):
        if chunk.strip():
            out.append("<p>" + _esc(chunk).replace("\n", "<br>") + "</p>")
    return "\n".join(out)


def build_html(data, cfg=None):
    """네이버에 올린 것과 같은 구성의 HTML 본문(요약 → 인사 → 뉴스블록 → 안전수칙 → FAQ → 마무리 → CTA)."""
    cfg = cfg or load_config()
    parts = []
    if data.get("summary"):
        items = [l.lstrip("·-• ").strip() for l in data["summary"].splitlines() if l.strip()]
        parts.append("<h3>📌 3줄 요약</h3><ul>"
                     + "".join(f"<li>{_esc(i)}</li>" for i in items) + "</ul>")
    parts.append(_para(data.get("intro", "")))
    for blk in data.get("news_blocks", []):
        parts.append(f"<h3>{_esc(blk.get('heading',''))}</h3>")
        parts.append(_para(blk.get("paragraph", "")))
        src = blk.get("source", {}) or {}
        link = (src.get("real_link") or src.get("link") or "").strip()
        if link:
            parts.append(f'<p>📰 기사 원문: <a href="{_url(link)}" target="_blank" '
                         f'rel="noopener">{_esc(src.get("title",""))}</a></p>')
    if data.get("tips"):
        parts.append(_para(data["tips"]))
    if data.get("faq"):
        parts.append("<h3>❓ 자주 묻는 질문</h3>" + _para(data["faq"]))
    if data.get("outro"):
        parts.append(_para(data["outro"]))
    cta = (cfg.get("blog", {}) or {}).get("cta") or {}
    # Blogger 글에는 운영 중인 채널을 모두 링크로 건다(config.blogger.links).
    # 네이버 글의 CTA 링크(홈페이지·유튜브 검색)보다 우선한다 — 여기선 전 채널 안내가 목적.
    links = [l for l in ((cfg.get("blogger", {}) or {}).get("links")
                         or cta.get("links") or []) if (l.get("url") or "").strip()]
    if cta.get("text") or links:
        parts.append("<hr>")
        parts.append(_para(cta.get("text") or "세명대학교 재난안전학과의 채널에서 더 많은 소식을 만나보세요."))
        parts.append("<p><strong>📌 채널 바로가기</strong></p>")
        if links:
            parts.append("<ul>" + "".join(
                f'<li><a href="{_url(l["url"])}" target="_blank" rel="noopener">'
                f'{_esc(l.get("label", l["url"]))}</a></li>' for l in links) + "</ul>")
    return "\n".join(p for p in parts if p)


POST_STATE = os.path.join(BASE_DIR, "blogger_post_state.json")


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _posted_today():
    """오늘 이 블로그에 API 로 올린 글 수."""
    try:
        with open(POST_STATE, encoding="utf-8") as f:
            return int(json.load(f).get(_today(), 0))
    except Exception:
        return 0


def _count_post():
    """발행 기록 +1. 오늘 것만 남기고 옛 기록은 버린다."""
    try:
        with open(POST_STATE, "w", encoding="utf-8") as f:
            json.dump({_today(): _posted_today() + 1}, f, ensure_ascii=False)
    except Exception as e:
        log(f"발행 횟수 기록 실패: {type(e).__name__}")


def _already_posted(svc, blog_id, title):
    """같은 제목의 글이 이미 있으면 True(중복 발행 방지)."""
    try:
        r = svc.posts().list(blogId=blog_id, maxResults=20,
                             fetchBodies=False, fields="items(title)").execute()
        return any((i.get("title") or "").strip() == title.strip()
                   for i in r.get("items", []))
    except Exception as e:
        log(f"Blogger 중복 확인 실패({type(e).__name__}) — 발행은 진행합니다")
        return False


def publish(data, dry_run=False, cfg=None):
    """주간 브리핑을 Blogger 에 올린다. 실패해도 예외를 올리지 않는다."""
    cfg = cfg or load_config()
    bcfg = cfg.get("blogger", {}) or {}
    if not bcfg.get("enabled", False):
        return {"status": "disabled"}
    blog_id = str(bcfg.get("blog_id", "")).strip()
    if not blog_id:
        log("Blogger: blog_id 가 없어 건너뜀")
        return {"status": "no_blog_id"}
    # 하루 상한 — 짧은 시간에 여러 편을 올리다 계정이 API 게시 제한을 먹은 적이 있다
    # (2026-09-16, 학과 계정). 기본 1편으로 묶는다.
    limit = int(bcfg.get("daily_limit", 1))
    if not dry_run and _posted_today() >= limit:
        log(f"Blogger: 오늘 이미 {limit}편 올렸습니다 — 건너뜁니다")
        return {"status": "daily_limit"}
    # 대표 라벨: 에디션별 blogger_category(없으면 blogger.category)
    max_labels = int((cfg.get("blogger", {}) or {}).get("max_labels", 6))
    cat = (cfg.get("blogger_category")
           or (cfg.get("blogger", {}) or {}).get("category", "재난안전뉴스"))
    title = data.get("title", "재난안전 브리핑")
    body = {
        "kind": "blogger#post",
        "title": title,
        "content": build_html(data, cfg),
        # 라벨(=태그)은 Blogger 검색·분류에 쓰인다. 지역 태그가 항상 포함되도록 앞에 둔다.
        # 라벨 = Blogger 의 카테고리 역할. 대표 라벨 + 소수의 주제어만 넣는다.
        # 15개씩 달면 사이드바가 카테고리 메뉴가 아니라 태그 구름이 되어 쓸모가 없다.
        # (상한은 문서상 20개지만 실제로는 16개부터 400 이 떨어진다)
        "labels": list(dict.fromkeys([cat] + (data.get("tags") or [])))[:max_labels],
    }
    # 글 위치(제천) — 지역 검색·지역 관련성에 쓰이도록 모든 글에 같은 위치를 붙인다.
    loc = bcfg.get("location") or {}
    if loc.get("name"):
        body["location"] = {k: v for k, v in loc.items() if v is not None}
    if dry_run:
        log(f"[DRY] Blogger 발행 예정: {title[:50]} ({len(body['content'])}자 HTML, "
            f"라벨 {len(body['labels'])}개)")
        return {"status": "dry_run", "html_len": len(body["content"])}
    try:
        svc = build("blogger", "v3", credentials=_creds(cfg), cache_discovery=False)
        if _already_posted(svc, blog_id, title):
            log("Blogger: 같은 제목의 글이 이미 있어 건너뜀")
            return {"status": "duplicate"}
        r = svc.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
        _count_post()
        log(f"Blogger 발행 완료: {r.get('url','')}")
        return {"status": "published", "url": r.get("url", "")}
    except Exception as e:
        log(f"Blogger 발행 실패(네이버 발행은 정상): {type(e).__name__}: {str(e)[:150]}")
        return {"error": str(e)[:200]}


if __name__ == "__main__":
    import glob, sys
    files = sorted(glob.glob(os.path.join(BASE_DIR, "posts", "*.json")))
    if not files:
        raise SystemExit("posts/*.json 이 없습니다.")
    d = json.load(open(files[-1], encoding="utf-8"))
    print(json.dumps(publish(d, dry_run="--go" not in sys.argv), ensure_ascii=False))
