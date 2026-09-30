"""저장된 Chrome 프로필로 인스타그램 웹에 카드뉴스를 '캐러셀'로 게시한다.

주의: 인스타그램 웹은 봇 탐지가 강하고 DOM 이 자주 바뀐다. 셀렉터가 안 맞으면
logs/ 에 단계별 스크린샷(.png)을 남기니 그걸 보고 셀렉터를 조정한다.
config.instagram.dry_run=true 면 '공유하기' 직전에 멈추고 스크린샷만 남긴다.

★ 안전장치: 수동 실행(python post_instagram.py)은 항상 dry_run.
  실제 게시는 스케줄 엔트리(run_weekly.py)에서 dry_run=False 로만 일어난다.
  (네이버 프로젝트에서 dry_run=false 로 테스트하다 실수 발행했던 사고 방지.)
"""
import json
import os
import subprocess
import sys
import re
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from common import BASE_DIR, PROFILE_DIR, LOGS_DIR, POSTS_DIR, load_config, log

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")
MOD_KEY = Keys.COMMAND if IS_MAC else Keys.CONTROL


def _set_clip(text):
    """OS 클립보드에 텍스트를 올린다(맥: pbcopy / 윈도우: PowerShell / 리눅스: xclip).

    윈도우는 stdin 인코딩 문제를 피하려 UTF-8 임시파일을 PowerShell 로 읽어 올린다.
    """
    try:
        if IS_MAC:
            return subprocess.run(["pbcopy"], input=text, text=True).returncode == 0
        if IS_WIN:
            import tempfile
            with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                             encoding="utf-8") as f:
                f.write(text)
                tmp = f.name
            try:
                subprocess.run(["powershell", "-NoProfile", "-Command",
                                f"Set-Clipboard -Value (Get-Content -Raw -Encoding UTF8 "
                                f"-LiteralPath '{tmp}')"], check=False)
            finally:
                os.remove(tmp)
            return True
        return subprocess.run(["xclip", "-selection", "clipboard"],
                              input=text, text=True).returncode == 0
    except Exception:
        return False


def _send_text(driver, text):
    """한 줄을 입력한다.

    맥의 ChromeDriver 는 BMP 밖 문자(이모지)를 send_keys 로 보낼 때 서로게이트 쌍이
    깨져 두부 글자로 들어간다. 그런 줄만 클립보드 붙여넣기로 우회한다.
    (윈도우는 send_keys 로 정상 입력되므로 기존 경로를 그대로 쓴다.)
    """
    if IS_MAC and any(ord(ch) > 0xFFFF for ch in text):
        r = subprocess.run(["pbcopy"], input=text, text=True)
        if r.returncode == 0:
            ActionChains(driver).key_down(MOD_KEY).send_keys("v")\
                .key_up(MOD_KEY).perform()
            time.sleep(0.3)
            return
        log("pbcopy 실패 → send_keys 로 대체(이모지 깨질 수 있음).")
    ActionChains(driver).send_keys(text).perform()

# 한국어/영어 UI 모두 대응하기 위한 라벨 후보
CREATE_LABELS = ["새로운 게시물 만들기", "새로운 게시물", "새 게시물", "만들기",
                 "New post", "Create"]
POST_MENU_LABELS = ["게시물", "Post"]
NEXT_LABELS = ["다음", "Next"]
SHARE_LABELS = ["공유하기", "공유", "Share"]
SELECT_LABELS = ["컴퓨터에서 선택", "Select from computer", "Select From Computer"]
CAPTION_LABELS = ["문구 입력...", "문구 입력", "Write a caption...", "Write a caption"]


def build_driver(headless):
    opts = Options()
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--window-size=1280,1000")
    opts.add_argument("--lang=ko-KR")
    opts.set_capability("unhandledPromptBehavior", "accept")
    if headless:
        opts.add_argument("--headless=new")
    driver = webdriver.Chrome(options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
    )
    return driver


def shot(driver, name):
    path = os.path.join(LOGS_DIR, f"{datetime.now():%Y%m%d_%H%M%S}_{name}.png")
    try:
        driver.save_screenshot(path)
        log(f"스크린샷 저장: {path}")
    except Exception as e:
        log(f"스크린샷 실패: {e}")


def _click_by_labels(driver, labels, timeout=8):
    """aria-label 또는 보이는 텍스트가 labels 중 하나와 일치하는 클릭요소를 누른다."""
    end = time.time() + timeout
    while time.time() < end:
        for lb in labels:
            xpaths = [
                f"//*[@aria-label='{lb}']",
                f"//*[@role='button'][normalize-space(.)='{lb}']",
                f"//button[normalize-space(.)='{lb}']",
                f"//div[@role='button'][.//text()[normalize-space()='{lb}']]",
                f"//*[normalize-space(text())='{lb}']",
            ]
            for xp in xpaths:
                try:
                    el = driver.find_element(By.XPATH, xp)
                    if el.is_displayed():
                        try:
                            el.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", el)
                        return True
                except Exception:
                    continue
        time.sleep(0.5)
    return False


