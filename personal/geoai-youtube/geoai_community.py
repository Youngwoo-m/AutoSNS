"""유튜브 '게시물'(커뮤니티)에 그날 블로그 글을 올린다.

왜 브라우저인가: YouTube Data API 에는 게시물 작성 기능이 없다. 그래서 로그인 세션을
담아 둔 Chrome 프로필로 youtube.com 의 작성기를 직접 다룬다(네이버 블로그 발행과 같은
방식이고, 같은 약점을 가진다 — 화면이 바뀌면 셀렉터를 고쳐야 한다).

작성기 구조(2026-09-16 확인):
  · 접힌 작성기 : #placeholder-area 를 '진짜 마우스 클릭'으로 눌러야 펼쳐진다
  · 본문       : 펼친 뒤의 #contenteditable-root 에 CDP Input.insertText 로 넣는다
  · 게시       : shadow DOM 안 button[aria-label='게시'] 을 **JS click** 으로 누른다

  · 이미지     : '이미지' 버튼(보이는 것)을 눌러 대화상자를 연 뒤, 그 안의
                 input[type=file] 에 파일 경로를 넣는다.
                 붙고 나면 유튜브가 화면을 다시 그려 그 input 은 사라진다(stale).
                 유튜브가 가로세로 2:5~5:2 만 받으므로 3:1 배너는 2:1 로 맞춰 보낸다.
셀렉터가 깨지면 실패 화면을 logs/ 에 남기고 조용히 포기한다(글 발행은 이미 끝난 뒤다).

입력은 표준입력 JSON 이다(발행 파이프라인이 subprocess 로 부른다):
    {"title": "글 제목", "summary": "첫 줄 요약", "url": "글 주소",
     "video_url": "그날 쇼츠 주소(선택)", "image": "붙일 이미지 경로(2:5~5:2)",
     "dry_run": true}

사용:
    echo '{"title":"...","url":"..."}' | python geoai_community.py        # 게시 안 함
    echo '{...}' | python geoai_community.py --go                        # 실제 게시
"""
import json
import os
import sys
import time

# 게시물 문구·설정은 GeoAI 판을 쓴다(load_config 호출 전에 세워야 병합된다).
os.environ["SMUDS_EDITION"] = "geoai"

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from common import BASE_DIR, LOGS_DIR, load_config, log

PROFILE_DIR = os.path.join(BASE_DIR, "chrome-profile-youtube")

# 게시 직후 화면에서 글이 보이는지 확인할 때 쓰는 문구 길이
VERIFY_CHARS = 12


def chrome_options(headless=True):
    o = Options()
    o.add_argument(f"--user-data-dir={PROFILE_DIR}")
    o.add_argument("--disable-blink-features=AutomationControlled")
    # use-mock-keychain 을 빼 로그인 앱(일반 크롬)과 같은 진짜 키체인 키로 쿠키를 읽고 쓴다(2026-10-28)
    o.add_experimental_option("excludeSwitches", ["enable-automation", "use-mock-keychain"])
    o.add_experimental_option("useAutomationExtension", False)
    o.add_argument("--window-size=1280,1000")
    o.add_argument("--lang=ko-KR")
    if headless:
        o.add_argument("--headless=new")
    # 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
    o.add_argument("--disable-features=MacAppCodeSignClone")
    return o


# shadow DOM 까지 훑어 버튼을 찾는다(유튜브는 대부분 shadow DOM 안에 있다).
# **크기가 0 인 사본을 거른다** — 같은 aria-label 을 가진 숨은 사본이 먼저 잡히면
# 좌표 클릭이 (0,0) 으로 빗나가고 아무 일도 일어나지 않는다(2026-09-17 확인).
DEEP_FIND = """
const label = arguments[0];
const walk = (root, depth=0) => {
  if (depth > 14) return null;
  for (const el of root.querySelectorAll('*')) {
    const l = el.getAttribute && el.getAttribute('aria-label');
    if (l === label && !el.disabled) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) return el;
    }
    if (el.shadowRoot) { const r2 = walk(el.shadowRoot, depth+1); if (r2) return r2; }
  }
  return null;
};
return walk(document);
"""

DEEP_BY_ID = """
const want = arguments[0];
const walk = (root, depth=0) => {
  if (depth > 14) return null;
  for (const el of root.querySelectorAll('*')) {
    if (el.id === want) { const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) return el; }
    if (el.shadowRoot) { const r2 = walk(el.shadowRoot, depth+1); if (r2) return r2; }
  }
  return null;
};
return walk(document);
"""

