"""GeoAI 전용 블로그(geoaina.blogspot.com)에 글을 올리는 발행 계층.

왜 post_blogger.py 와 따로 두나: 이 블로그는 학과 블로그(smusafety)와 **소유 구글
계정이 다르다**. 2026-09-16 기존 토큰(ds2eye)으로 관리자 조회를 하면 403 이 난다.
그래서 토큰 파일을 따로 둔다(token_blogger_geoai.json ← geoai_auth_setup.py 로 1회 인증).
나머지(HTML 이스케이프·URL 인코딩·라벨 상한)는 post_blogger 에서 겪은 제약을 그대로 따른다.
"""
import json
import os
from datetime import datetime, timezone

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from common import BASE_DIR, POSTS_DIR, load_config, log
from post_blogger import SCOPES, _esc, _url

TOKEN_PATH = os.path.join(BASE_DIR, "token_blogger_geoai.json")

# 라벨 상한 — 문서엔 20개지만 실제로는 16개부터 400(invalid argument)이 떨어진다.
LABEL_CAP = 15
# 라벨은 개수뿐 아니라 '쉼표로 이은 전체 길이'에도 한계가 있다. 넘기면 Blogger 가
# 400 invalid argument 를 낸다(2026-09-18·09-20 발행 실패의 원인). 실측으로
# 213 바이트는 통과하고 221 바이트는 거부됐다 — 한글은 한 자가 3 바이트라
# 15 개를 채우면 쉽게 넘는다. 여유를 두고 200 바이트로 자른다.
LABEL_BYTES_CAP = 200


def gcfg(cfg=None):
    return ((cfg or load_config()).get("geoai") or {})


def creds():
    if not os.path.exists(TOKEN_PATH):
        raise RuntimeError(
            "GeoAI 블로그 토큰이 없습니다 — python geoai_auth_setup.py 로 "
            "블로그 소유 계정 인증을 한 번 해주세요.")
    c = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not c.valid and c.expired and c.refresh_token:
        c.refresh(Request())
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(c.to_json())
        log("GeoAI Blogger 토큰 자동 갱신됨.")
    return c


def service():
    return build("blogger", "v3", credentials=creds(), cache_discovery=False)


def blog_id(cfg=None):
    bid = str(gcfg(cfg).get("blog_id", "")).strip()
    if not bid:
        raise RuntimeError("config.json 의 geoai.blog_id 가 비어 있습니다.")
    return bid


def posted_titles(svc, bid, pages=4):
    """이미 올라간 글 제목 집합(중복 발행 방지). 최대 pages*50 편까지 훑는다."""
    titles, token = set(), None
    for _ in range(pages):
        r = svc.posts().list(blogId=bid, maxResults=50, fetchBodies=False,
                             pageToken=token,
                             fields="items(title),nextPageToken").execute()
        for i in r.get("items", []):
            titles.add((i.get("title") or "").strip())
        token = r.get("nextPageToken")
        if not token:
            break
    return titles


def _local_date(ts):
    """Blogger 의 RFC3339 시각을 이 맥의 날짜(KST)로 바꾼다.

    블로그 시간대가 KST 가 아니어서(2026-09-16 13:30 KST 발행분이 published 에는
    2026-09-15T21:30 로 기록됐다) 문자열 앞 10자리를 그대로 쓰면 날짜가 하루 어긋난다.
    → 오프셋까지 읽어 현지 시각으로 바꾼 뒤 비교한다."""
    try:
        d = datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return ""
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return f"{d.astimezone():%Y-%m-%d}"


def posts_today(svc, bid):
    """오늘 올라간 글 제목을 모두 준다(최신 순).

    launchd 가 밀린 실행을 몰아서 돌리거나 손으로 한 번 더 돌려도 하루 상한을
    넘기지 않게 한다. 아침·저녁 2회 체제라 하루 여러 편이 정상이다."""
    r = svc.posts().list(blogId=bid, maxResults=10, fetchBodies=False,
                         fields="items(title,published)").execute()
    today = f"{datetime.now():%Y-%m-%d}"
    return [(i.get("title") or "").strip() or "(제목 없음)"
            for i in r.get("items", [])
            if _local_date(i.get("published")) == today]


def posted_today(svc, bid):
    """오늘 올라간 글이 있으면 가장 최근 제목(없으면 빈 문자열)."""
    t = posts_today(svc, bid)
    return t[0] if t else ""