def _find_file_input(driver, timeout=8):
    end = time.time() + timeout
    while time.time() < end:
        for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
            accept = (inp.get_attribute("accept") or "").lower()
            if accept == "" or "image" in accept or "jpeg" in accept or "png" in accept:
                return inp
        time.sleep(0.5)
    return None


def _dialog(driver):
    try:
        return driver.find_element(By.CSS_SELECTOR, "div[role='dialog']")
    except Exception:
        return driver


def _click_dialog_button(driver, labels):
    """다이얼로그 우상단의 '다음'/'공유하기' 같은 버튼을 정확히 눌러 진행한다.

    다이얼로그 범위 안에서 텍스트가 정확히 일치하는 클릭요소를 찾아 스크롤 후
    JS 클릭한다. (단순 라벨 클릭이 부모 div 를 눌러 동작 안 하는 문제 해결)
    """
    scope = _dialog(driver)
    for lb in labels:
        xpaths = [
            f".//div[@role='button'][normalize-space(.)='{lb}']",
            f".//button[normalize-space(.)='{lb}']",
            f".//*[@role='button'][normalize-space(.)='{lb}']",
            f".//div[normalize-space(text())='{lb}']",
        ]
        for xp in xpaths:
            try:
                for el in scope.find_elements(By.XPATH, xp):
                    if el.is_displayed():
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", el)
                        time.sleep(0.2)
                        driver.execute_script("arguments[0].click();", el)
                        return True
            except Exception:
                continue
    return False


def _click_next(driver):
    return _click_dialog_button(driver, NEXT_LABELS)


def _caption_box(driver):
    """캡션 입력란(있으면 요소, 없으면 None). 캡션 화면 도달 판별에도 사용.

    인스타 캡션란은 aria-label 이 자주 바뀌고 contenteditable div 라서,
    ① aria-label 부분일치 → ② 다이얼로그 내 contenteditable/textarea 폴백 순으로 찾는다.
    """
    # ① aria-label 부분일치 (문구/caption)
    for kw in ("문구", "caption", "Caption"):
        try:
            for el in driver.find_elements(
                    By.XPATH, f"//*[contains(@aria-label,'{kw}')]"):
                if el.is_displayed():
                    return el
        except Exception:
            continue
    # ② 다이얼로그 내 편집 가능한 영역 폴백 (필터/자르기 화면엔 없음 → 캡션화면 신호)
    scope = _dialog(driver)
    for sel in ("div[contenteditable='true']", "textarea",
                "div[role='textbox']"):
        try:
            for el in scope.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    return el
        except Exception:
            continue
    return None


