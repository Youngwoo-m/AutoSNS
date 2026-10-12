"""GeoAI 블로그(geoaina.blogspot.com) 글을 티스토리(na-geoai.tistory.com)에 '요약 + 원문 링크'로 올린다.

왜 요약인가: 같은 본문을 두 도메인에 통째로 올리면 Google 이 중복 문서로 보고 하나만
검색에 남긴다. 티스토리는 도메인 신뢰도가 높아 원본(블로그스팟) 대신 티스토리 쪽이 남을
공산이 크고, 그러면 geoaina 색인·애드센스 계획이 무너진다(2026-10-08 결정).
그래서 티스토리에는 대표 그림·첫 문단·3줄 요약·첫 소제목 하나·FAQ 만 싣고, 끝에
'전체 글 보기 → geoaina' 링크를 단다. 다음·카카오 검색 노출과 geoaina 백링크가 목적이다.

원본은 공개 피드(/feeds/posts/default?alt=json)로 읽는다 — 인증이 필요 없다.
티스토리는 글쓰기 Open API 가 2024년에 끝나서 Chrome(셀레니움)으로 글쓰기 화면을 조작한다.
로그인은 전용 프로필(chrome-profile-tistory/)에 한 번 해 둔다: tistory_login.py

한 번 돌 때 최대 config.tistory.per_run 편(기본 2). 새 글을 먼저, 남는 몫으로 예전 글을
오래된 것부터 채운다(새 블로그에 하루 수십 편을 쏟으면 스팸으로 잡힌다).

    ./.venv/bin/python tistory_crosspost.py --plan      # 무엇을 올릴지만
    ./.venv/bin/python tistory_crosspost.py --dry       # 글쓰기 화면까지 채우고 발행 직전에 멈춤
    ./.venv/bin/python tistory_crosspost.py --go        # 실제 발행
"""
import html
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime

from common import BASE_DIR, LOGS_DIR, load_config, log, start_chrome

SOURCE = "https://geoaina.blogspot.com"
BLOG = "https://na-geoai.tistory.com"
PROFILE = os.path.join(BASE_DIR, "chrome-profile-tistory")
STATE = os.path.join(BASE_DIR, "tistory_state.json")
# 티스토리 로그인 쿠키(TSSESSION)는 '로그인 상태 유지'를 켜도 세션 쿠키라 Chrome 을 닫으면
# 프로필에서 사라진다(2026-10-08 확인). 그래서 로그인 직후 쿠키를 이 파일에 따로 받아 두고
# 발행할 때마다 다시 넣는다. 비밀정보 — .gitignore 에 있고 권한 600.
COOKIES = os.path.join(BASE_DIR, "tistory_cookies.json")

# 티스토리 카테고리(관리 화면에서 만들어 둔 이름과 같아야 한다)
CATEGORIES = ("GeoAI 개념및실습", "GIS 도구", "재난 현장 활용", "생성형AI 사용법",
              "안전한국훈련 실무", "QGIS 실습", "GeoAI 브리핑")
# 원본 라벨 중 태그로 옮기지 않을 것(모든 글에 붙는 지역·소속 라벨)
SKIP_TAGS = {"세명대학교", "재난안전학과", "제천", "충북"}