DEEP_FILE_INPUT = """
// 작성기(backstage) 대화상자 안의 파일 입력란. 페이지에는 검색창의 '이미지로 검색'
// input 도 있어서(accept 에 image/jpeg) 그걸 잡으면 엉뚱하게 검색이 열린다.
const walk = (root, depth=0) => {
  if (depth > 14) return null;
  for (const el of root.querySelectorAll('*')) {
    if (el.tagName === 'INPUT' && el.type === 'file') {
      let h = el, hops = 0;
      while (h && hops < 8) {
        if ((h.tagName||'').toLowerCase().includes('backstage')) return el;
        h = h.parentElement || h.getRootNode().host; hops++;
      }
    }
    if (el.shadowRoot) { const r = walk(el.shadowRoot, depth+1); if (r) return r; }
  }
  return null;
};
return walk(document);
"""

HAS_PREVIEW = """
const walk = (root, depth=0) => {
  if (depth > 14) return false;
  for (const el of root.querySelectorAll('*')) {
    if (el.id === 'image-preview-container' ||
        el.tagName === 'YTD-BACKSTAGE-MULTI-IMAGE-THUMBNAIL-RENDERER') {
      const r = el.getBoundingClientRect(); if (r.height > 10) return true;
    }
    if (el.shadowRoot && walk(el.shadowRoot, depth+1)) return true;
  }
  return false;
};
return walk(document);
"""


def _click_at(driver, el):
    """요소 한가운데를 '진짜 마우스 클릭'으로 누른다.

    유튜브 작성기는 Selenium 클릭이 막히고(element not interactable) JS focus() 로는
    입력이 먹지 않는다. CDP 로 신뢰된 마우스 이벤트를 보내야 작성기가 펼쳐진다."""
    r = driver.execute_script(
        "const b=arguments[0].getBoundingClientRect();"
        "return {x:b.x+b.width/2, y:b.y+b.height/2};", el)
    for ev in ("mousePressed", "mouseReleased"):
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {
            "type": ev, "x": r["x"], "y": r["y"], "button": "left",
            "clickCount": 1, "buttons": 1 if ev == "mousePressed" else 0})
    time.sleep(1)


def _shot(driver, name):
    path = os.path.join(LOGS_DIR, f"community_{name}_{time.strftime('%Y%m%d_%H%M%S')}.png")
    try:
        driver.save_screenshot(path)
        log(f"  화면 저장: {path}")
    except Exception:
        pass


def _ccfg(cfg=None):
    return (cfg or load_config()).get("community_post") or {}