def post_carousel(data, dry_run=None):
    cfg = load_config()
    ig = cfg.get("instagram", {})
    if dry_run is None:
        dry_run = ig.get("dry_run", True)
    headless = ig.get("headless", False)

    images = data.get("images") or []
    images = [p for p in images if os.path.exists(p)]
    if not images:
        raise RuntimeError("게시할 카드 PNG 가 없습니다. 먼저 gamma_make.py 를 실행하세요.")
    # 인스타 캐러셀은 최대 10장
    images = images[:10]

    caption = _build_caption(data, cfg)

    driver = build_driver(headless)
    try:
        driver.get("https://www.instagram.com/")
        time.sleep(6)
        # 쿠키/저장 팝업 닫기 (있으면)
        _click_by_labels(driver, ["나중에 하기", "Not Now", "닫기", "Close",
                                  "허용", "Allow"], timeout=3)

        if "/accounts/login" in driver.current_url or "login" in driver.current_url:
            shot(driver, "not_logged_in")
            raise RuntimeError(
                "인스타그램 로그인 세션이 없습니다. login_setup_insta.py 를 실행해 "
                "한 번 로그인해 주세요.")

        # 1) 새 게시물 만들기
        if not _click_by_labels(driver, CREATE_LABELS, timeout=12):
            shot(driver, "no_create_button")
            raise RuntimeError("'새로운 게시물' 버튼을 찾지 못했습니다. 스크린샷 확인.")
        time.sleep(1.5)
        # 일부 UI 는 만들기 클릭 후 '게시물' 하위 메뉴가 뜬다
        _click_by_labels(driver, POST_MENU_LABELS, timeout=3)
        time.sleep(1.5)

        # 2) 파일 선택 (input 에 여러 경로 한번에 전달 → 캐러셀)
        inp = _find_file_input(driver, timeout=8)
        if inp is None:
            # '컴퓨터에서 선택' 클릭이 input 을 노출시키기도 함
            _click_by_labels(driver, SELECT_LABELS, timeout=4)
            inp = _find_file_input(driver, timeout=6)
        if inp is None:
            shot(driver, "no_file_input")
            raise RuntimeError("파일 입력(input[type=file])을 찾지 못했습니다.")
        inp.send_keys("\n".join(os.path.abspath(p) for p in images))
        log(f"카드 {len(images)}장 업로드 시작...")
        time.sleep(9)  # 캐러셀 7장 처리 대기
        shot(driver, "after_upload")

        # 3) 크롭 → (편집) → 캡션 화면까지 '다음'을 눌러 전진.
        #    화면 수가 가변일 수 있어, 캡션 입력란이 보일 때까지 최대 4번 시도하며
        #    매번 '실제로 넘어갔는지'를 캡션란 등장으로 검증한다.
        advanced = False
        for step in range(1, 5):
            if _caption_box(driver) is not None:
                advanced = True
                break
            if not _click_next(driver):
                shot(driver, f"no_next_{step}")
                log(f"'다음' 버튼을 찾지 못함(step {step}).")
                break
            # 화면 전환 대기 (최대 6초, 캡션란 또는 새 '다음' 버튼 안정화)
            for _ in range(12):
                time.sleep(0.5)
                if _caption_box(driver) is not None:
                    break
            log(f"'다음' 클릭 {step}회 진행.")
        if not advanced and _caption_box(driver) is None:
            shot(driver, "nav_stuck")
            raise RuntimeError("캡션 화면까지 진행하지 못했습니다(스크린샷 nav_stuck 확인).")
        shot(driver, "caption_screen")

        # 4) 캡션 입력
        if not _type_caption(driver, caption):
            shot(driver, "no_caption_box")
            log("캡션 입력란을 찾지 못해 캡션 없이 진행 가능(스크린샷 확인).")
        time.sleep(1)
        shot(driver, "before_share")

        if dry_run:
            log("DRY_RUN: '공유하기' 직전에서 멈춤. logs/ 의 caption_screen / "
                "before_share 스크린샷에서 카드·캡션을 확인하세요. 문제 없으면 "
                "스케줄 실행(run_weekly.py)이 실제 게시합니다.")
            return {"status": "dry_run", "images": len(images)}

        # 6) 공유하기 (다음 버튼과 동일한 JS 클릭 방식)
        _settle_caption_before_share(driver, caption)
        if not _click_dialog_button(driver, SHARE_LABELS):
            shot(driver, "no_share")
            raise RuntimeError("'공유하기' 버튼을 찾지 못했습니다.")
        # ★ 공유는 7장 업로드라 시간이 걸린다. '공유 중입니다' 동안 브라우저를 닫으면
        #    게시가 중단되므로, '공유되었습니다' 성공 문구가 뜰 때까지 최대 100초 대기.
        ok = False
        for _ in range(66):
            time.sleep(1.5)
            src = driver.page_source or ""
            sharing = ("공유 중" in src) or ("업로드 중" in src)
            if not sharing and ("공유되었습니다" in src or "게시물이 공유" in src):
                ok = True
                break
        time.sleep(3)  # 성공 화면 안정화
        shot(driver, "after_share")
        if not ok:
            log("공유 완료 문구를 명확히 감지하지 못했습니다. 프로필에서 확인하세요.")
            return {"status": "shared_unconfirmed", "images": len(images)}
        log("게시 완료(추정). 스크린샷으로 결과를 확인하세요.")
        return {"status": "published", "images": len(images)}

    except Exception as e:
        shot(driver, "error")
        log(f"게시 중 오류: {e}")
        raise
    finally:
        driver.quit()


def _norm_caption(s):
    """비교용 정규화 — 입력칸은 줄바꿈·공백을 살짝 다르게 돌려준다."""
    return re.sub(r"\s+", " ", s or "").strip()


def _refill_caption(driver, box, caption):
    """입력칸을 비우고 캡션을 다시 넣는다(타이핑이 먹지 않았을 때의 복구 경로).

    contenteditable 이라 Cmd+A 가 먹지 않으므로 Selection API 로 전체 선택 후
    BACK_SPACE 로 비운다. 본문은 execCommand, 줄바꿈만 ENTER 로 넣는다
    (execCommand 는 '\n' 을 버리고, 전부 타이핑하면 '@'·'#' 자동완성이 끼어든다)."""
    ActionChains(driver).move_to_element(box).pause(0.3).click().perform()
    time.sleep(0.5)
    driver.execute_script(
        "const el=arguments[0]; el.focus();"
        "const r=document.createRange(); r.selectNodeContents(el);"
        "const s=window.getSelection(); s.removeAllRanges(); s.addRange(r);", box)
    time.sleep(0.3)
    ActionChains(driver).send_keys(Keys.BACK_SPACE).perform()
    time.sleep(0.8)
    for i, para in enumerate(caption.split("\n")):
        if i:
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            time.sleep(0.2)
        if para:
            driver.execute_script(
                "arguments[0].focus(); document.execCommand('insertText', false, arguments[1]);",
                box, para)
            time.sleep(0.3)
    time.sleep(0.8)


