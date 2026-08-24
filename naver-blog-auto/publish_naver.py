"""저장된 Chrome 프로필로 네이버 블로그 스마트에디터 ONE 에 글을 발행한다.

주의: 네이버 에디터는 수시로 구조/클래스명이 바뀐다. 셀렉터가 안 맞으면
logs/ 에 스크린샷(.png)을 남기니 그걸 보고 SELECTORS 를 수정하면 된다.
config.publish.dry_run=true 면 '발행' 직전에 멈추고 스크린샷만 남긴다.
"""
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from common import PROFILE_DIR, LOGS_DIR, load_config, log
from make_banner import make_banner
from gamma_image import make_gamma_image

IS_MAC = sys.platform == "darwin"
# 맥은 붙여넣기/문서끝 이동이 Command 키. 윈도우는 Control.
MOD_KEY = Keys.COMMAND if IS_MAC else Keys.CONTROL


def build_driver(headless):
    opts = Options()
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    opts.add_argument("--window-size=1280,1000")
    opts.add_argument("--lang=ko-KR")
    # 네이버가 띄우는 alert/confirm 을 자동 수락해 동작이 멈추지 않게 함
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


def click_if_present(driver, by, sel, timeout=4):
    try:
        el = WebDriverWait(driver, timeout).until(
            EC.element_to_be_clickable((by, sel)))
        el.click()
        return True
    except Exception:
        return False


def dismiss_upload_error(driver, quiet=False):
    """이미지 업로드 실패 모달('파일 전송 오류')이 떠 있으면 닫는다.

    이 모달이 남아 있으면 '발행' 버튼·카테고리 드롭다운을 가려 이후 단계가 전부
    실패한다. 실패한 이미지는 에디터가 문서에서 자동 삭제하므로, 경고만 남기고
    발행은 계속 진행한다(이미지 수집 자체가 원래 best-effort 설계).
    """
    for xp in ("//*[contains(@class,'se-popup')]//button[normalize-space(.)='확인']",
               "//button[normalize-space(.)='확인']"):
        try:
            els = driver.find_elements(By.XPATH, xp)
        except Exception:
            continue
        for el in els:
            try:
                if not el.is_displayed():
                    continue
                el.click()
                if not quiet:
                    log("⚠️ 이미지 업로드 실패 모달을 닫았습니다 "
                        "— 일부 이미지가 빠진 채 발행됩니다.")
                time.sleep(0.8)
                return True
            except Exception:
                continue
    return False


def select_category(driver, name):
    """발행 설정 레이어에서 카테고리를 이름(텍스트)으로 선택한다."""
    if not name:
        return False
    # 1) 카테고리 드롭다운 열기 (여러 후보 시도)
    opened = (
        click_if_present(driver, By.XPATH,
            "//*[contains(@class,'category')]//button", 4)
        or click_if_present(driver, By.XPATH,
            "//button[contains(@class,'selectbox_button')]", 3)
        or click_if_present(driver, By.XPATH,
            "//label[contains(.,'카테고리')]/following::button[1]", 3)
    )
    time.sleep(1)
    # 2) 이름이 일치하는 항목 클릭
    candidates = [
        f"//label[normalize-space(text())='{name}']",
        f"//span[normalize-space(text())='{name}']",
        f"//*[contains(@class,'option') or contains(@class,'item') or "
        f"contains(@class,'category')][normalize-space(.)='{name}']",
        f"//*[normalize-space(text())='{name}']",
    ]
    for xp in candidates:
        if click_if_present(driver, By.XPATH, xp, 2):
            log(f"카테고리 '{name}' 선택됨.")
            return True
    log(f"카테고리 '{name}' 자동 선택 실패 → 스크린샷 확인 후 셀렉터 조정 필요. "
        f"(드롭다운 열림={opened})")
    return False


def _set_clipboard_image_mac(image_path):
    """이미지를 macOS 클립보드에 올린다. (osascript, 필요시 sips 로 PNG 변환)"""
    src, tmp = image_path, None
    if not src.lower().endswith(".png"):
        # AppleScript 의 «class PNGf» 는 PNG 만 받으므로 먼저 변환한다.
        tmp = os.path.join(tempfile.gettempdir(), f"_clip_{os.getpid()}.png")
        r = subprocess.run(["sips", "-s", "format", "png", src, "--out", tmp],
                           capture_output=True, text=True)
        if r.returncode != 0:
            log(f"sips PNG 변환 실패: {r.stderr.strip()}")
            return False
        src = tmp
    script = f'set the clipboard to (read (POSIX file "{src}") as «class PNGf»)'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if tmp and os.path.exists(tmp):
        os.remove(tmp)
    if r.returncode != 0:
        log(f"osascript 클립보드 설정 실패: {r.stderr.strip()}")
    return r.returncode == 0


