"""틱톡 웹(TikTok Studio)에 로그인된 크롬 프로필로 세로 mp4 를 올린다.

API(tiktok_upload.py) 는 앱 심사를 통과해야 공개 게시가 되고, 2026-09-22 현재
개발자 포털에 앱 자체가 없어 쓸 수 없다. 그래서 인스타와 같은 방식 —
전용 크롬 프로필에 한 번 로그인해 두고 브라우저로 올리는 길 — 을 함께 둔다.

  tiktok_web_login.py   최초 1회 로그인(사람이 직접 로그인, 세션만 프로필에 남는다)
  tiktok_web.py         업로드. 기본은 dry-run 이라 '게시' 를 누르지 않는다.

안전장치(다른 업로더와 같은 철학):
  - 인자 없이 돌리면 dry-run: 영상·캡션을 올려두고 게시 직전에 멈춘 뒤 스크린샷만 남긴다.
  - 실제 게시는 --post 를 줄 때만 일어난다.
  - 같은 mp4 를 두 번 올리지 않게 tiktok_web_state.json 에 기록한다.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

from common import BASE_DIR, LOGS_DIR, POSTS_DIR, load_config, log

PROFILE_DIR = os.path.join(BASE_DIR, "chrome-profile-tiktok")
STATE_PATH = os.path.join(BASE_DIR, "tiktok_web_state.json")
UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?from=webapp"

# 한국어/영어 UI 를 모두 받는다(틱톡은 계정 언어에 따라 바뀐다).
POST_LABELS = ["게시", "Post", "업로드", "Upload"]
CAPTION_HINTS = ["설명", "캡션", "Description", "caption"]


CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DEBUG_PORT = 9222


def _port_open(port, host="127.0.0.1"):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def launch_chrome(url=None, port=DEBUG_PORT):
    """Chrome 을 '평범한 앱으로' 띄우고 디버깅 포트가 열릴 때까지 기다린다.

    틱톡은 chromedriver 가 직접 띄운 Chrome(--test-type=webdriver 등)을 감지해
    접속 즉시 로그인 쿠키를 지워버린다(2026-09-22 확인). 그래서 Chrome 은 평범하게
    띄우고 Selenium 은 디버깅 포트로 '붙기만' 한다. 그러면 자동화 흔적이 남지 않는다.
    """
    if _port_open(port):
        return None                      # 이미 떠 있으면 그대로 쓴다
    args = [CHROME, f"--user-data-dir={PROFILE_DIR}", f"--remote-debugging-port={port}",
            "--no-first-run", "--no-default-browser-check", "--lang=ko-KR",
            # 크롬 155 부터 이 프로필로 띄우면 '사용자 선택' 창만 열려 Selenium 이 붙을 페이지가
            # 없었다(10/12~15 틱톡 게시 중단). 프로필을 지정하고 빈 탭을 하나 연다.
            "--profile-directory=Default",
            "--window-size=1400,1000",
            "--disable-features=MacAppCodeSignClone"]  # 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
    args.append(url or "about:blank")
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if _port_open(port):
            return proc
        time.sleep(0.5)
    raise SystemExit("Chrome 디버깅 포트가 열리지 않았습니다.")


def _kill_debug_chrome(port=DEBUG_PORT):
    """디버깅 포트에 떠 있는 틱톡 전용 Chrome 만 끈다(사용자의 다른 Chrome 은 건드리지 않는다)."""
    subprocess.run(["pkill", "-f", f"remote-debugging-port={port}"], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    for _ in range(20):
        if not _port_open(port):
            return
        time.sleep(0.5)


def build_driver(headless=False, port=DEBUG_PORT):
    """평범하게 띄운 Chrome 에 붙는다(headless 는 틱톡에서 쓰지 않는다).

    10/12~10/15: 떠 있던 Chrome 이 멈춰 'cannot connect to chrome / unable to discover open
    pages' 로 사흘 동안 한 편도 못 올렸다. 붙지 못하면 그 Chrome 을 끄고 새로 띄워 한 번 더 붙는다."""
    for attempt in (1, 2):
        launch_chrome(port=port)
        o = Options()
        o.add_experimental_option("debuggerAddress", f"127.0.0.1:{port}")
        try:
            return webdriver.Chrome(options=o)
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                raise
            log(f"틱톡 Chrome 에 붙지 못함({type(e).__name__}) — 끄고 다시 띄웁니다")
            _kill_debug_chrome(port)