def has_label(svc, bid, label):
    """그 라벨이 붙은 글이 블로그에 이미 있나. 카테고리 첫 글을 가려내는 데 쓴다."""
    if not label:
        return True
    r = svc.posts().list(blogId=bid, labels=label, maxResults=1,
                         fetchBodies=False, fields="items(title)").execute()
    return bool(r.get("items"))


def merge_labels(topical, cfg=None, pinned=()):
    """주제 라벨 + 카테고리 + 지역/브랜드 라벨을 상한 안에서 합친다.

    지역 태그와 카테고리는 '모든 게시물에 항상' 규칙이라 뒤쪽 자리를 미리 비워 두고
    채운다(주제 태그가 많아도 밀려 사라지지 않게). 카테고리가 빠지면 그 글은 카테고리
    메뉴에서 사라지므로, 개수·길이 어느 쪽으로도 잘리지 않아야 한다."""
    cfg = cfg or load_config()
    g = gcfg(cfg)
    local = [t for t in (g.get("local_tags") or cfg.get("local_tags") or []) if t]
    local = list(dict.fromkeys(local))[:4]
    pin = [t.strip() for t in (pinned or []) if t and t.strip()]
    pin = [t for t in dict.fromkeys(pin) if t not in local]
    tail = pin + local                      # 끝까지 지키는 자리
    room = max(LABEL_CAP - len(tail), 0)
    top = [t for t in dict.fromkeys(t.strip() for t in (topical or []) if t and t.strip())
           if t not in tail][:room]
    return _fit_bytes((top + tail)[:LABEL_CAP], len(tail))


def _fit_bytes(labels, keep_tail):
    """쉼표로 이은 길이가 상한을 넘으면 주제 라벨을 뒤에서부터 덜어낸다.

    뒤쪽 keep_tail 개는 지역·브랜드 라벨이라 마지막까지 남긴다(그것만으로도
    넘치면 그때는 지역 라벨도 줄인다)."""
    def size(ls):
        return len(",".join(ls).encode("utf-8"))
    out = list(labels)
    cut = len(out) - keep_tail          # 주제 라벨의 끝 경계
    while size(out) > LABEL_BYTES_CAP and cut > 0:
        cut -= 1
        del out[cut]
    while size(out) > LABEL_BYTES_CAP and out:
        out.pop()
    if len(out) < len(labels):
        log(f"라벨 길이 상한({LABEL_BYTES_CAP}바이트)에 맞춰 "
            f"{len(labels)}개 → {len(out)}개로 줄였습니다.")
    return out


def channel_links_html(cfg=None):
    """글 끝에 붙는 채널 안내. geoai.links 가 없으면 blogger.links 를 쓴다."""
    cfg = cfg or load_config()
    links = [l for l in (gcfg(cfg).get("links")
                         or (cfg.get("blogger", {}) or {}).get("links") or [])
             if (l.get("url") or "").strip()]
    if not links:
        return ""
    text = gcfg(cfg).get("cta_text") or "GeoAI·생성형AI 이야기를 더 보고 싶다면 아래 채널도 함께 보세요."
    from follow_box import follow_box_html
    return (follow_box_html(cfg, "geoai") + "<hr><p>" + _esc(text) + "</p><p><strong>📌 바로가기</strong></p><ul>"
            + "".join(f'<li><a href="{_url(l["url"])}" target="_blank" rel="noopener">'
                      f'{_esc(l.get("label", l["url"]))}</a></li>' for l in links)
            + "</ul>")


def img_html(url, alt=""):
    """카드뉴스 이미지 한 장. 폭은 글 폭에 맞춰 줄어들게 한다(모바일 대응)."""
    return (f'<p style="text-align:center"><img src="{_url(url)}" alt="{_esc(alt)}" '
            f'style="max-width:100%;height:auto;border-radius:8px"></p>')


def video_html(video_id, title=""):
    """유튜브 임베드. 세로 쇼츠라 9:16 비율 틀에 넣는다."""
    if not video_id:
        return ""
    return ('<p style="text-align:center"><iframe width="320" height="569" '
            f'src="https://www.youtube.com/embed/{_esc(video_id)}" '
            f'title="{_esc(title) or "GeoAI 브리핑"}" frameborder="0" '
            'allow="accelerometer; autoplay; clipboard-write; encrypted-media; '
            'gyroscope; picture-in-picture" allowfullscreen></iframe></p>')


