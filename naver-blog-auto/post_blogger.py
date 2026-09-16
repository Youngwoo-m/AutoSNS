"""같은 주간 브리핑을 Blogger(smusafety.blogspot.com)에도 올린다.

왜 블로그를 하나 더 쓰나: 네이버 블로그는 구글 검색 색인이 약하다. Blogger 는
구글 자산이라 구글·생성형 AI 검색에 잘 잡혀서, 같은 글로 노출 경로를 하나 더 얻는다.

인증: Blogger API v3 (scope=blogger). 유튜브와 같은 client_secret.json 을 쓰되
      토큰 파일은 따로 둔다(token_blogger.json). 최초 1회 인증은 사람이 해야 하므로
      blogger_auth_setup.py 를 사용자가 직접 실행한다.

중복 방지: 같은 제목의 글이 이미 있으면 올리지 않는다.
"""
import html
import os
import re
import urllib.parse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from common import BASE_DIR, load_config, log

SCOPES = ["https://www.googleapis.com/auth/blogger"]
TOKEN_PATH = os.path.join(BASE_DIR, "token_blogger.json")
CLIENT_SECRET = os.path.join(os.path.dirname(BASE_DIR), "youtube-shorts-auto",
                             "client_secret.json")


def _creds():
    if not os.path.exists(TOKEN_PATH):
        raise RuntimeError(
            "Blogger 토큰이 없습니다 — python blogger_auth_setup.py 로 최초 인증이 필요합니다.")
    c = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not c.valid and c.expired and c.refresh_token:
        c.refresh(Request())
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
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
    title = data.get("title", "재난안전 주간 브리핑")
    body = {
        "kind": "blogger#post",
        "title": title,
        "content": build_html(data, cfg),
        # 라벨(=태그)은 Blogger 검색·분류에 쓰인다. 지역 태그가 항상 포함되도록 앞에 둔다.
        # 라벨 상한 — 문서엔 20개라고 되어 있으나 실제로는 16개부터 400(invalid argument)이
        # 떨어진다(15개는 정상). 안전하게 15개로 자른다.
        "labels": list(dict.fromkeys(
            (cfg.get("local_tags") or []) + (data.get("tags") or [])))[:15],
    }
    if dry_run:
        log(f"[DRY] Blogger 발행 예정: {title[:50]} ({len(body['content'])}자 HTML, "
            f"라벨 {len(body['labels'])}개)")
        return {"status": "dry_run", "html_len": len(body["content"])}
    try:
        svc = build("blogger", "v3", credentials=_creds(), cache_discovery=False)
        if _already_posted(svc, blog_id, title):
            log("Blogger: 같은 제목의 글이 이미 있어 건너뜀")
            return {"status": "duplicate"}
        r = svc.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
        log(f"Blogger 발행 완료: {r.get('url','')}")
        return {"status": "published", "url": r.get("url", "")}
    except Exception as e:
        log(f"Blogger 발행 실패(네이버 발행은 정상): {type(e).__name__}: {str(e)[:150]}")
        return {"error": str(e)[:200]}


if __name__ == "__main__":
    import glob, json, sys
    files = sorted(glob.glob(os.path.join(BASE_DIR, "posts", "*.json")))
    if not files:
        raise SystemExit("posts/*.json 이 없습니다.")
    d = json.load(open(files[-1], encoding="utf-8"))
    print(json.dumps(publish(d, dry_run="--go" not in sys.argv), ensure_ascii=False))