def shot(d, name):
    p = os.path.join(LOGS_DIR, f"{datetime.now():%Y%m%d_%H%M%S}_tiktok_{name}.png")
    try:
        d.save_screenshot(p)
        log(f"스크린샷: {p}")
    except Exception as e:
        log(f"스크린샷 실패: {e}")
    return p


def _state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"posted": []}


def _mark(video):
    s = _state()
    # 파일 이름만 적으면 재난 숏츠처럼 편마다 이름이 같은(final.mp4) 영상이 '이미 올림'으로
    # 막힌다 — 전체 경로(path)도 함께 적고, 비교는 경로가 있으면 경로로 한다.
    s["posted"].append({"video": os.path.basename(video), "path": os.path.abspath(video),
                        "at": datetime.now().isoformat(timespec="seconds")})
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def already_posted(video):
    full = os.path.abspath(video)
    return any((x["path"] == full) if x.get("path") else (x["video"] == os.path.basename(video))
               for x in _state()["posted"])


def logged_in(d):
    """업로드 화면까지 들어가지면 로그인된 것으로 본다."""
    return "login" not in d.current_url and "/upload" in d.current_url


def _file_input(d, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        for e in d.find_elements(By.CSS_SELECTOR, "input[type=file]"):
            return e            # 숨어 있어도 send_keys 는 동작한다
        time.sleep(1)
    return None


def _caption_box(d, timeout=40):
    """캡션 입력칸(contenteditable)을 찾는다. 영상 처리 중에는 늦게 나타난다."""
    end = time.time() + timeout
    while time.time() < end:
        boxes = [e for e in d.find_elements(By.CSS_SELECTOR, "div[contenteditable='true']")
                 if e.is_displayed()]
        if boxes:
            return boxes[0]
        time.sleep(1)
    return None


def _clear_caption(d, box):
    """틱톡 캡션칸은 파일명이 미리 채워져 있다. 전부 지운다.

    contenteditable 에서는 Cmd+A 가 안 먹는 경우가 있어 Selection API 로 고르고
    BACK_SPACE 를 보낸다(인스타에서 확인한 방식).
    """
    box.click()
    time.sleep(0.3)
    d.execute_script("""
      const el = arguments[0];
      el.focus();
      const r = document.createRange(); r.selectNodeContents(el);
      const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
    """, box)
    time.sleep(0.2)
    ActionChains(d).send_keys(Keys.BACK_SPACE).perform()
    time.sleep(0.5)


def _type_caption(d, box, caption):
    _clear_caption(d, box)
    for i, line in enumerate(caption.split("\n")):
        if i:
            ActionChains(d).key_down(Keys.SHIFT).send_keys(Keys.ENTER)\
                .key_up(Keys.SHIFT).perform()
        ActionChains(d).send_keys(line).perform()
        time.sleep(0.4)     # 해시태그 자동완성 창이 뜨면 가라앉을 시간을 준다
    ActionChains(d).send_keys(Keys.ESCAPE).perform()
    time.sleep(0.5)
    return box.text.strip()


def _click_post(d):
    for lb in POST_LABELS:
        for e in d.find_elements(By.XPATH,
                                 f"//button[normalize-space()='{lb}']"
                                 f"|//div[@role='button'][normalize-space()='{lb}']"):
            if e.is_displayed() and e.is_enabled():
                e.click()
                return lb
    return None


def _wait_uploaded(d, timeout=300):
    """영상 전송이 끝날 때까지 기다린다(상단 진행률 'NN%'·'N초 남음'이 사라질 때까지)."""
    import re as _re
    t0 = time.time()
    while time.time() - t0 < timeout:
        top = d.execute_script("return (document.body.innerText||'').slice(0,600);") or ""
        if not _re.search(r"\d+(\.\d+)?%|남음|remaining", top):
            return True
        time.sleep(3)
    return False


def _confirm_posted(d, caption, timeout=150):
    """게시가 실제로 끝났는지 게시물 목록에서 확인한다.

    10/12: '게시' 클릭 20초 뒤 다음 영상으로 넘어가자 산불·퀴즈 2편이 조용히 사라졌다
    (전송·검사가 덜 끝난 상태). 끝날 때까지 기다리고, 목록에 제목이 보여야 성공으로 친다."""
    title = (caption.split("\n")[0] or "").strip()[:14]
    t0 = time.time()
    while time.time() - t0 < timeout:
        for lb in ("지금 게시", "Post now"):
            for e in d.find_elements(By.XPATH, f"//button[normalize-space()='{lb}']"):
                try:
                    d.execute_script("arguments[0].click();", e)
                    log(f"'{lb}' 확인 창 누름")
                except Exception:
                    pass
        if "/tiktokstudio/content" in d.current_url:
            break
        time.sleep(3)
    for _ in range(6):
        if "/tiktokstudio/content" not in d.current_url:
            d.get("https://www.tiktok.com/tiktokstudio/content")
        time.sleep(10)
        if title and title in (d.execute_script("return document.body.innerText||'';") or ""):
            return True
        d.get("https://www.tiktok.com/tiktokstudio/content")
    return False


def _set_location(d, name="충북제천"):
    """위치를 name 으로 정한다. 정해졌으면 True.

    업로드·편집 화면의 '위치' 칸 아래 추천 칩에 '충북제천'이 뜬다 — 칩을 누르고,
    없으면 검색칸에 쳐서 첫 결과를 고른다."""
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys

    def chosen():
        return bool(d.execute_script(
            "const n=arguments[0];return [...document.querySelectorAll('input')].some(i=>i.placeholder&&/위치/.test(i.placeholder)&&i.value===n)"
            "||[...document.querySelectorAll('div,span')].some(e=>e.children.length===0&&e.textContent.trim()===n&&e.closest('[class*=select],[class*=Select],[class*=location],[class*=Location]'));",
            name))
    for e in d.find_elements(By.XPATH, f"//*[normalize-space(text())='{name}']"):
        try:
            d.execute_script("arguments[0].scrollIntoView({block:'center'});", e)
            ActionChains(d).move_to_element(e).click().perform()
            time.sleep(1.5)
            break
        except Exception:
            continue
    if chosen():
        return True
    inp = next((i for i in d.find_elements(By.CSS_SELECTOR, "input") if "위치" in (i.get_attribute("placeholder") or "")), None)
    if inp is None:
        return False
    ActionChains(d).move_to_element(inp).click().perform()
    inp.send_keys(name)
    time.sleep(3)
    for e in d.find_elements(By.XPATH, f"//*[contains(normalize-space(text()),'{name}')]"):
        if e != inp:
            try:
                ActionChains(d).move_to_element(e).click().perform()
                time.sleep(1.5)
                break
            except Exception:
                continue
    return chosen()


# 인기 음원에서 피할 이름 — 뉴스·시사 음원이나 남의 '오리지널 사운드'는 재난안전 영상과 맞지 않는다.
SOUND_SKIP = ("뉴스", "속보", "계엄", "비상", "전쟁", "정치", "original sound", "오리지널 사운드")


def _add_popular_sound(d, volume_db=-20):
    # ※ 기본으로 쓰지 않는다(upload(popular_sound=False)). 웹 편집기는 음원을 영상 소리에 섞어
    #   넣을 뿐 그 음원 페이지와 연결하지 않아('오리지널 사운드'로 남는다) 인기 음원의 추천 효과가
    #   없고, 우리 영상의 나레이션·배경음악 위에 음악이 겹친다(2026-10-12 확인).
    """업로드 화면의 '사운드' 편집기에서 추천(인기) 음원 하나를 낮은 볼륨으로 깐다. 넣은 음원 이름(실패면 "").

    우리 영상에는 나레이션·배경음악이 이미 있다 — 음원은 추천 노출을 위한 것이라
    -20dB 로 아주 작게 둔다. 어느 단계든 실패하면 편집을 취소하고 음원 없이 진행한다."""
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys
    try:
        btn = [b for b in d.find_elements(By.XPATH, "//button[normalize-space()='사운드']")]
        if not btn:
            return ""
        ActionChains(d).move_to_element(btn[0]).click().perform()
        time.sleep(8)
        for b in d.find_elements(By.XPATH, "//button[normalize-space()='확인']"):   # 'Phone mode' 안내
            try:
                ActionChains(d).move_to_element(b).click().perform()
                time.sleep(1)
                break
            except Exception:
                pass
        # 추천 목록: 이름 + 오른쪽 '+' 버튼
        items = d.execute_script("""return [...document.querySelectorAll('div')].filter(e=>{
            const t=(e.innerText||'').split('\\n'); return e.offsetParent && t.length>=2 && t.length<=3
              && /\\d\\d:\\d\\d ·/.test(t[1]||'') && e.querySelectorAll('button').length>=1 && e.getBoundingClientRect().x<500;})
            .map(e=>[e, (e.innerText||'').split('\\n')[0]]);""")
        name, plus = "", None
        for el, nm in items:
            if any(k.lower() in nm.lower() for k in SOUND_SKIP):
                continue
            bs = el.find_elements(By.TAG_NAME, "button")
            if bs:
                name, plus = nm, bs[-1]
                break
        if plus is None:
            raise RuntimeError("추천 음원 없음")
        ActionChains(d).move_to_element(plus).click().perform()
        time.sleep(5)
        vol = d.execute_script("""return [...document.querySelectorAll('input[type=text]')].find(i=>i.offsetParent
            && (i.closest('[class*=PropSetting]')) && i.getBoundingClientRect().y<220) || null;""")
        if vol is None:
            raise RuntimeError("볼륨 칸 없음")
        ActionChains(d).move_to_element(vol).click().key_down(Keys.COMMAND).send_keys("a").key_up(Keys.COMMAND)\
            .send_keys(str(volume_db)).send_keys(Keys.ENTER).perform()
        time.sleep(1)
        save = d.execute_script("""return [...document.querySelectorAll('button')].find(b=>b.offsetParent
            && b.textContent.trim()==='저장' && b.getBoundingClientRect().y<60) || null;""")
        d.execute_script("arguments[0].click();", save)
        time.sleep(8)
        return name if name in (d.execute_script("return document.body.innerText||'';") or "") else ""
    except Exception as e:  # noqa: BLE001
        log(f"인기 음원 넣기 실패(음원 없이 진행): {type(e).__name__}: {str(e)[:80]}")
        for b in d.find_elements(By.XPATH, "//button[normalize-space()='취소']"):
            try:
                if b.location.get("y", 999) < 60:
                    d.execute_script("arguments[0].click();", b)
                    time.sleep(3)
                    break
            except Exception:
                pass
        return ""


def _set_ai_generated(d):
    """'AI 생성 콘텐츠' 표시를 켠다. 켜졌으면 True.

    AI 아바타(HeyGen)처럼 실제 사람처럼 보이는 합성 영상은 틱톡 정책상 표시해야 한다.
    스위치는 '더 보기'를 펼쳐야 보인다(2026-10-12 TikTok Studio 기준)."""
    for e in d.find_elements(By.XPATH, "//*[normalize-space(text())='더 보기' or normalize-space(text())='Show more']"):
        try:
            d.execute_script("arguments[0].click();", e)
            time.sleep(1)
        except Exception:
            pass
    js = """return [...document.querySelectorAll('[role=switch],input[type=checkbox]')].find(e=>{
        let p=e; for(let i=0;i<6&&p;i++){ if(/AI 생성 콘텐츠|AI-generated content/.test(p.textContent||'')
            && (p.textContent||'').length<120) return true; p=p.parentElement; } return false; }) || null;"""
    sw = d.execute_script(js)
    if sw is None:
        return False
    on = lambda: str(sw.get_attribute("aria-checked") or sw.get_attribute("checked") or "").lower() in ("true", "checked")
    if not on():
        d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", sw)
        time.sleep(1.5)
        for b in d.find_elements(By.XPATH, "//button[.//text()[normalize-space()='켜기' or normalize-space()='Turn on']]"):
            try:
                d.execute_script("arguments[0].click();", b)
                time.sleep(1)
            except Exception:
                pass
    return on()


def upload(video, caption, post=False, ai_generated=False, location="충북제천", popular_sound=False):
    if not os.path.exists(video):
        raise SystemExit(f"mp4 가 없습니다: {video}")
    if post and already_posted(video):
        raise SystemExit(f"이미 올린 영상입니다: {os.path.basename(video)}")

    d = build_driver()
    try:
        d.get(UPLOAD_URL)
        time.sleep(8)
        for _ in range(11):        # 방금 띄운 Chrome 은 업로드 화면이 늦게 뜬다(10/15 첫 시도 실패)
            if d.find_elements(By.CSS_SELECTOR, "input[type=file]"):
                break
            time.sleep(2)
        if not logged_in(d):
            shot(d, "not_logged_in")
            raise SystemExit("로그인이 안 돼 있습니다 — tiktok_web_login.py 를 먼저 실행하세요.")

        inp = _file_input(d)
        if inp is None:
            shot(d, "no_file_input")
            raise SystemExit("파일 입력칸을 못 찾았습니다(화면 구조 변경?)")
        inp.send_keys(os.path.abspath(video))
        log(f"영상 전송: {os.path.basename(video)}")
        time.sleep(10)

        if popular_sound and not video.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            snd = _add_popular_sound(d)
            log(f"인기 음원: {snd} (-20dB)" if snd else "인기 음원 없이 진행")
        box = _caption_box(d)
        if box is None:
            shot(d, "no_caption_box")
            raise SystemExit("캡션 입력칸을 못 찾았습니다")
        got = _type_caption(d, box, caption)
        log(f"캡션 입력됨({len(got)}자): {got[:60]}…")
        if location:
            log(f"위치 '{location}' " + ("지정" if _set_location(d, location) else "지정 실패(위치 없이 진행)"))
        if ai_generated:
            if not _set_ai_generated(d):
                shot(d, "no_ai_label")
                raise SystemExit("'AI 생성 콘텐츠' 표시를 켜지 못해 게시하지 않습니다")
            log("'AI 생성 콘텐츠' 표시 켬")

        if not post:
            p = shot(d, "dryrun")
            log("DRY-RUN: '게시' 를 누르지 않고 멈춥니다. 화면을 확인하세요.")
            log("실제 게시는 --post 를 붙여 다시 실행하세요.")
            if sys.stdin.isatty():
                input("확인했으면 Enter 를 눌러 창을 닫습니다... ")
            return {"status": "dry_run", "shot": p}

        if not _wait_uploaded(d):
            shot(d, "upload_timeout")
            raise SystemExit("영상 전송이 5분 안에 끝나지 않아 게시하지 않습니다")
        # AI 표시 스위치를 누르면 설명칸이 다시 그려지는 일이 있어, 게시 직전에 한 번 더 확인
        box = _caption_box(d, timeout=10)
        if box is not None and (caption.split("\n")[0][:10] not in (box.text or "")):
            got = _type_caption(d, box, caption)
            log(f"설명이 비어 다시 입력({len(got)}자)")
        lb = _click_post(d)
        if lb is None:
            shot(d, "no_post_button")
            raise SystemExit("'게시' 버튼을 못 찾았습니다")
        log(f"'{lb}' 클릭 — 게시물 목록에 나타날 때까지 기다립니다")
        ok = _confirm_posted(d, caption)
        p = shot(d, "posted" if ok else "post_unconfirmed")
        if not ok:
            raise SystemExit("게시물 목록에서 확인되지 않았습니다(게시 실패 가능)")
        _mark(video)
        log("✅ 게시 완료(게시물 목록에서 확인)")
        return {"status": "posted", "shot": p}
    finally:
        # 붙어 있는 브라우저는 닫지 않는다 — 닫으면 다음 실행 때 다시 띄워야 하고,
        # 종료 시점에 따라 쿠키가 제대로 기록되지 않을 수 있다.
        pass


def _latest():
    """영상이 실제로 렌더링된 것 중 가장 최근 대본 json 을 돌려준다.

    대본만 만들어지고 렌더링 전인 json 이 맨 뒤에 올 수 있으므로(그날 아침 파이프라인
    중간 상태), video 가 비었거나 파일이 없는 건 건너뛴다.

    파일명 정렬은 쓰지 않는다 — 재난안전판(20260921_...)과 GeoAI판(geoai_20260921_...)이
    이름 규칙이 달라 사전순으로는 시간 순서가 뒤집힌다. 수정시각으로 고른다.
    """
    paths = [os.path.join(POSTS_DIR, f) for f in os.listdir(POSTS_DIR) if f.endswith(".json")]
    for path in sorted(paths, key=os.path.getmtime, reverse=True):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        v = data.get("video")
        if v and os.path.exists(v):
            return data
    raise SystemExit("렌더링된 영상이 있는 대본을 찾지 못했습니다.")


def build_caption(data, cfg):
    from tiktok_upload import _build_caption
    return _build_caption(data, cfg.get("youtube", {}))


def _data_for(video):
    """주어진 mp4 에 해당하는 대본 json 을 찾는다(캡션이 영상과 어긋나지 않게)."""
    want = os.path.basename(video)
    for f in os.listdir(POSTS_DIR):
        if not f.endswith(".json"):
            continue
        with open(os.path.join(POSTS_DIR, f), encoding="utf-8") as fp:
            data = json.load(fp)
        if os.path.basename(data.get("video") or "") == want:
            return data
    raise SystemExit(f"{want} 에 해당하는 대본 json 을 찾지 못했습니다.")


if __name__ == "__main__":
    cfg = load_config()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        video = args[0] if os.path.isabs(args[0]) else os.path.join(POSTS_DIR, args[0])
        data = _data_for(video)
    else:
        data = _latest()
        video = data["video"]
    caption = build_caption(data, cfg)
    print(upload(video, caption, post="--post" in sys.argv))