def set_clipboard_image(image_path):
    """이미지를 OS 클립보드에 올린다. (맥: osascript / 윈도우: PowerShell STA + .NET)"""
    if IS_MAC:
        return _set_clipboard_image_mac(image_path)
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        f"$img=[System.Drawing.Image]::FromFile('{image_path}');"
        "[System.Windows.Forms.Clipboard]::SetImage($img);"
    )
    r = subprocess.run(["powershell", "-sta", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True)
    return r.returncode == 0


def insert_sources_links(driver, sources):
    """본문 끝에 '참고한 뉴스 출처'를 에디터 네이티브 '링크' 도구로 삽입한다.

    각 줄(제목)을 입력 → 선택 → 링크 버튼 → URL 입력 → 적용. 단순 타이핑/붙여넣기로는
    링크가 안 걸려서 이 방식이 유일하게 안정적이다.
    """
    if not sources:
        return False
    # 본문 맨 끝으로 이동 (맥은 Cmd+↓, 윈도우는 Ctrl+End)
    _end_key = Keys.ARROW_DOWN if IS_MAC else Keys.END
    ActionChains(driver).key_down(MOD_KEY).send_keys(_end_key)\
        .key_up(MOD_KEY).perform()
    time.sleep(0.3)
    # 구분선 + 안내 머리말 (링크 아님)
    for line in ["", "─────────────", "📰 참고한 뉴스 출처 (제목 클릭 시 기사로 이동)"]:
        ActionChains(driver).send_keys(Keys.ENTER).perform()
        if line:
            _send_text(driver, line)
        time.sleep(0.1)

    done = 0
    for s in sources:
        if not s.get("link"):
            continue
        anchor = f"· [{s.get('published_str','')}] {s.get('title','')}"
        ActionChains(driver).send_keys(Keys.ENTER).perform()
        if _link_line(driver, anchor, s["link"]):
            done += 1
    log(f"출처 링크 {done}/{len(sources)}건 삽입(네이티브 링크 도구).")
    return done > 0


def _link_line(driver, anchor, url):
    """현재 줄에 anchor 텍스트를 입력하고 그 텍스트에 url 링크를 건다."""
    ActionChains(driver).send_keys(anchor).perform()
    time.sleep(0.2)
    ac = ActionChains(driver).key_down(Keys.SHIFT)
    for _ in range(len(anchor)):
        ac = ac.send_keys(Keys.ARROW_LEFT)
    ac.key_up(Keys.SHIFT).perform()
    time.sleep(0.2)
    ok = False
    if click_if_present(driver, By.CSS_SELECTOR, "[data-name='link']", 3):
        time.sleep(0.6)
        try:
            inp = WebDriverWait(driver, 4).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "input.se-custom-layer-link-input")))
            inp.click()
            inp.send_keys(url)
            time.sleep(0.3)
            inp.send_keys(Keys.ENTER)
            time.sleep(0.6)
            ok = True
        except Exception as e:
            log(f"링크 입력 실패: {e}")
    ActionChains(driver).send_keys(Keys.END).perform()
    time.sleep(0.15)
    return ok


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