def _type_caption(driver, caption):
    """캡션을 입력하고 '실제로 들어갔는지' 확인한다.

    예전에 입력이 조용히 실패해 캡션 없는 게시물이 30건 넘게 쌓인 적이 있다.
    그래서 입력 후 입력칸 내용을 대조하고, 어긋나면 한 번 더 채워 넣는다."""
    box = _caption_box(driver)
    if box is None:
        return False
    try:
        ActionChains(driver).move_to_element(box).click().perform()
        time.sleep(0.4)
        # 줄바꿈 포함 캡션을 안전하게 입력 (줄바꿈은 SHIFT+ENTER 로 별도 전송)
        lines = caption.split("\n")
        for i, line in enumerate(lines):
            if line:
                _send_text(driver, line)
            if i < len(lines) - 1:
                ActionChains(driver).key_down(Keys.SHIFT)\
                    .send_keys(Keys.ENTER).key_up(Keys.SHIFT).perform()
            time.sleep(0.02)
    except Exception:
        return False
    # 입력 검증 — 비어 있거나 내용이 다르면 다른 방식으로 한 번 더 시도한다.
    for attempt in (1, 2):
        try:
            got = box.text
        except Exception:
            return False
        if _norm_caption(got) == _norm_caption(caption):
            return True
        log(f"캡션 입력 검증 실패({len(got)}자/{len(caption)}자) → 재입력 {attempt}회차")
        try:
            _refill_caption(driver, box, caption)
        except Exception as e:
            log(f"캡션 재입력 중 오류: {type(e).__name__}")
            return False
    ok = _norm_caption(box.text) == _norm_caption(caption)
    if not ok:
        log("⚠ 캡션이 끝내 들어가지 않았습니다 — 게시 후 ig_caption_boost 로 보완 필요")
    return ok


def _fill_empty_caption(driver, box, caption):
    """빈 캡션칸에 caption 을 넣는다. 줄바꿈은 ENTER, 본문은 execCommand.

    빈 편집기에 스크립트로만 글을 넣으면 화면엔 보여도 저장되지 않았다(9/15~9/27 5건).
    앞뒤로 실제 키 입력을 한 번씩 넣어 편집기 상태를 화면과 맞춘다 — 이 방식으로
    2026-09-28 빈 캡션 8건을 복원했고 8건 모두 다시 열어 저장을 확인했다."""
    ActionChains(driver).move_to_element(box).pause(0.4).click().perform()
    time.sleep(0.6)
    ActionChains(driver).send_keys(" ").pause(0.3).send_keys(Keys.BACK_SPACE).perform()
    time.sleep(0.6)
    for i, para in enumerate(caption.split("\n")):
        if i:
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            time.sleep(0.25)
        if para:
            driver.execute_script(
                "arguments[0].focus(); document.execCommand('insertText', false, arguments[1]);",
                box, para)
            time.sleep(0.35)
    ActionChains(driver).send_keys(" ").pause(0.3).send_keys(Keys.BACK_SPACE).perform()
    time.sleep(1.0)


def _saved_caption_ok(driver, code, caption):
    """게시물 편집창을 다시 열어 저장된 캡션이 의도한 내용인지 확인한다(읽기만)."""
    try:
        driver.get(f"https://www.instagram.com/p/{code}/")
        time.sleep(4)
        if not _click_dialog_button(driver, ["옵션 더 보기", "옵션", "More options"]):
            return False
        time.sleep(1.5)
        if not _click_dialog_button(driver, ["수정", "Edit"]):
            return False
        time.sleep(4)
        boxes = [b for b in driver.find_elements(
            By.CSS_SELECTOR, "div[role='textbox'][contenteditable='true']") if b.is_displayed()]
        ok = bool(boxes) and _norm_caption(boxes[0].text) == _norm_caption(caption)
        _click_dialog_button(driver, ["취소", "Cancel"])
        return ok
    except Exception:
        return False


CAPTION_LOG = os.path.join(BASE_DIR, "caption_log.json")


