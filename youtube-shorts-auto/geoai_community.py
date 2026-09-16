"""유튜브 '게시물'(커뮤니티)에 그날 블로그 글을 올린다.

왜 브라우저인가: YouTube Data API 에는 게시물 작성 기능이 없다. 그래서 로그인 세션을
담아 둔 Chrome 프로필로 youtube.com 의 작성기를 직접 다룬다(네이버 블로그 발행과 같은
방식이고, 같은 약점을 가진다 — 화면이 바뀌면 셀렉터를 고쳐야 한다).

작성기 구조(2026-09-16 확인):
  · 본문   : light DOM 의 #contenteditable-root
  · 이미지 : 숨은 input[type=file] (accept 에 image/jpeg 포함) — 클릭 대신 경로를 넣는다
  · 게시   : shadow DOM 안 button[aria-label='게시']
셀렉터가 깨지면 실패 화면을 logs/ 에 남기고 조용히 포기한다(글 발행은 이미 끝난 뒤다).

입력은 표준입력 JSON 이다(발행 파이프라인이 subprocess 로 부른다):
    {"title": "글 제목", "summary": "첫 줄 요약", "url": "글 주소",
     "image": "배너 PNG 경로", "dry_run": true}

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
    o.add_experimental_option("excludeSwitches", ["enable-automation"])
    o.add_experimental_option("useAutomationExtension", False)
    o.add_argument("--window-size=1280,1000")
    o.add_argument("--lang=ko-KR")
    if headless:
        o.add_argument("--headless=new")
    return o


# shadow DOM 까지 훑어 버튼을 찾는다(스튜디오·유튜브는 대부분 shadow DOM 안에 있다).
DEEP_FIND = """
const label = arguments[0];
const walk = (root, depth=0) => {
  if (depth > 12) return null;
  for (const el of root.querySelectorAll('*')) {
    const l = el.getAttribute && el.getAttribute('aria-label');
    if (l === label && !el.disabled) return el;
    if (el.shadowRoot) { const r = walk(el.shadowRoot, depth+1); if (r) return r; }
  }
  return null;
};
return walk(document);
"""

DEEP_FILE_INPUT = """
const walk = (root, depth=0) => {
  if (depth > 12) return null;
  for (const el of root.querySelectorAll('*')) {
    if (el.tagName === 'INPUT' && el.type === 'file' && (el.accept||'').includes('image/')) return el;
    if (el.shadowRoot) { const r = walk(el.shadowRoot, depth+1); if (r) return r; }
  }
  return null;
};
const el = walk(document);
if (el) { el.style.display='block'; el.style.visibility='visible'; el.style.opacity=1;
          el.style.position='fixed'; el.style.left='0'; el.style.top='0';
          el.style.width='200px'; el.style.height='40px'; }
return el;
"""


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
        driver.get(f"https://www.youtube.com/@{handle}/community")
        time.sleep(6)
        box = driver.execute_script("return document.querySelector('#contenteditable-root');")
        if box is None:
            _shot(driver, "no_composer")
            return {"error": "작성기를 찾지 못했습니다(로그인이 풀렸거나 화면이 바뀜)."}
        box.click()
        time.sleep(1)
        for i, line in enumerate(text.split("\n")):
            if i:
                box.send_keys("\n")
            box.send_keys(line)
        time.sleep(1)

        if image_path and os.path.exists(image_path):
            inp = driver.execute_script(DEEP_FILE_INPUT)
            if inp is None:
                log("  이미지 input 을 찾지 못해 텍스트만 올립니다")
            else:
                inp.send_keys(os.path.abspath(image_path))
                time.sleep(6)
                save = driver.execute_script(DEEP_FIND, "이미지 저장")
                if save is not None:            # 자르기 화면이 뜨면 저장까지 눌러 준다
                    driver.execute_script("arguments[0].click();", save)
                    time.sleep(4)

        if dry_run:
            _shot(driver, "dry")
            log("[DRY] 작성기까지만 채웠습니다(게시하지 않음).")
            return {"status": "dry_run"}

        btn = driver.execute_script(DEEP_FIND, "게시")
        if btn is None:
            _shot(driver, "no_post_button")
            return {"error": "게시 버튼을 찾지 못했습니다."}
        driver.execute_script("arguments[0].click();", btn)
        time.sleep(8)
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
    tail = c.get("tail", "#GeoAI #재난안전 #생성형AI")
    return "\n".join(x for x in [f"📝 {title}", summary, url, tail] if x)


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