def post(text, image_path=None, dry_run=True, cfg=None):
    """게시물 하나를 올린다. 실패해도 예외를 올리지 않고 결과 dict 를 준다."""
    cfg = cfg or load_config()
    c = _ccfg(cfg)
    if not c.get("enabled", False):
        return {"status": "disabled"}
    handle = c.get("handle", "geoai-safety")
    if not os.path.exists(PROFILE_DIR):
        return {"error": "로그인 프로필이 없습니다 — geoai_community_login.py 를 먼저 실행하세요."}
    driver = webdriver.Chrome(options=chrome_options(headless=c.get("headless", True)))
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"})
        # 커뮤니티 탭 주소가 /community 에서 /posts 로 바뀌었다(2026-09 확인). 둘 다 시도한다.
        placeholder = None
        for path in ("posts", "community"):
            driver.get(f"https://www.youtube.com/@{handle}/{path}")
            time.sleep(6)
            placeholder = driver.execute_script(DEEP_BY_ID, "placeholder-area")
            if placeholder is not None:
                log(f"  작성기 찾음: /@{handle}/{path}")
                break
        if placeholder is None:
            _shot(driver, "no_composer")
            return {"error": "작성기를 찾지 못했습니다(로그인이 풀렸거나 화면이 바뀜)."}
        # 작성기는 접혀 있다. 이 자리를 눌러야 입력란이 펼쳐진다(#contenteditable-root 는
        # 펼치기 전까지 0x0 이라 클릭도 입력도 먹지 않는다).
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", placeholder)
        time.sleep(1)
        _click_at(driver, placeholder)
        time.sleep(2)
        box = driver.execute_script(DEEP_BY_ID, "contenteditable-root")
        if box is None:
            _shot(driver, "no_editor")
            return {"error": "입력란이 펼쳐지지 않았습니다."}
        # 작성기는 접힌 상태라 Selenium 클릭이 막힌다(element not interactable).
        # 화면 안으로 올린 뒤 JS 로 펼치고, 글자는 CDP 로 직접 넣는다.
        _click_at(driver, box)
        driver.execute_cdp_cmd("Input.insertText", {"text": text})
        time.sleep(1)
        typed = driver.execute_script("return arguments[0].innerText || '';", box)
        if text.strip()[:VERIFY_CHARS] not in typed:
            _shot(driver, "typing_failed")
            return {"error": f"본문이 입력되지 않았습니다(입력된 글자 {len(typed)}자)."}
        log(f"  본문 입력 {len(typed)}자")

        if image_path and os.path.exists(image_path):
            btn = driver.execute_script(DEEP_FIND, "이미지 추가")
            if btn is None:
                log("  이미지 버튼을 찾지 못해 글만 올립니다")
            else:
                _click_at(driver, btn)
                time.sleep(3)
                inp = driver.execute_script(DEEP_FILE_INPUT)
                if inp is None:
                    log("  이미지 입력란을 찾지 못해 글만 올립니다")
                else:
                    inp.send_keys(os.path.abspath(image_path))
                    time.sleep(9)        # 첨부되면 화면이 다시 그려진다(요소는 stale)
                    if driver.execute_script(HAS_PREVIEW):
                        log("  이미지 첨부 완료")
                    else:
                        _shot(driver, "image_failed")
                        log("  이미지가 붙지 않았습니다(비율 2:5~5:2 인지 확인) — 글만 올립니다")

        if dry_run:
            _shot(driver, "dry")
            log("[DRY] 작성기까지만 채웠습니다(게시하지 않음).")
            return {"status": "dry_run"}

        btn = driver.execute_script(DEEP_FIND, "게시")
        if btn is None:
            _shot(driver, "no_post_button")
            return {"error": "게시 버튼을 찾지 못했습니다."}
        # 이미지를 붙이면 편집 대화상자가 떠서 좌표 클릭을 가로챈다(닫기 버튼은 이미지를
        # 지워 버린다). JS 클릭은 그 위로 그대로 전달된다.
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(8)
        # 게시 직후 화면은 아직 목록을 다시 그리지 않는다 — 새로고침해서 확인한다.
        driver.get(f"https://www.youtube.com/@{handle}/posts")
        time.sleep(6)
        body = driver.execute_script("return document.body.innerText;") or ""
        ok = text.strip()[:VERIFY_CHARS] in body
        if not ok:
            _shot(driver, "after_post")
        log(f"게시물 작성 {'완료' if ok else '결과 확인 필요'}")
        return {"status": "posted" if ok else "unverified"}
    except Exception as e:
        _shot(driver, "error")
        log(f"게시물 작성 실패: {type(e).__name__}: {str(e)[:150]}")
        return {"error": f"{type(e).__name__}: {str(e)[:150]}"}
    finally:
        driver.quit()


def text_for(post_data, cfg=None):
    """그날 블로그 글 → 게시물 문구(제목 + 한 줄 + 링크)."""
    cfg = cfg or load_config()
    c = _ccfg(cfg)
    title = (post_data.get("title") or "").split(" | ")[0].strip()
    summary = ""
    s = post_data.get("summary")
    if isinstance(s, str):
        summary = next((l.lstrip("· ").strip() for l in s.splitlines() if l.strip()), "")
    elif s:
        summary = str(s[0]).strip()
    url = post_data.get("url", "")
    video = post_data.get("video_url", "")     # 있으면 유튜브가 영상 카드로 펼쳐 준다
    tail = c.get("tail", "#GeoAI #재난안전 #생성형AI")
    return "\n".join(x for x in [f"📝 {title}", summary, url, video, tail] if x)


if __name__ == "__main__":
    payload = {}
    if not sys.stdin.isatty():
        raw = sys.stdin.read().strip()
        if raw:
            payload = json.loads(raw)
    dry = "--go" not in sys.argv
    text = payload.get("text") or text_for(payload)
    result = post(text, payload.get("image"), dry_run=dry)
    result["text"] = text
    print(json.dumps(result, ensure_ascii=False))