def _record_caption(code, caption):
    """게시물 코드와 그때 넣은 캡션을 남긴다.

    캡션이 빈 채로 올라가는 사고가 반복되는데, 나중에 무엇을 넣어야 했는지 알 길이
    없어 사람이 하나씩 찾아 채웠다. 발행 순간이 원문을 아는 유일한 시점이라 여기서
    남긴다(build_caption_fixlist.py 가 이 기록으로 복원 목록을 만든다)."""
    try:
        rec = {}
        if os.path.exists(CAPTION_LOG):
            with open(CAPTION_LOG, "r", encoding="utf-8") as f:
                rec = json.load(f)
        rec[code] = {"caption": caption, "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        with open(CAPTION_LOG, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=1)
    except Exception as e:
        log(f"캡션 기록 실패({type(e).__name__}) — 발행에는 영향 없음")


def _settle_caption_before_share(driver, caption):
    """'공유하기' 직전, 캡션칸 상태를 기록하고 편집기를 안정시킨다.

    캡션이 화면에는 있는데 게시물엔 비어 올라가는 사고가 반복된다. 유력한 경로 둘:
      - 캡션 끝이 '@smu_ds_official' 이라 멘션 자동완성이 열린 채 공유를 누른다.
      - 붙여넣기·스크립트 입력만으로는 편집기 내부 상태가 화면과 어긋난다
        (복원 경로가 앞뒤로 실제 키를 한 번씩 넣어 해결한 것과 같은 문제).
    그래서 ESC 로 자동완성을 닫고, 실제 키 입력을 한 번 넣어 상태를 맞춘 뒤,
    공유 직전 길이를 로그에 남긴다(원인 확인용)."""
    box = _caption_box(driver)
    if box is None:
        log("공유 직전 점검: 캡션칸을 찾지 못함")
        return
    try:
        before = box.text
        popups = driver.find_elements(
            By.CSS_SELECTOR, "div[role='listbox'], ul[role='listbox'], div[role='presentation'] li")
        open_popup = any(p.is_displayed() for p in popups)
        log(f"공유 직전 점검: 캡션 {len(before)}자, 자동완성 {'열림' if open_popup else '닫힘'}")
        if open_popup:
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
        # 실제 키 입력 한 번으로 편집기 상태를 화면과 맞춘다(복원 경로에서 검증된 방법).
        ActionChains(driver).move_to_element(box).pause(0.3).click().perform()
        time.sleep(0.4)
        ActionChains(driver).send_keys(" ").pause(0.3).send_keys(Keys.BACK_SPACE).perform()
        time.sleep(0.6)
        after = box.text
        if _norm_caption(after) != _norm_caption(caption):
            log(f"⚠ 공유 직전 캡션이 달라짐({len(before)}자 → {len(after)}자)")
        shot(driver, "reel_caption_settled")
    except Exception as e:
        log(f"공유 직전 점검 중 오류({type(e).__name__}) — 게시는 계속한다")


def _fix_caption_after_publish(driver, username, caption):
    """게시 직후 실제 캡션을 확인하고, 비어 있으면 편집으로 채운다.

    공유 화면에서 캡션 입력이 확인됐는데도 게시물에는 캡션이 없는 사례가 반복됐다
    (2026-09-12 카드뉴스 릴). 그래서 '게시된 결과'를 한 번 더 보고 비었을 때만 채운다.
    이미 캡션이 있으면 손대지 않는다(사용자가 직접 쓴 내용을 덮지 않기 위해)."""
    try:
        driver.get(f"https://www.instagram.com/{username}/")
        time.sleep(5)
        links = driver.find_elements(By.CSS_SELECTOR, "main a[href*='/p/'], main a[href*='/reel/']")
        m = re.search(r"/(?:p|reel)/([A-Za-z0-9_-]+)/", links[0].get_attribute("href") or "") if links else None
        if not m:
            log("게시 후 캡션 확인 생략(최근 게시물을 찾지 못함)")
            return
        code = m.group(1)
        _record_caption(code, caption)
        driver.get(f"https://www.instagram.com/p/{code}/")
        time.sleep(4)
        if not _click_dialog_button(driver, ["옵션 더 보기", "옵션", "More options"]):
            return
        time.sleep(1.5)
        if not _click_dialog_button(driver, ["수정", "Edit"]):
            return
        time.sleep(4)
        boxes = [b for b in driver.find_elements(
            By.CSS_SELECTOR, "div[role='textbox'][contenteditable='true']") if b.is_displayed()]
        if not boxes:
            return
        box = boxes[0]
        if box.text.strip():
            log("게시 후 캡션 확인: 정상")
            _click_dialog_button(driver, ["취소", "Cancel"])
            return
        log(f"⚠ 게시된 캡션이 비어 있음({code}) → 편집으로 채웁니다")
        _fill_empty_caption(driver, box, caption)
        if _norm_caption(box.text) == _norm_caption(caption):
            _click_dialog_button(driver, ["완료", "Done"])
            time.sleep(5)
            # 저장됐는지 편집창을 다시 열어 확인한다. 예전엔 '완료'만 누르고 성공으로 기록해,
            # 실제로는 저장되지 않은 5건(9/15~9/27)이 모두 '보완 완료'로 남았다.
            if _saved_caption_ok(driver, code, caption):
                log(f"게시 후 캡션 보완 완료(저장 확인됨, {code})")
            else:
                log(f"⚠ 게시 후 캡션 보완 저장 안 됨({code}) — 캡션이 빈 채로 게시돼 있습니다")
        else:
            _click_dialog_button(driver, ["취소", "Cancel"])
            log("게시 후 캡션 보완 실패(저장하지 않음) — ig_caption_boost 로 보완하세요")
    except Exception as e:
        log(f"게시 후 캡션 확인 건너뜀: {type(e).__name__}")


def _caption_body(data, cfg):
    """피드에 보이는 본문(훅·요약) + 팔로우 CTA."""
    body = (data.get("caption", "") or "").strip()
    # 캡션 끝에 팔로우 유도(도달·재방문↑). config.instagram.follow_cta 로 문구 지정.
    ig = cfg.get("instagram", {})
    # 저장(북마크) 유도 — 인스타에서 저장은 팔로우보다 강한 도달 신호라 CTA 앞에 둔다.
    save = (ig.get("save_cta") or "").strip()
    if save and save not in body:
        body = (body + "\n\n" + save).strip()
    cta = (ig.get("follow_cta") or "").strip()
    if cta and cta not in body:
        body = (body + "\n\n" + cta).strip()
    return body


def _caption_extras(data, cfg):
    """출처·해시태그·음악크레딧 등 '긴 부속 내용'."""
    parts = []
    sources = data.get("sources") or []
    if sources and cfg.get("instagram", {}).get("include_sources", True):
        parts.append("📰 참고 뉴스 출처")
        for s in sources[:6]:
            parts.append(f"· [{s.get('published_str','')}] {s.get('title','')}")
    tags = data.get("hashtags") or []
    if tags:
        if parts:
            parts.append("")
        parts.append(" ".join("#" + t for t in tags))
    # 릴 배경음악 출처(CC-BY 등 라이선스 표기 필수)
    reel = cfg.get("reel", {})
    if reel.get("enabled") and reel.get("audio_credit"):
        parts.append("")
        parts.append(reel["audio_credit"])
    return "\n".join(parts).strip()


def _first_comment_text(data, cfg):
    """첫 댓글 = 질문형 참여 유도 한 줄 + (출처·해시태그).

    댓글은 인스타 알고리즘의 참여 신호라, 맨 앞에 답하기 쉬운 질문을 던져 댓글을
    유도한다. 문구는 config.instagram.first_comment_question 으로 바꿀 수 있다.
    """
    q = (cfg.get("instagram", {}).get("first_comment_question") or
         "여러분 지역은 안전한가요? 겪은 일이나 궁금한 점을 댓글로 남겨주세요! 👇").strip()
    # 유튜브로 넘기는 한 줄(채널 간 순환). 인스타 댓글의 링크는 클릭되지 않으므로 채널명으로 안내.
    yt = (cfg.get("instagram", {}).get("youtube_cta") or "").strip()
    extras = _caption_extras(data, cfg)
    return "\n\n".join(p for p in (q, yt, extras) if p).strip()


def _build_caption(data, cfg):
    """캡션 전체(본문+부속). first_comment 를 쓰면 부속은 댓글로 분리된다."""
    body, extras = _caption_body(data, cfg), _caption_extras(data, cfg)
    if cfg.get("instagram", {}).get("first_comment", False):
        return body          # 부속은 첫 댓글로
    return "\n\n".join(p for p in (body, extras) if p).strip()


def _post_first_comment(driver, username, text, dry=False):
    """방금 올린 릴(프로필 최신 릴)에 첫 댓글을 단다.

    릴은 캡션이 잘 안 보이므로 출처·해시태그 같은 긴 내용을 첫 댓글로 옮긴다.
    줄바꿈·이모지가 안전하도록 클립보드 붙여넣기를 쓴다.
    dry=True 면 '게시' 직전까지만 하고 실제로 달지 않는다.
    """
    if not (username and text.strip()):
        return False
    try:
        driver.get(f"https://www.instagram.com/{username}/reels/")
        time.sleep(6)
        links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/reel/']")
        if not links:
            shot(driver, "comment_no_reel")
            log("첫 댓글: 프로필에서 릴을 찾지 못했습니다.")
            return False
        links[0].click()
        time.sleep(5)

        box = None
        for sel in ("textarea[aria-label*='댓글']", "textarea[placeholder*='댓글']",
                    "div[contenteditable='true'][aria-label*='댓글']",
                    "textarea[aria-label*='omment']",
                    "div[contenteditable='true'][aria-label*='omment']"):
            els = [e for e in driver.find_elements(By.CSS_SELECTOR, sel) if e.is_displayed()]
            if els:
                box = els[0]
                break
        if box is None:
            shot(driver, "comment_no_box")
            log("첫 댓글: 댓글 입력란을 찾지 못했습니다.")
            return False

        box.click()
        time.sleep(0.6)
        # 클립보드 붙여넣기(줄바꿈·이모지 보존). 엔터는 즉시 게시되므로 쓰지 않는다.
        _set_clip(text)   # 맥/윈도우/리눅스 공용
        ActionChains(driver).key_down(MOD_KEY).send_keys("v").key_up(MOD_KEY).perform()
        time.sleep(1.5)
        shot(driver, "comment_before_post")

        if dry:
            log("첫 댓글(dry): 입력까지만 하고 게시하지 않음.")
            return True

        if not _click_dialog_button(driver, ["게시", "Post"]):
            log("첫 댓글: '게시' 버튼을 찾지 못했습니다.")
            return False
        time.sleep(3)
        shot(driver, "comment_after_post")
        log("첫 댓글 등록 완료.")
        return True
    except Exception as e:
        shot(driver, "comment_error")
        log(f"첫 댓글 실패: {type(e).__name__}")
        return False


def _try_enable_ai_label(driver):
    """게시 전 '고급 설정 → AI 레이블' 토글을 켠다(best-effort, 실패해도 게시는 계속).

    Meta는 사실적 AI 콘텐츠(예: AI 아나운서)에 레이블을 요구한다. UI가 자주 바뀌므로
    여러 문구/스위치를 시도하고, 못 찾으면 로그만 남기고 넘어간다(게시 흐름 보호)."""
    try:
        _click_by_labels(driver, ["고급 설정", "고급설정", "Advanced settings"], timeout=3)
        time.sleep(1.2)
        for kw in ("AI 레이블", "AI label", "AI로 생성", "인공지능"):
            for el in [e for e in driver.find_elements(By.XPATH, f"//*[contains(text(),'{kw}')]")
                       if e.is_displayed()]:
                try:
                    sw = el.find_element(
                        By.XPATH, "./ancestor::*[.//*[@role='switch' or @role='checkbox']][1]"
                        "//*[@role='switch' or @role='checkbox']")
                    if (sw.get_attribute("aria-checked") or "").lower() != "true":
                        sw.click()
                        time.sleep(0.8)
                    log("AI 레이블 토글 ON(시도).")
                    shot(driver, "reel_ai_label")
                    return True
                except Exception:
                    continue
        log("AI 레이블 토글을 찾지 못함 → 게시 후 수동 확인 필요.")
    except Exception as e:
        log(f"AI 레이블 설정 건너뜀: {type(e).__name__}")
    return False


JS_CROP_BUTTON = """
const svgs = [...document.querySelectorAll('div[role=dialog] svg[aria-label]')];
const hit = svgs.find(v => /자르기 선택|Select crop|자르기|crop/i.test(v.getAttribute('aria-label')));
if (!hit) return false;
(hit.closest('button,[role=button]') || hit.parentElement).click();
return hit.getAttribute('aria-label');
"""
JS_CROP_ORIGINAL = """
const els = [...document.querySelectorAll('div[role=dialog] span, div[role=dialog] div')];
const opt = els.find(e => e.childElementCount <= 1 && /^(원본|Original)$/.test((e.innerText || '').trim()));
if (!opt) return false;
(opt.closest('button,[role=button]') || opt).click();
return true;
"""


def _select_original_crop(driver):
    """자르기 화면에서 비율 메뉴를 열고 '원본'을 고른다. 성공 여부를 돌려준다."""
    try:
        label = driver.execute_script(JS_CROP_BUTTON)
        if not label:
            log("자르기 비율 버튼을 찾지 못함 → 기본 비율로 진행")
            return False
        time.sleep(1.2)
        if not driver.execute_script(JS_CROP_ORIGINAL):
            log("자르기 메뉴에 '원본' 없음 → 기본 비율로 진행")
            shot(driver, "reel_crop_menu")
            return False
        time.sleep(1.5)
        shot(driver, "reel_crop_original")
        log("자르기 비율: 원본(9:16) 선택")
        return True
    except Exception as e:
        log(f"자르기 비율 선택 실패({type(e).__name__}) → 기본 비율로 진행")
        return False


def post_reel(data, dry_run=None):
    """카드 슬라이드쇼 영상(data['reel'])을 인스타 릴로 게시한다. (음악은 영상에 포함됨)

    캐러셀과 다른 점: 단일 영상 업로드, '이 동영상은 릴로 공유됩니다' 확인 팝업 처리,
    영상 처리 대기가 더 길다. 나머지(네비게이션·캡션·공유)는 캐러셀과 동일 헬퍼 재사용.
    수동 실행은 항상 dry_run. 실제 게시는 run_weekly 에서만.
    """
    cfg = load_config()
    ig = cfg.get("instagram", {})
    if dry_run is None:
        dry_run = ig.get("dry_run", True)
    headless = ig.get("headless", False)

    video = data.get("reel")
    if not video or not os.path.exists(video):
        raise RuntimeError("게시할 릴 영상이 없습니다. 먼저 make_reel 을 실행하세요.")
    caption = _build_caption(data, cfg)

    driver = build_driver(headless)
    try:
        driver.get("https://www.instagram.com/")
        time.sleep(6)
        _click_by_labels(driver, ["나중에 하기", "Not Now", "닫기", "Close",
                                  "허용", "Allow"], timeout=3)
        if "/accounts/login" in driver.current_url or "login" in driver.current_url:
            shot(driver, "reel_not_logged_in")
            raise RuntimeError("인스타 로그인 세션이 없습니다. ig_manual_login.py 실행.")

        # 1) 새 게시물 만들기
        # 감독 모드(data['supervised']): '새 게시물'이 안 보이면 CAPTCHA 등 챌린지일 수
        # 있으니, 사람이 브라우저 창에서 직접 해결하도록 최대 3분 대기하며 재시도한다.
        # (자동/스케줄 실행에서는 supervised=False → 기존처럼 즉시 실패.)
        if not _click_by_labels(driver, CREATE_LABELS, timeout=12):
            if data.get("supervised"):
                shot(driver, "reel_challenge")
                log("⚠️ '새 게시물'을 찾지 못했습니다(CAPTCHA/보안확인일 수 있음).")
                log("   → 열린 브라우저 창에서 직접 인증을 완료해 주세요. 최대 3분 대기하며 재시도합니다...")
                clicked = False
                for i in range(18):
                    time.sleep(10)
                    if _click_by_labels(driver, CREATE_LABELS, timeout=5):
                        clicked = True
                        log(f"   인증 통과 감지({(i+1)*10}s) → 게시 계속.")
                        break
                if not clicked:
                    shot(driver, "reel_no_create")
                    raise RuntimeError("3분 내 인증이 완료되지 않았습니다(수동 업로드 권장).")
            else:
                shot(driver, "reel_no_create")
                raise RuntimeError("'새로운 게시물' 버튼을 찾지 못했습니다.")
        time.sleep(1.5)
        _click_by_labels(driver, POST_MENU_LABELS, timeout=3)
        time.sleep(1.5)

        # 2) 영상 파일 선택
        inp = _find_file_input(driver, timeout=8)
        if inp is None:
            _click_by_labels(driver, SELECT_LABELS, timeout=4)
            inp = _find_file_input(driver, timeout=6)
        if inp is None:
            shot(driver, "reel_no_file_input")
            raise RuntimeError("파일 입력(input[type=file])을 찾지 못했습니다.")
        inp.send_keys(os.path.abspath(video))
        log("릴 영상 업로드 시작...")
        time.sleep(8)
        # 2-1) '이 동영상은 릴로 공유됩니다' 확인 팝업(있으면)
        _click_by_labels(driver, ["확인", "OK"], timeout=6)
        time.sleep(4)
        shot(driver, "reel_after_upload")
        # 2-2) 자르기 비율을 '원본'(9:16)으로 — 웹 업로드는 기본이 정사각형(1:1)이라 카드 위아래의
        #      실사 배경이 잘려 나갔다(9/30 릴: 배경 영상이 거의 안 보임). 실패해도 게시는 계속.
        _select_original_crop(driver)

        # 3) 캡션 화면까지 '다음' 전진 (영상 처리 대기 포함, 최대 5단계)
        advanced = False
        for step in range(1, 6):
            if _caption_box(driver) is not None:
                advanced = True
                break
            if not _click_next(driver):
                time.sleep(3)  # 아직 처리 중일 수 있으니 잠깐 더 대기
                if not _click_next(driver):
                    shot(driver, f"reel_no_next_{step}")
                    break
            for _ in range(20):
                time.sleep(0.5)
                if _caption_box(driver) is not None:
                    break
            log(f"릴 '다음' 클릭 {step}회 진행.")
        if not advanced and _caption_box(driver) is None:
            shot(driver, "reel_nav_stuck")
            raise RuntimeError("릴 캡션 화면까지 진행하지 못했습니다.")
        shot(driver, "reel_caption_screen")

        # 4) 캡션 입력
        if not _type_caption(driver, caption):
            shot(driver, "reel_caption_failed")
            log("⚠ 릴 캡션 입력 실패 — 캡션 없이 게시됩니다. 게시 후 확인하세요.")
        time.sleep(1)
        # 4-1) AI 레이블(사실적 AI 콘텐츠) — 아나운서 릴 등. best-effort(실패해도 게시 진행).
        if data.get("ai_label"):
            _try_enable_ai_label(driver)
        shot(driver, "reel_before_share")

        if dry_run:
            log("DRY_RUN(릴): '공유하기' 직전에서 멈춤. logs/ 스크린샷 확인.")
            return {"status": "dry_run"}

        # 5) 공유하기 (릴은 처리 시간이 더 길다 → 최대 ~150초 대기)
        _settle_caption_before_share(driver, caption)
        if not _click_dialog_button(driver, SHARE_LABELS):
            shot(driver, "reel_no_share")
            raise RuntimeError("'공유하기' 버튼을 찾지 못했습니다.")
        ok = False
        for _ in range(100):
            time.sleep(1.5)
            src = driver.page_source or ""
            # '공유 중'/'업로드 중' 스피너가 떠 있는 동안은 완료로 보지 않는다
            # (느슨한 영어 매칭이 페이지 곳곳 텍스트에 오탐지되던 버그 수정).
            sharing = ("공유 중" in src) or ("업로드 중" in src)
            if not sharing and ("공유되었습니다" in src or "게시물이 공유" in src
                                or "릴이 공유" in src):
                ok = True
                break
        time.sleep(3)
        shot(driver, "reel_after_share")
        if not ok:
            log("릴 공유 완료 문구를 감지하지 못했습니다. 프로필에서 확인하세요.")
            return {"status": "shared_unconfirmed"}
        log("릴 게시 완료(추정).")

        # 게시 결과의 캡션을 확인하고 비어 있으면 채운다(캡션 누락 재발 방지)
        _fix_caption_after_publish(driver, ig.get("username", ""), caption)

        # 릴은 캡션 노출이 약해 질문형 참여유도 + 출처·해시태그를 첫 댓글로 옮긴다
        if ig.get("first_comment", False):
            _post_first_comment(driver, ig.get("username", ""),
                                _first_comment_text(data, cfg))
        return {"status": "published"}

    except Exception as e:
        shot(driver, "reel_error")
        log(f"릴 게시 중 오류: {e}")
        raise
    finally:
        driver.quit()


if __name__ == "__main__":
    import sys
    # 수동 실행은 무조건 dry_run (안전장치)
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        files = sorted(f for f in os.listdir(POSTS_DIR) if f.endswith(".json"))
        if not files:
            raise SystemExit("먼저 generate_cards.py → gamma_make.py 를 실행하세요.")
        path = os.path.join(POSTS_DIR, files[-1])
    with open(path, "r", encoding="utf-8") as f:
        post_carousel(json.load(f), dry_run=True)