def _type_text(driver, text):
    """현재 커서 위치에 여러 줄 텍스트를 입력(줄바꿈은 ENTER)."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.strip():
            _send_text(driver, line)
        if i < len(lines) - 1:
            ActionChains(driver).send_keys(Keys.ENTER).perform()
        time.sleep(0.03)


def _upload_error_present(driver):
    """'파일 전송 오류' 모달이 떠 있는지 확인한다."""
    for xp in ("//*[contains(text(),'파일 전송 오류')]",
               "//*[contains(text(),'전송하지 못했습니다')]"):
        try:
            if any(e.is_displayed() for e in driver.find_elements(By.XPATH, xp)):
                return True
        except Exception:
            continue
    return False


def _paste_image_here(driver, path, retries=2, wait=6):
    """현재 커서 위치에 이미지를 클립보드로 붙여넣는다. 업로드 실패면 재시도.

    네이버는 간헐적으로 '파일 전송 오류(알 수 없는 오류)'를 내며 이미지를 버린다.
    붙여넣기 직후 그 모달을 확인해, 뜨면 닫고 같은 이미지를 다시 붙여넣는다.
    """
    if not path or not os.path.exists(path):
        return False
    for attempt in range(1, retries + 2):
        if not set_clipboard_image(path):
            return False
        time.sleep(0.4)
        ActionChains(driver).key_down(MOD_KEY).send_keys("v")\
            .key_up(MOD_KEY).perform()
        time.sleep(wait)
        if not _upload_error_present(driver):
            if attempt > 1:
                log(f"  이미지 재시도 {attempt - 1}회 만에 성공")
            return True
        dismiss_upload_error(driver, quiet=True)
        if attempt <= retries:
            log(f"  이미지 업로드 실패 → 재시도 {attempt}/{retries}")
            time.sleep(2.0)   # 연속 업로드 제한을 피해 잠깐 쉼
    log("  이미지 업로드 재시도 모두 실패 → 이 이미지는 건너뜁니다.")
    return False


def type_structured_post(driver, data):
    """뉴스별 구조(인사 → [소제목·본문·이미지·출처링크]×N → 안전수칙 → 마무리)로 입력."""
    retries = int(load_config().get("publish", {}).get("image_retries", 2))
    body_el = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, ".se-component.se-text .se-text-paragraph")))
    ActionChains(driver).move_to_element(body_el).click().perform()
    time.sleep(0.4)

    _type_text(driver, data.get("intro", ""))
    for blk in data.get("news_blocks", []):
        ActionChains(driver).send_keys(Keys.ENTER, Keys.ENTER).perform()
        _type_text(driver, blk.get("heading", ""))
        ActionChains(driver).send_keys(Keys.ENTER).perform()
        _type_text(driver, blk.get("paragraph", ""))
        if blk.get("image"):
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            if _paste_image_here(driver, blk["image"], retries=retries):
                ActionChains(driver).send_keys(Keys.ENTER).perform()
        src = blk.get("source", {})
        # 구글뉴스 리다이렉트 대신 article_image 가 찾아낸 '실제 기사 주소'를 우선 사용
        link = (src.get("real_link") or src.get("link") or "").strip()
        if link:
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            _link_line(driver, f"📰 기사 원문: {src.get('title','')}", link)
    if data.get("tips"):
        ActionChains(driver).send_keys(Keys.ENTER, Keys.ENTER).perform()
        _type_text(driver, data["tips"])
    if data.get("outro"):
        ActionChains(driver).send_keys(Keys.ENTER, Keys.ENTER).perform()
        _type_text(driver, data["outro"])
    # 글 끝 CTA: 이웃추가 유도 + 학과 홈페이지·유튜브 링크(체류시간·교차 유입↑).
    # config.blog.cta = {"text": "...", "links": [{"label","url"}, ...]} 로 지정.
    cta = (load_config().get("blog", {}) or {}).get("cta") or {}
    cta_text = (cta.get("text") or "").strip()
    cta_links = [l for l in (cta.get("links") or []) if (l.get("url") or "").strip()]
    if cta_text or cta_links:
        ActionChains(driver).send_keys(Keys.ENTER, Keys.ENTER).perform()
        if cta_text:
            _type_text(driver, cta_text)
        for ln in cta_links:
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            _link_line(driver, ln.get("label", ln["url"]), ln["url"].strip())
    log(f"구조형 본문 입력 완료(뉴스 {len(data.get('news_blocks', []))}블록).")


def insert_image_top(driver, image_path):
    """본문 맨 위에 배너 이미지를 삽입한다.

    스마트에디터는 '사진' 버튼이 OS 파일창을 열어 자동화가 어렵다.
    대신 이미지를 클립보드에 올린 뒤 본문에 Ctrl+V 로 붙여넣어 업로드한다.
    실패해도 글 작성은 계속 진행한다.
    """
    if not image_path or not os.path.exists(image_path):
        return False
    # 본문 첫 단락에 커서 두기
    try:
        body = driver.find_element(
            By.CSS_SELECTOR, ".se-component.se-text .se-text-paragraph")
        ActionChains(driver).move_to_element(body).click().perform()
        time.sleep(0.5)
    except Exception:
        pass
    # 1) 파일 input 이 있으면 그걸로 (가장 깔끔)
    for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
        accept = (inp.get_attribute("accept") or "").lower()
        if accept and "image" not in accept:
            continue
        try:
            inp.send_keys(image_path)
            time.sleep(6)
            log("상단 배너 이미지 삽입 완료(file input).")
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            time.sleep(0.4)
            return True
        except Exception:
            continue
    # 2) 클립보드 붙여넣기
    if not set_clipboard_image(image_path):
        log("클립보드 이미지 설정 실패 → 배너 건너뜀.")
        return False
    time.sleep(0.5)
    ActionChains(driver).key_down(MOD_KEY).send_keys("v")\
        .key_up(MOD_KEY).perform()
    time.sleep(7)  # 업로드 완료 대기
    log("상단 배너 이미지 삽입 완료(클립보드 붙여넣기).")
    ActionChains(driver).send_keys(Keys.ENTER).perform()
    time.sleep(0.4)
    return True


def type_contenteditable(driver, element, text):
    """스마트에디터 contenteditable 영역에 입력한다.

    span 에 직접 send_keys 하면 'not interactable' 이 나므로,
    ActionChains 로 클릭해 포커스를 준 뒤 active element 에 키를 보낸다.
    """
    ActionChains(driver).move_to_element(element).click().perform()
    time.sleep(0.5)
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.strip():
            ActionChains(driver).send_keys(line).perform()
        if i < len(lines) - 1:
            ActionChains(driver).send_keys(Keys.ENTER).perform()
        time.sleep(0.03)


def _embed_video(driver, url, wait=7):
    """유튜브 URL 을 클립보드로 붙여넣어 스마트에디터가 동영상으로 자동 임베드하게 한다.

    네이버는 유튜브 링크를 '붙여넣기'하면 oEmbed 로 동영상 카드를 자동 삽입한다.
    (send_keys 타이핑으로는 잘 안 되고, 실제 붙여넣기 이벤트여야 인식된다.)
    """
    if not url:
        return False
    ActionChains(driver).send_keys(Keys.ENTER).perform()
    time.sleep(0.3)
    if IS_MAC:
        subprocess.run(["pbcopy"], input=url, text=True)
        ActionChains(driver).key_down(MOD_KEY).send_keys("v")\
            .key_up(MOD_KEY).perform()
    else:
        ActionChains(driver).send_keys(url).perform()
    time.sleep(wait)   # 네이버가 동영상 카드를 만들 시간
    ActionChains(driver).send_keys(Keys.ENTER).perform()
    time.sleep(0.4)
    log("유튜브 동영상 임베드 시도(붙여넣기).")
    return True


def publish(data, dry_run=None):
    cfg = load_config()
    naver_id = cfg["naver_id"]
    pub = cfg.get("publish", {})
    if dry_run is None:
        dry_run = pub.get("dry_run", True)
    headless = pub.get("headless", False)

    # 글별 카테고리 우선(data["category"]) → 없으면 config 기본값
    category = data.get("category") or cfg.get("blog", {}).get("category", "")

    structured = bool(data.get("news_blocks"))

    if structured:
        # 뉴스별 이미지 준비(기사 og:image, 없으면 Gamma). 상단 요약 이미지는 만들지 않음.
        try:
            from article_image import prepare_images
            prepare_images(data["news_blocks"])
        except Exception as e:
            log(f"뉴스 이미지 준비 실패(이미지 없이 진행): {e}")
    else:
        # (구버전 글) 상단 이미지 생성: image.source=gamma 면 Gamma, 아니면 배너. 폴백 보장.
        want_image = not data.get("no_banner") and cfg.get("blog", {}).get("banner", True)
        img_source = cfg.get("image", {}).get("source", "banner")
        if want_image and not data.get("banner"):
            date_str = f"{datetime.now():%Y년 %m월 %d일}"
            try:
                data["banner"] = (make_gamma_image(data) if img_source == "gamma"
                                  else make_banner(data["title"], date_str))
            except Exception as e:
                log(f"이미지 생성 실패({img_source}) → 배너 폴백: {e}")
                try:
                    data["banner"] = make_banner(data["title"], date_str)
                except Exception as e2:
                    log(f"배너 생성도 실패, 이미지 없이 진행: {e2}")

    driver = build_driver(headless)
    try:
        # GoBlogWrite 는 로그인된 계정의 블로그 에디터로 자동 연결된다
        # (로그인 ID와 블로그 주소가 달라도 안전)
        url = f"https://blog.naver.com/GoBlogWrite.naver?blogId={naver_id}"
        driver.get(url)
        time.sleep(5)

        # 진입 시 네이버 alert 가 떠 있으면 닫는다
        try:
            driver.switch_to.alert.accept()
            time.sleep(1)
        except Exception:
            pass

        # 로그인 안 된 상태면 로그인 페이지로 튕긴다 -> 안내 후 중단
        if "nidlogin" in driver.current_url or "nid.naver.com" in driver.current_url:
            shot(driver, "not_logged_in")
            raise RuntimeError(
                "로그인 세션이 만료되었습니다. login_setup.py 를 다시 실행해 주세요.")

        # 에디터는 mainFrame iframe 안에 있다
        WebDriverWait(driver, 20).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "mainFrame")))
        time.sleep(3)

        # 1) '작성 중이던 글' 팝업 -> 취소(새 글로 시작)
        click_if_present(driver, By.CSS_SELECTOR,
                         ".se-popup-button-cancel", timeout=4)
        # 2) 도움말/패널 팝업 닫기 (있으면)
        click_if_present(driver, By.CSS_SELECTOR,
                         ".se-help-panel-close-button", timeout=2)
        time.sleep(1)

        # 3) 제목 입력
        title_el = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                ".se-section-documentTitle .se-text-paragraph")))
        type_contenteditable(driver, title_el, data["title"])
        time.sleep(0.5)

        if structured:
            # 뉴스별 구조: 인사 → [소제목·본문·기사이미지·출처링크]×N → 안전수칙 → 마무리
            type_structured_post(driver, data)
            time.sleep(1)
        else:
            # (구버전) 상단 배너 + 본문 + 끝부분 출처링크
            if data.get("banner"):
                insert_image_top(driver, data["banner"])
            paragraphs = driver.find_elements(
                By.CSS_SELECTOR, ".se-component.se-text .se-text-paragraph")
            body_el = paragraphs[-1] if paragraphs else WebDriverWait(
                driver, 15).until(EC.presence_of_element_located((
                    By.CSS_SELECTOR, ".se-component.se-text .se-text-paragraph")))
            type_contenteditable(driver, body_el, data["body"])
            time.sleep(1)
            if data.get("video_url"):
                _embed_video(driver, data["video_url"])
            if data.get("sources"):
                insert_sources_links(driver, data["sources"])
                time.sleep(1)

        shot(driver, "after_typing")

        # 상단(배너) 미리보기 스크린샷 — 발행 레이어 열기 전에
        # 제목 요소를 화면에 노출시켜 최상단으로 스크롤
        try:
            title_top = driver.find_element(
                By.CSS_SELECTOR, ".se-section-documentTitle")
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'start'});", title_top)
            time.sleep(1)
        except Exception:
            pass
        shot(driver, "top_preview")

        # 4-1) 업로드 실패 모달이 떠 있으면 닫는다(발행 버튼을 가림)
        dismiss_upload_error(driver)

        # 5) 상단 '발행' 버튼 클릭 -> 발행 설정 레이어 열림
        if not click_if_present(driver, By.XPATH,
                "//button[contains(@class,'publish') and contains(.,'발행')]", 6):
            click_if_present(driver, By.XPATH,
                "//*[contains(@class,'publish_btn')]", 6)
        time.sleep(2)

        # 6) 카테고리 선택 (글별 지정 → config 기본값)
        select_category(driver, category)
        time.sleep(1)

        # 7) 태그 입력 (가능하면)
        tags = data.get("tags", [])
        try:
            tag_input = driver.find_element(By.ID, "tag-input")
            for t in tags:
                tag_input.send_keys(t)
                tag_input.send_keys(Keys.ENTER)
                time.sleep(0.3)
        except Exception:
            log("태그 입력란을 찾지 못해 건너뜀(선택사항).")

        shot(driver, "publish_layer")

        # dry_run: 카테고리/태그까지 세팅하고 '발행 확정' 직전에 멈춤
        if dry_run:
            log("DRY_RUN: 발행 직전 멈춤. logs/ 의 after_typing / publish_layer "
                "스크린샷에서 본문·카테고리·태그를 확인하세요. 문제 없으면 "
                "config 의 dry_run 을 false 로.")
            return {"status": "dry_run"}

        # 8) 레이어 안의 최종 '발행' 확정 버튼
        if not click_if_present(driver, By.XPATH,
                "//div[contains(@class,'layer') or contains(@class,'option')]"
                "//button[contains(@class,'confirm') and contains(.,'발행')]", 6):
            click_if_present(driver, By.XPATH,
                "//button[contains(@class,'confirm_btn')]", 6)
        time.sleep(5)
        shot(driver, "after_publish")
        log("발행 완료(추정). 스크린샷으로 결과를 확인하세요.")
        return {"status": "published"}

    except Exception as e:
        shot(driver, "error")
        log(f"발행 중 오류: {e}")
        raise
    finally:
        driver.quit()


if __name__ == "__main__":
    import json
    import sys
    from common import POSTS_DIR
    # 인자로 posts/xxx.json 을 받거나, 가장 최근 글을 발행
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        files = sorted(f for f in os.listdir(POSTS_DIR) if f.endswith(".json"))
        if not files:
            raise SystemExit("발행할 글이 없습니다. 먼저 generate_content.py 실행.")
        path = os.path.join(POSTS_DIR, files[-1])
    with open(path, "r", encoding="utf-8") as f:
        publish(json.load(f))