def compose(body_html, images=(), video_id="", cfg=None, title=""):
    """표지 카드·영상을 글 위에, 나머지 카드뉴스를 글 아래에 붙이고 채널 안내로 닫는다.

    본문 HTML 에는 채널 안내가 없어야 한다(여기서 마지막에 한 번만 붙인다)."""
    cfg = cfg or load_config()
    images = [u for u in (images or []) if u]
    parts = []
    if images:
        parts.append(img_html(images[0], title))
    if video_id:
        parts.append("<h3>🎬 1분 브리핑 영상</h3>")
        parts.append(video_html(video_id, title))
    parts.append(body_html)
    if len(images) > 1:
        parts.append("<h3>🖼️ 카드뉴스로 한눈에</h3>")
        parts += [img_html(u, title) for u in images[1:]]
    parts.append(channel_links_html(cfg))
    return "\n".join(p for p in parts if p)


def publish(title, html_body, labels, dry_run=False, cfg=None, pinned=()):
    """GeoAI 블로그에 글 하나를 올린다. 실패해도 예외를 올리지 않고 결과 dict 를 준다."""
    cfg = cfg or load_config()
    g = gcfg(cfg)
    if not g.get("enabled", False):
        return {"status": "disabled"}
    body = {"kind": "blogger#post", "title": title, "content": html_body,
            "labels": merge_labels(labels, cfg, pinned=pinned)}
    loc = g.get("location") or {}
    if loc.get("name"):
        body["location"] = {k: v for k, v in loc.items() if v is not None}
    if dry_run:
        log(f"[DRY] GeoAI 발행 예정: {title[:60]} "
            f"({len(html_body)}자 HTML, 라벨 {len(body['labels'])}개: "
            f"{', '.join(body['labels'])})")
        return {"status": "dry_run", "html_len": len(html_body),
                "labels": body["labels"]}
    try:
        bid = blog_id(cfg)
        svc = service()
        if title.strip() in posted_titles(svc, bid):
            log(f"GeoAI: 같은 제목이 이미 있어 건너뜀 — {title[:50]}")
            return {"status": "duplicate"}
        r = svc.posts().insert(blogId=bid, body=body, isDraft=False).execute()
        log(f"GeoAI 발행 완료: {r.get('url','')}")
        return {"status": "published", "url": r.get("url", "")}
    except Exception as e:
        msg = str(e)
        if "403" in msg[:200]:
            msg += (" | 이 토큰 계정에 geoaina 블로그 쓰기 권한이 없습니다 — "
                    "블로그 소유 계정으로 geoai_auth_setup.py 를 다시 실행하세요.")
        # 실패한 본문을 남긴다 — 글 생성에 든 API 호출을 버리지 않고 원인을 찾거나
        # 고쳐서 다시 올릴 수 있다(2026-09-16 400 invalid argument 를 놓친 적이 있다).
        dump = os.path.join(POSTS_DIR, f"failed_geoai_{datetime.now():%Y%m%d_%H%M%S}.json")
        try:
            with open(dump, "w", encoding="utf-8") as f:
                json.dump(body, f, ensure_ascii=False, indent=2)
        except Exception:
            dump = "(본문 저장 실패)"
        log(f"GeoAI 발행 실패: {type(e).__name__}: {msg[:600]}")
        log(f"  실패한 본문 저장: {dump}")
        try:
            from blogger_diag import describe
            log(f"  요청 요약: {describe(body)}")
        except Exception:
            pass
        return {"error": msg[:300], "dump": dump}


if __name__ == "__main__":     # 연결·권한 점검용(발행하지 않는다)
    cfg = load_config()
    svc = service()
    bid = blog_id(cfg)
    b = svc.blogs().get(blogId=bid).execute()
    print(f"블로그: {b.get('name')} {b.get('url')}")
    try:
        svc.posts().list(blogId=bid, maxResults=1, view="ADMIN",
                         status=["DRAFT", "LIVE"], fetchBodies=False,
                         fields="items(title)").execute()
        print("쓰기 권한: OK")
    except Exception as e:
        print(f"쓰기 권한: 없음 — {str(e)[:120]}")
    print("오늘 올라간 글:", posted_today(svc, bid) or "없음")
    print("최근 제목 수:", len(posted_titles(svc, bid)))