# ─── 원본 읽기 ───────────────────────────────────────────────────────────────
def fetch_posts(n=150):
    url = f"{SOURCE}/feeds/posts/default?alt=json&max-results={n}"
    req = urllib.request.Request(url, headers={"User-Agent": "smuds/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        feed = json.load(r)["feed"]
    out = []
    for e in feed.get("entry", []):
        link = next((l["href"] for l in e.get("link", []) if l.get("rel") == "alternate"), "")
        out.append({
            "url": link, "title": e["title"]["$t"].strip(),
            "published": e["published"]["$t"],
            "labels": [c["term"].strip() for c in e.get("category", [])],
            "content": e.get("content", {}).get("$t", ""),
        })
    return out          # 최신 글이 앞


def category_of(post):
    for c in CATEGORIES:
        if c in post["labels"]:
            return c
    t = post["title"]
    if t.startswith("NaGeoAI") or "QGIS 실습" in t:
        return "QGIS 실습"
    if t.endswith("| 재난안전과 GeoAI"):
        return "GeoAI 브리핑"
    if "생성형 AI 사용법" in t:
        return "생성형AI 사용법"
    if "안전한국훈련 실무" in t:
        return "안전한국훈련 실무"
    return "GeoAI 개념및실습"


def tags_of(post):
    tags = [t for t in post["labels"] if t not in SKIP_TAGS and len(t) <= 20]
    return list(dict.fromkeys(tags))[:10]


# ─── 요약 본문 ───────────────────────────────────────────────────────────────
_BLOCK = re.compile(r"<(h[23]|p|ul|ol|figure)\b[^>]*>(.*?)</\1>", re.S | re.I)


def _text(fragment):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


YT_EMBED = re.compile(r'youtube(?:-nocookie)?\.com/embed/([\w-]{11})')


def shorts_html(video_id):
    """세로 숏츠 임베드(폭 315, 9:16). 영상이 안 뜨는 환경을 위해 아래에 링크도 둔다."""
    v = html.escape(video_id)
    return ('<h3>▶ 1분 영상으로 보기</h3>'
            '<p style="text-align:center"><iframe width="315" height="560" '
            f'src="https://www.youtube.com/embed/{v}" title="재난안전과 GeoAI 숏츠" frameborder="0" '
            'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" '
            'allowfullscreen style="max-width:100%;border-radius:12px"></iframe></p>'
            f'<p style="text-align:center;font-size:13px"><a href="https://youtube.com/shorts/{v}" '
            'target="_blank" rel="noopener">유튜브에서 보기</a> · '
            '<a href="https://www.youtube.com/@geoai-safety" target="_blank" rel="noopener">채널 구독</a></p>')


def summary_html(post):
    """원본 HTML 에서 앞부분만 골라 요약 본문을 만든다."""
    c = post["content"]
    blocks = [(m.group(1).lower(), m.group(0), _text(m.group(2))) for m in _BLOCK.finditer(c)]
    img = re.search(r'<img[^>]+src="([^"]+)"', c)
    P = []
    if img:
        P.append(f'<p style="text-align:center"><img src="{html.escape(img.group(1))}" '
                 f'alt="{html.escape(post["title"])}" style="max-width:100%;height:auto;border-radius:10px"></p>')

    lead = next((t for tag, raw, t in blocks if tag == "p" and len(t) >= 40
                 and "자료사진" not in t and "실습일" not in t), "")
    if lead:
        P.append(f"<p>{html.escape(lead)}</p>")

    # 원문에 붙은 숏츠가 있으면 같이 싣는다 — 티스토리는 색인이 잘 돼서 영상 유입 통로가 된다
    yt = YT_EMBED.search(c)
    if yt:
        P.append(shorts_html(yt.group(1)))

    # 3줄 요약(있으면) — 제목 블록 바로 다음 목록
    for i, (tag, raw, t) in enumerate(blocks):
        if tag in ("h2", "h3") and "요약" in t and i + 1 < len(blocks) and blocks[i + 1][0] == "ul":
            P.append("<h3>📌 3줄 요약</h3>" + blocks[i + 1][1])
            break

    # 첫 본문 소제목 하나와 그 문단(요약·영상·따라하기 같은 안내 칸은 건너뜀)
    skip = ("요약", "영상", "따라하기", "프롬프트", "해보기", "자주 묻는", "채널", "출처")
    for i, (tag, raw, t) in enumerate(blocks):
        if tag in ("h2", "h3") and t and not any(s in t for s in skip):
            body = [b for b in blocks[i + 1:i + 3] if b[0] == "p" and len(b[2]) >= 60]
            if body:
                P.append(f"<h3>{html.escape(t)}</h3>")
                P += [f"<p>{html.escape(b[2])}</p>" for b in body[:2]]
                break

    # FAQ(있으면)
    for i, (tag, raw, t) in enumerate(blocks):
        if tag in ("h2", "h3") and "자주 묻는" in t:
            faq = [b[1] for b in blocks[i + 1:i + 5] if b[0] == "p" and "Q." in b[2]]
            if faq:
                P.append("<h3>❓ 자주 묻는 질문</h3>" + "".join(faq[:3]))
            break

    u = html.escape(post["url"])
    P.append(f'<p style="margin:28px 0 8px;text-align:center"><a href="{u}" target="_blank" '
             'rel="noopener" style="display:inline-block;background:#0b1c3a;color:#fff;'
             'padding:12px 26px;border-radius:999px;text-decoration:none;font-weight:700">'
             '전체 글 보기 →</a></p>')
    P.append('<p style="font-size:13px;color:#7b8794;text-align:center">이 글은 '
             f'<a href="{SOURCE}/" target="_blank" rel="noopener">재난안전과 GeoAI</a> '
             '블로그 글을 요약한 것입니다. 따라하기 그림·영상·프롬프트 예시는 원문에 있습니다.</p>')
    return "\n".join(P)


# ─── 상태 ────────────────────────────────────────────────────────────────────
def state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posted": {}}


def save_state(s):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def pick(posts, done, per_run):
    """새 글(최근 3일) 먼저 오래된 순으로, 남는 몫은 예전 글을 오래된 것부터."""
    todo = [p for p in posts if p["url"] and p["url"] not in done]
    cutoff = datetime.now().astimezone().timestamp() - 3 * 86400
    fresh = [p for p in todo if datetime.fromisoformat(p["published"]).timestamp() >= cutoff]
    old = [p for p in todo if p not in fresh]
    return (list(reversed(fresh)) + list(reversed(old)))[:per_run]


# ─── 티스토리 글쓰기 화면 ────────────────────────────────────────────────────
def build_driver(headless):
    from selenium.webdriver.chrome.options import Options
    o = Options()
    o.add_argument(f"--user-data-dir={PROFILE}")
    o.add_argument("--disable-blink-features=AutomationControlled")
    o.add_experimental_option("excludeSwitches", ["enable-automation"])
    o.add_experimental_option("useAutomationExtension", False)
    o.add_argument("--window-size=1400,1000")
    o.add_argument("--lang=ko-KR")
    # 글쓰기 화면이 '임시 저장된 글을 이어서 쓸까요?' 를 물으면 '아니오' — 남의 초안을 끌어오지 않게
    o.set_capability("unhandledPromptBehavior", "dismiss")
    if headless:
        o.add_argument("--headless=new")
    d = start_chrome(o)
    d.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
                      {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"})
    restore_cookies(d)
    return d


_COOKIE_KEYS = ("name", "value", "domain", "path", "secure", "httpOnly", "sameSite", "expires")


def save_cookies(d):
    """티스토리·카카오 쿠키를 파일로 받아 둔다(세션 쿠키 포함)."""
    allc = d.execute_cdp_cmd("Network.getAllCookies", {}).get("cookies", [])
    keep = [{k: c[k] for k in _COOKIE_KEYS if k in c} for c in allc
            if "tistory" in c.get("domain", "") or "kakao" in c.get("domain", "")]
    with open(COOKIES, "w", encoding="utf-8") as f:
        json.dump(keep, f)
    os.chmod(COOKIES, 0o600)
    return len(keep)


def kakao_relogin(d):
    """티스토리 세션이 끊겼을 때 '카카오계정으로 로그인'만 눌러 다시 들어간다.

    티스토리 로그인 쿠키(TSSESSION)는 서버에서 몇 시간이면 만료된다(2026-10-08 저녁부터
    정기 실행이 전부 로그인 화면으로 튕겼다). 카카오 쪽 로그인(_kawlt)이 '로그인 상태 유지'로
    살아 있으면 버튼 한 번에 비밀번호 없이 돌아온다. 비밀번호를 묻는 화면이 나오면
    여기서 멈춘다 — 그때는 사람이 tistory_login.py 로 다시 로그인해야 한다."""
    from selenium.webdriver.common.by import By
    if "tistory.com/auth/login" not in d.current_url:
        return False
    btn = d.find_elements(By.CSS_SELECTOR, "a.link_kakao_id, .btn_login.link_kakao_id")
    if not btn:
        return False
    btn[0].click()
    picked = False
    for _ in range(25):
        time.sleep(1)
        u = d.current_url
        if "tistory.com" in u and "auth/login" not in u and "kauth" not in u:
            log("  티스토리 세션 만료 → 카카오 로그인으로 다시 들어옴")
            save_cookies(d)
            return True
        # 카카오 '간편로그인' 화면 — 저장된 계정을 고르면 비밀번호 없이 넘어간다(10/10 확인)
        if "accounts.kakao.com/login/simple" in u and not picked:
            acc = [a for a in d.find_elements(By.CSS_SELECTOR, "a.wrap_profile")
                   if "새로운 계정" not in a.text]
            if acc:
                acc[0].click()
                picked = True
                continue
        # 비밀번호 칸이 '보이고' 간편로그인 화면이 아닐 때만 포기한다(화면이 넘어가는 중이거나
        # 숨은 입력칸에 속지 않게 — 10/10 시험에서 중간 화면을 비밀번호 요구로 잘못 읽었다)
        pw = [e for e in d.find_elements(By.CSS_SELECTOR, "input[type=password]") if e.is_displayed()]
        if pw and "login/simple" not in u and _ > 6:
            log("  카카오가 비밀번호를 묻습니다 — 자동 재로그인 불가(tistory_login.py 로 다시 로그인)")
            return False
    log(f"  카카오 재로그인 시간 초과: {d.current_url[:80]}")
    return False


def close(d):
    """드라이버를 닫기 전에 바뀐 로그인 쿠키를 받아 둔다 — 티스토리 Chrome 을 쓰는 곳은 모두 이걸로 닫는다.

    카카오·티스토리 로그인 쿠키는 쓸 때마다 새 값으로 바뀐다(카카오 _kawlt 는 한 번 쓰면
    옛 값이 무효 — 10/10 시험에서 바뀐 값을 안 받아 둬 로그인이 통째로 풀렸다)."""
    try:
        if any(c["name"] == "TSSESSION" for c in
               d.execute_cdp_cmd("Network.getAllCookies", {})["cookies"]):
            save_cookies(d)
    except Exception:
        pass
    d.quit()


def restore_cookies(d):
    if not os.path.exists(COOKIES):
        return 0
    with open(COOKIES, encoding="utf-8") as f:
        cs = json.load(f)
    for c in cs:
        if c.get("expires", -1) in (-1, 0):
            c.pop("expires", None)          # 세션 쿠키는 만료일 없이 넣는다
    d.execute_cdp_cmd("Network.setCookies", {"cookies": cs})
    return len(cs)


def _shot(d, name):
    p = os.path.join(LOGS_DIR, f"{datetime.now():%Y%m%d_%H%M%S}_tistory_{name}.png")
    try:
        d.save_screenshot(p)
        log(f"  스크린샷: {p}")
    except Exception:
        pass


def write_post(d, post, body, category, tags, go):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    W = WebDriverWait(d, 25)

    try:
        d.set_window_size(1400, 1000)       # 두 번째 글부터 창이 낮아져 발행 버튼이 화면 밖으로 밀렸다(10/10)
    except Exception:
        pass
    d.get(f"{BLOG}/manage/newpost/")
    if "/manage/newpost" not in d.current_url and kakao_relogin(d):
        d.get(f"{BLOG}/manage/newpost/")
    if "/manage/newpost" not in d.current_url:
        raise RuntimeError(f"글쓰기 화면이 아님(로그인 풀림?): {d.current_url} — tistory_login.py 로 다시 로그인")
    W.until(lambda x: x.execute_script("return !!(window.tinymce && tinymce.activeEditor && tinymce.activeEditor.initialized)"))
    time.sleep(1)

    # 카테고리
    # 화면이 다 뜨기 전에 누르면 목록이 안 열려 시간 초과가 났다(10/10) — 세 번까지 다시 연다
    sel = f'#category-list [role="option"][aria-label="{category}"]'
    for n in range(3):
        try:
            time.sleep(1 + n)
            d.find_element(By.ID, "category-btn").click()
            WebDriverWait(d, 6).until(EC.element_to_be_clickable((By.CSS_SELECTOR, sel))).click()
            break
        except Exception:
            if n == 2:
                raise RuntimeError(f"카테고리 '{category}' 를 고르지 못함")

    # 제목
    t = d.find_element(By.ID, "post-title-inp")
    t.click()
    t.send_keys(post["title"])

    # 본문 — TinyMCE 에 HTML 을 그대로 넣는다
    d.execute_script("tinymce.activeEditor.setContent(arguments[0]);"
                     "tinymce.activeEditor.fire('change'); tinymce.activeEditor.save();", body)

    # 태그
    try:
        tag = d.find_element(By.ID, "tagText")
        for tg in tags:
            tag.send_keys(tg)
            tag.send_keys(Keys.ENTER)
            time.sleep(0.2)
    except Exception as e:
        log(f"  태그 입력 실패(글은 진행): {type(e).__name__}")

    # 완료 → 발행 설정 창
    d.execute_script("arguments[0].click();", d.find_element(By.ID, "publish-layer-btn"))
    W.until(EC.presence_of_element_located((By.ID, "open20")))
    d.execute_script("document.getElementById('open20').click();")      # 공개
    time.sleep(0.8)
    btn = d.find_element(By.ID, "publish-btn")
    if not go:
        _shot(d, "dry")
        log(f"  [DRY] 발행 직전 멈춤 — 버튼: {btn.text}")
        d.execute_script("arguments[0].click();", d.find_element(By.ID, "unpublish-btn"))
        return ""
    d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", btn)
    W.until(lambda x: "/manage/newpost" not in x.current_url)
    time.sleep(2)
    return find_url(post["title"])


def find_url(title, tries=6):
    """방금 올린 글 주소 — 공개 RSS 에서 제목으로 찾는다."""
    for _ in range(tries):
        try:
            req = urllib.request.Request(f"{BLOG}/rss", headers={"User-Agent": "smuds/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                x = r.read().decode("utf-8", "ignore")
            for item in re.findall(r"<item>(.*?)</item>", x, re.S):
                # RSS 제목은 '·' 같은 문자가 두 번 이스케이프돼 온다(&amp;middot;) — 두 번 푼다
                t = html.unescape(html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", re.search(r"<title>(.*?)</title>", item, re.S).group(1)))).strip()
                if t == title.strip():
                    return re.search(r"<link>(.*?)</link>", item, re.S).group(1).strip()
        except Exception:
            pass
        time.sleep(5)
    return f"{BLOG}/ (주소 확인 실패)"


def video_block(video_id):
    """가로 해설 영상(기술사 등) 임베드 — 16:9, 화면 폭에 맞춘다."""
    v = html.escape(video_id)
    return ('<h3>▶ 2분 요약 영상</h3>'
            '<p style="text-align:center"><iframe width="640" height="360" '
            f'src="https://www.youtube.com/embed/{v}" title="재난안전과 GeoAI 해설 영상" frameborder="0" '
            'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" '
            'allowfullscreen style="max-width:100%;aspect-ratio:16/9;height:auto;border-radius:12px"></iframe></p>')


def add_shorts(d, tistory_url, video_id, go, block=None, anchor=None, h2=None, move=False):
    """이미 올린 티스토리 글에 영상 칸을 끼워 넣는다. anchor 글자가 든 요소 앞, 없으면 첫 소제목 앞,
    그것도 없으면 '전체 글 보기' 앞. 편집기가 iframe 을 지우면 저장하지 않고 멈춘다."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    W = WebDriverWait(d, 25)
    num = tistory_url.rstrip("/").rsplit("/", 1)[-1]
    d.get(f"{BLOG}/manage/newpost/{num}?type=post&returnURL=ENTRY")
    if "/manage/newpost" not in d.current_url and kakao_relogin(d):
        d.get(f"{BLOG}/manage/newpost/{num}?type=post&returnURL=ENTRY")
    W.until(lambda x: x.execute_script("return !!(window.tinymce && tinymce.activeEditor && tinymce.activeEditor.initialized)"))
    time.sleep(1.5)
    cur = d.execute_script("return tinymce.activeEditor.getContent();")
    moved = False
    if move:                                # 자리 옮기기: 이미 넣은 영상 칸을 빼고 다시 넣는다
        cut = re.compile(r"<h3[^>]*>[^<]*(?:요약 영상|영상으로 보기)[^<]*</h3>\s*<p[^>]*>\s*<iframe[^>]*embed/"
                         + re.escape(video_id) + r"[^>]*>\s*</iframe>\s*</p>", re.S)
        cur, moved = cut.subn("", cur, count=1)
    if video_id in cur:
        return "already"
    block = block or shorts_html(video_id)
    i = -1
    if h2 is not None:                      # h2 글자에 h2 가 든 첫 소제목 앞('' 이면 첫 h2 앞)
        m = re.search(r"<h2\b[^>]*>(?:(?!</h2>).)*" + re.escape(h2), cur, re.S) \
            or re.search(r"<h2\b", cur)       # 그 소제목이 없으면 첫 h2 앞(도입 다음)
        i = m.start() if m else -1
    if i < 0 and anchor and anchor in cur:
        i = cur.rfind("<", 0, cur.find(anchor))
        while i > 0 and cur[i + 1] not in "hp":     # 감싼 h2/h3/p 시작 태그까지 거슬러 간다
            i = cur.rfind("<", 0, i)
    if i < 0:
        i = cur.find("<h3")
    if i < 0:
        i = cur.find("전체 글 보기")
        i = cur.rfind("<p", 0, i) if i >= 0 else len(cur)
    new = cur[:i] + block + cur[i:]
    d.execute_script("tinymce.activeEditor.setContent(arguments[0]);"
                     "tinymce.activeEditor.fire('change'); tinymce.activeEditor.save();", new)
    kept = d.execute_script("return tinymce.activeEditor.getContent();")
    if f"embed/{video_id}" not in kept:
        raise RuntimeError("편집기가 iframe 을 지움 — 저장하지 않음")
    if not go:
        return "dry-ok" + (" (옮김)" if moved else "")
    d.execute_script("arguments[0].click();", d.find_element(By.ID, "publish-layer-btn"))
    W.until(EC.presence_of_element_located((By.ID, "publish-btn")))
    time.sleep(0.8)
    btn = d.find_element(By.ID, "publish-btn")
    d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", btn)
    W.until(lambda x: "/manage/newpost" not in x.current_url)
    time.sleep(2)
    return "saved"


def update_shorts(go):
    """state 의 기존 교차 발행 글 중 원문에 숏츠가 있는 글에 숏츠 칸을 넣는다."""
    s = state()
    src = {p["url"]: p for p in fetch_posts()}
    todo = []
    for url, v in s["posted"].items():
        m = YT_EMBED.search((src.get(url) or {}).get("content", ""))
        if m:
            todo.append((v["tistory"], m.group(1), v["title"]))
    d = build_driver(headless=False)
    try:
        for turl, vid, title in todo:
            try:
                r = add_shorts(d, turl, vid, go)
            except Exception as e:
                _shot(d, "shorts_fail")
                r = f"실패 {type(e).__name__}: {str(e)[:120]}"
            log(f"  숏츠 {r}: {turl} ← {vid} | {title[:40]}")
            if go and r == "saved":
                time.sleep(8)
    finally:
        close(d)


# ─── 실행 ────────────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]
    if "--move-video" in args:              # --move-video 글번호 영상ID 소제목글자 [--go]
        k = args.index("--move-video")
        num, vid, head = args[k + 1], args[k + 2], (args[k + 3] if len(args) > k + 3 and not args[k + 3].startswith("--") else "")
        d = build_driver(headless=False)
        try:
            r = add_shorts(d, f"{BLOG}/{num}", vid, "--go" in args, block=video_block(vid), h2=head, move=True)
            log(f"  영상 옮김 {r}: {BLOG}/{num} ← {vid} (h2 '{head}' 앞)")
        finally:
            close(d)
        return
    if "--add-video" in args:               # --add-video 글번호 영상ID [--go] — 기술사 글 등에 가로 영상
        k = args.index("--add-video")
        num, vid = args[k + 1], args[k + 2]
        d = build_driver(headless=False)
        try:
            r = add_shorts(d, f"{BLOG}/{num}", vid, "--go" in args, block=video_block(vid), h2="모범답안")
            log(f"  영상 {r}: {BLOG}/{num} ← {vid}")
        finally:
            close(d)
        return
    if "--add-shorts" in args:              # 기존 글에 숏츠 넣기(--go 없으면 저장 전 확인만)
        update_shorts("--go" in args)
        return
    cfg = load_config()
    tc = cfg.get("tistory") or {}
    if tc.get("enabled") is False:
        log("티스토리: config.tistory.enabled=false — 건너뜀")
        return
    per_run = int(tc.get("per_run", 2))
    s = state()
    posts = fetch_posts()
    todo = pick(posts, s["posted"], per_run)

    if "--plan" in args or not todo:
        log(f"티스토리: 원본 {len(posts)}편 · 올린 것 {len(s['posted'])}편 · 이번 몫 {len(todo)}편")
        for p in todo:
            log(f"  → [{category_of(p)}] {p['title'][:60]}")
        return
    go = "--go" in args
    if not go and "--dry" not in args:
        print(__doc__)
        return

    d = build_driver(headless=bool(tc.get("headless", False)))
    try:
        for p in todo:
            cat, tags = category_of(p), tags_of(p)
            log(f"티스토리 {'발행' if go else '[DRY]'}: [{cat}] {p['title'][:60]}")
            try:
                url = write_post(d, p, summary_html(p), cat, tags, go)
            except Exception as e:
                _shot(d, "fail")
                log(f"  티스토리 실패: {type(e).__name__}: {str(e)[:160]}")
                if go and "로그인" in str(e):
                    try:                        # 사람이 다시 로그인해야 풀린다 — 알린다
                        from kakao_notify import notify
                        notify("[티스토리] 로그인이 풀려 교차 발행을 못 했습니다.\n"
                               "맥에서 tistory_login.py 를 실행해 다시 로그인해 주세요"
                               "(카카오 '로그인 상태 유지' 켜기).", BLOG)
                    except Exception:
                        pass
                break
            if go:
                s["posted"][p["url"]] = {"tistory": url, "title": p["title"],
                                         "at": f"{datetime.now():%Y-%m-%d %H:%M}"}
                save_state(s)
                log(f"  티스토리 발행 완료: {url}")
                time.sleep(20)          # 연달아 올리지 않는다
    finally:
        close(d)


if __name__ == "__main__":
    main()
