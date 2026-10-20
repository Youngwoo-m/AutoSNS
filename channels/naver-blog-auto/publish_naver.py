"""저장된 Chrome 프로필로 네이버 블로그 스마트에디터 ONE 에 글을 발행한다.

주의: 네이버 에디터는 수시로 구조/클래스명이 바뀐다. 셀렉터가 안 맞으면
logs/ 에 스크린샷(.png)을 남기니 그걸 보고 SELECTORS 를 수정하면 된다.
config.publish.dry_run=true 면 '발행' 직전에 멈추고 스크린샷만 남긴다.
"""
import json
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

from common import LOGS_DIR, POSTS_DIR, PROFILE_DIR, load_config, log, start_chrome
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
    driver = start_chrome(opts)
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
    # 네이버는 카테고리 이름의 띄어쓰기를 줄바꿈 없는 공백(U+00A0)으로 그린다('학과 자료실').
    # normalize-space 는 이를 공백으로 보지 않아 이름이 안 맞았다 → 일반 공백으로 바꿔 비교.
    nb = "translate({}, '\u00a0', ' ')"
    candidates = [
        f"//label[normalize-space({nb.format('text()')})='{name}']",
        f"//span[normalize-space({nb.format('text()')})='{name}']",
        f"//*[contains(@class,'option') or contains(@class,'item') or "
        f"contains(@class,'category')][normalize-space({nb.format('.')})='{name}']",
        f"//*[normalize-space({nb.format('text()')})='{name}']",
    ]
    for xp in candidates:
        if click_if_present(driver, By.XPATH, xp, 2):
            log(f"카테고리 '{name}' 선택됨.")
            return True
    # 3) 목록이 길면 드롭다운 안에서 스크롤돼 위·아래 항목이 가려진다(보이지 않아 클릭 실패).
    #    2026-10-10 '학과 자료실'이 위로 가려져 기본값(학과진로)으로 발행됐다 → 화면에 끌어와 누른다.
    for xp in candidates:
        for el in driver.find_elements(By.XPATH, xp):
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.4)
                driver.execute_script("arguments[0].click();", el)
                time.sleep(0.6)
                log(f"카테고리 '{name}' 선택됨(목록 스크롤).")
                return True
            except Exception:
                continue
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


def insert_link_blocks(driver, blocks, outro=""):
    """본문 뒤에 [요약 여러 줄 + 링크 한 줄] 묶음을 차례로 넣고, 끝에 outro 를 붙인다.

    채용정보 글처럼 항목마다 원문으로 가는 링크가 바로 아래 있어야 하는 글에 쓴다
    (insert_sources_links 는 링크를 글 끝에 모아 둔다). blocks: [{text, link_text, url}]
    """
    _end_key = Keys.ARROW_DOWN if IS_MAC else Keys.END
    ActionChains(driver).key_down(MOD_KEY).send_keys(_end_key).key_up(MOD_KEY).perform()
    time.sleep(0.3)
    done = 0
    for b in blocks:
        ActionChains(driver).send_keys(Keys.ENTER).send_keys(Keys.ENTER).perform()
        _type_text(driver, b["text"])
        ActionChains(driver).send_keys(Keys.ENTER).perform()
        if _link_line(driver, b.get("link_text") or "👉 원본 보기", b["url"]):
            done += 1
    if outro:
        ActionChains(driver).send_keys(Keys.ENTER).send_keys(Keys.ENTER).perform()
        _type_text(driver, outro)
    log(f"링크 묶음 {done}/{len(blocks)}건 삽입.")
    return done


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
            time.sleep(0.15)                 # 클립보드에 실제로 올라갈 틈을 준다
            ActionChains(driver).key_down(MOD_KEY).send_keys("v")\
                .key_up(MOD_KEY).perform()
            # 붙여넣기는 에디터가 비동기로 처리한다. 0.3초로는 다음 입력과 겹쳐
            # 그 줄이 통째로 사라지는 일이 있었다(2026-10-12).
            time.sleep(0.9)
            return
        log("pbcopy 실패 → send_keys 로 대체(이모지 깨질 수 있음).")
    ActionChains(driver).send_keys(text).perform()


def _type_text(driver, text):
    """현재 커서 위치에 여러 줄 텍스트를 입력(줄바꿈은 ENTER).

    줄마다 들어갔는지 확인하고, 통째로 빠졌으면 한 번 더 넣는다. 이모지가 든 줄은
    클립보드 붙여넣기로 들어가는데(맥 ChromeDriver 가 이모지를 깨뜨린다) 에디터가
    붙여넣기를 처리하기 전에 다음 입력이 겹치면 그 줄이 사라진다. 2026-10-12 WBGT
    글에서 요약 3줄과 인사말이 두 번 연속 통째로 날아갔다.

    길이가 조금 모자란 정도면 다시 넣지 않는다 — 덧쓰면 글자가 겹쳐 더 나빠진다."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.strip():
            before = len(_doc_text(driver))
            _send_text(driver, line)
            grew = len(_doc_text(driver)) - before
            if grew < min(3, len(line)):          # 아무것도 안 들어갔다
                log(f"입력 누락 감지 → 다시 넣는다: {line[:24]}")
                time.sleep(0.8)
                _send_text(driver, line)
                if len(_doc_text(driver)) - before < min(3, len(line)):
                    log(f"⚠ 두 번째도 들어가지 않음: {line[:24]}")
        if i < len(lines) - 1:
            ActionChains(driver).send_keys(Keys.ENTER).perform()
        time.sleep(0.05)


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

    # 글 맨 위 3줄 요약 — 네이버 지식스니펫·AI 검색 요약이 이 부분을 그대로 가져간다.
    if data.get("summary"):
        _type_text(driver, "📌 3줄 요약")
        ActionChains(driver).send_keys(Keys.ENTER).perform()
        _type_text(driver, data["summary"])
        ActionChains(driver).send_keys(Keys.ENTER, Keys.ENTER).perform()

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
        # 블록마다 관련 영상을 하나씩 둘 수 있다(수동 글에서 뉴스 영상 여러 편을 넣을 때).
        if blk.get("video_url"):
            ActionChains(driver).send_keys(Keys.ENTER).perform()
            if blk.get("video_label"):
                _type_text(driver, blk["video_label"])
            _embed_video(driver, blk["video_url"])
    if data.get("tips"):
        ActionChains(driver).send_keys(Keys.ENTER, Keys.ENTER).perform()
        _type_text(driver, data["tips"])
    # 관련 유튜브 영상 — 블로그 독자가 채널로 넘어가는 길(외부 유입이 전체의 0.1%뿐이었다).
    # 블로거 글과 같은 자리(자주 묻는 질문 앞)에 둔다. 예전엔 예전 형식 글에서만 넣고
    # 구조형 글에서는 video_url 을 무시해, 진로·자격증 시리즈 네이버판엔 영상이 없었다.
    if data.get("video_url"):
        ActionChains(driver).send_keys(Keys.ENTER, Keys.ENTER).perform()
        _type_text(driver, "🎬 영상으로 보기")
        _embed_video(driver, data["video_url"])
    # 자주 묻는 질문 — 질문-답변 쌍은 검색 답변·생성형 AI 인용에 가장 잘 걸리는 형식이다.
    if data.get("faq"):
        ActionChains(driver).send_keys(Keys.ENTER, Keys.ENTER).perform()
        _type_text(driver, "❓ 자주 묻는 질문")
        ActionChains(driver).send_keys(Keys.ENTER).perform()
        _type_text(driver, data["faq"])
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


def _doc_text(driver):
    """에디터 본문 글자(제목 포함). 글자 수 비교·내용 확인용."""
    # body.innerText 는 링크 도구막대 같은 에디터 UI 글자까지 들어가 커서 위치에 따라 달라진다
    # (주소 줄 하나 지울 때마다 121자 차이). 본문 문단 글자만 모은다.
    return driver.execute_script(
        "return [...document.querySelectorAll('.se-text-paragraph')]"
        ".map(e=>e.innerText).join('\\n');") or ""


def _verify_document(driver, data):
    """발행 직전, 넣으려던 내용이 에디터에 다 있는지 확인한다. 빠진 것 목록을 돌려준다.

    10/12 WBGT 글 시험에서 요약·인사·첫 소제목·첫 그림이 통째로 사라진 채 다음 단계로
    넘어갔다(재현되지 않는 간헐적 현상). 빠진 채 발행되지 않게 여기서 막는다."""
    import re
    txt = re.sub(r"\s+", " ", _doc_text(driver))
    want = []
    if data.get("summary"):
        want += [l.strip() for l in data["summary"].splitlines() if l.strip()]
    want.append((data.get("intro") or "").splitlines()[0] if data.get("intro") else "")
    for b in data.get("news_blocks", []):
        want.append(b.get("heading", ""))
        want.append((b.get("paragraph") or "").strip().splitlines()[0] if b.get("paragraph") else "")
    missing = [w for w in want if w and re.sub(r"\s+", " ", w)[:25] not in txt]
    imgs = sum(1 for b in data.get("news_blocks", []) if b.get("image"))
    have = len(driver.find_elements(By.CSS_SELECTOR, ".se-component.se-image"))
    if data.get("banner"):
        imgs += 1
    if have < imgs:
        missing.append(f"그림 {imgs}장 중 {have}장만 있음")
    return missing


def _strip_embed_url_lines(driver, url):
    """유튜브 주소를 붙여넣으면 에디터가 영상 카드를 만들면서 주소 글자도 한 줄 남긴다.
    그 줄을 지운다. 본문 입력을 모두 마친 뒤(발행 직전)에 부른다.

    스크립트로 옮긴 커서는 에디터가 인식하지 못해, 지우기 키가 주소 대신 영상 카드를
    지웠다(2026-09-28 시험). 줄 오른쪽 빈 곳을 실제로 클릭해 커서를 두고 줄을 선택해
    지운다. 지운 뒤 영상 카드 수가 줄었으면 되돌린다(⌘Z)."""
    if not url:
        return 0
    card_sel = ".se-component.se-oembed"
    removed = 0
    for _ in range(3):
        lines = [p for p in driver.find_elements(
            By.CSS_SELECTOR, ".se-component.se-text .se-text-paragraph")
            if (p.text or "").strip() == url]
        if not lines:
            break
        before = len(driver.find_elements(By.CSS_SELECTOR, card_sel))
        p = lines[-1]
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", p)
        time.sleep(0.3)
        # 줄의 글자(링크) 끝 바로 오른쪽을 누른다 — 줄 폭의 오른쪽 끝을 누르면 그 자리가
        # 다른 요소(글감 검색창 등)에 가려 커서가 엉뚱한 줄에 남는 일이 있었다.
        span = (p.find_elements(By.CSS_SELECTOR, "span") or [p])[-1]
        ActionChains(driver).move_to_element_with_offset(
            span, span.size["width"] // 2 + 2, 0).click().perform()
        time.sleep(0.6)
        ActionChains(driver).send_keys(Keys.END).perform()
        time.sleep(0.2)
        ActionChains(driver).key_down(Keys.SHIFT).send_keys(Keys.HOME).key_up(Keys.SHIFT).perform()
        time.sleep(0.3)
        # 지운 뒤 본문 글자가 주소 길이보다 많이 줄었으면 다른 줄(본문)을 지운 것 — 되돌린다.
        # 10/12 WBGT 글의 3줄 요약 앞부분이 이렇게 사라졌다. (에디터는 자체 선택을 써서
        # window.getSelection 으로는 선택 내용을 읽을 수 없다.)
        text_before = len(_doc_text(driver))
        ActionChains(driver).send_keys(Keys.BACK_SPACE).perform()
        time.sleep(0.6)
        lost = text_before - len(_doc_text(driver))
        if lost > len(url) + 3:
            ActionChains(driver).key_down(MOD_KEY).send_keys("z").key_up(MOD_KEY).perform()
            time.sleep(0.8)
            log(f"⚠ 주소 줄 지우기가 본문 {lost}자를 지워 되돌렸습니다(주소 줄은 남음).")
            break
        if len(driver.find_elements(By.CSS_SELECTOR, card_sel)) < before:
            ActionChains(driver).key_down(MOD_KEY).send_keys("z").key_up(MOD_KEY).perform()
            time.sleep(0.8)
            log("⚠ 주소 줄 지우기가 영상 카드를 건드려 되돌렸습니다(주소 줄은 남음).")
            break
        removed += 1
    if removed:
        log(f"영상 카드 위 주소 줄 {removed}개 정리.")
    return removed


def _save_payload(data, dry_run):
    """발행에 넣은 원고를 posts/ 에 남긴다.

    파일을 거치지 않고 메모리에서 바로 publish() 를 부르는 호출자가 있어, 발행이
    엎어지면 원고가 통째로 사라진다. 10/12 '더위지수(WBGT)' 글이 발행도 임시저장도
    못 된 채 날아갔고 어디에도 남지 않아 다시 올릴 수 없었다.

    실패해도 발행은 그대로 진행한다 — 기록 때문에 글을 못 올리는 일은 없어야 한다."""
    try:
        os.makedirs(POSTS_DIR, exist_ok=True)
        name = f"naver_{datetime.now():%Y%m%d_%H%M%S}{'_dry' if dry_run else ''}.json"
        path = os.path.join(POSTS_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        log(f"원고 보관: {os.path.basename(path)}")
        return path
    except Exception as e:
        log(f"원고 보관 실패({type(e).__name__}) — 발행은 계속한다")
        return None


def publish(data, dry_run=None):
    cfg = load_config()
    naver_id = cfg["naver_id"]
    pub = cfg.get("publish", {})
    if dry_run is None:
        dry_run = pub.get("dry_run", True)
    headless = pub.get("headless", False)
    _save_payload(data, dry_run)

    # 글별 카테고리 우선(data["category"]) → 없으면 config 기본값
    category = data.get("category") or cfg.get("blog", {}).get("category", "")

    structured = bool(data.get("news_blocks"))

    if structured:
        # 뉴스별 이미지 준비(기사 og:image, 없으면 Gamma).
        # no_images: 기사가 없는 글(진로·자격증 시리즈)은 건너뛴다 — 넣어 봐야
        # 내용과 무관한 그림이고, Gamma 는 편당 크레딧 10을 태운다(2026-09-23 확인).
        if data.get("no_images"):
            log("이미지 준비 건너뜀(no_images).")
        else:
            try:
                from article_image import prepare_images
                prepare_images(data["news_blocks"])
            except Exception as e:
                log(f"뉴스 이미지 준비 실패(이미지 없이 진행): {e}")
        # 상단 배너(제목·날짜 헤더). config.blog.banner 로 끌 수 있다.
        # 여기서는 Gamma 를 쓰지 않는다 — 헤더는 제목/날짜를 넣는 고정 서식이고,
        # Gamma 는 유료 크레딧을 쓰므로 뉴스별 삽화(article_image)에만 남긴다.
        want_banner = (not data.get("no_banner")
                       and cfg.get("blog", {}).get("banner", True))
        if want_banner and not data.get("banner"):
            try:
                data["banner"] = make_banner(
                    data["title"], f"{datetime.now():%Y년 %m월 %d일}",
                    badge=data.get("banner_badge", "DISASTER BRIEFING"))
            except Exception as e:
                log(f"배너 생성 실패, 배너 없이 진행: {e}")
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
            # 상단 배너 → 뉴스별 구조: 인사 → [소제목·본문·기사이미지·출처링크]×N
            #             → 안전수칙 → 마무리
            if data.get("banner"):
                insert_image_top(driver, data["banner"])
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
            if data.get("link_blocks"):
                insert_link_blocks(driver, data["link_blocks"], data.get("outro", ""))
                time.sleep(1)
            if data.get("video_url"):
                _embed_video(driver, data["video_url"])
            if data.get("sources"):
                insert_sources_links(driver, data["sources"])
                time.sleep(1)

        # 영상 카드 위에 남은 주소 글자 줄을 지운다(본문 입력을 다 마친 뒤라 커서 위치가 무관하다).
        for vurl in [data.get("video_url")] + [b.get("video_url") for b in data.get("news_blocks", [])]:
            if vurl:
                _strip_embed_url_lines(driver, vurl)

        shot(driver, "after_typing")
        if structured:
            missing = _verify_document(driver, data)
            if missing:
                shot(driver, "content_missing")
                raise RuntimeError("본문 일부가 에디터에서 빠져 발행을 멈춥니다: "
                                   + " / ".join(m[:30] for m in missing[:5]))

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
        def _layer_open():
            return bool(driver.find_elements(
                By.XPATH, "//*[normalize-space(text())='공개 설정' or normalize-space(text())='발행 시간']"))
        for _try in range(2):
            if not click_if_present(driver, By.XPATH,
                    "//button[contains(@class,'publish') and contains(.,'발행')]", 6):
                click_if_present(driver, By.XPATH,
                    "//*[contains(@class,'publish_btn')]", 6)
            time.sleep(2)
            if _layer_open():
                break
            # 10/12: 발행 레이어가 안 열린 채 다음 단계로 넘어가 '발행 완료(추정)'만 남기고
            # 글은 임시저장 상태로 남았다. 열린 팝업을 닫고 한 번 더 누른다.
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(1)
        if not _layer_open():
            shot(driver, "no_publish_layer")
            raise RuntimeError("발행 설정 레이어가 열리지 않았습니다(발행 안 됨).")

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
    # 인자로 posts/xxx.json 을 받거나, 가장 최근 글을 발행.
    # naver_*.json 은 발행할 때 남긴 원고 보관본이라 '최근 글' 자동 선택에서 뺀다
    # (이름이 뒤에 와서 그냥 두면 옛 글이 다시 발행된다).
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        files = sorted(f for f in os.listdir(POSTS_DIR)
                       if f.endswith(".json") and not f.startswith("naver_"))
        if not files:
            raise SystemExit("발행할 글이 없습니다. 먼저 generate_content.py 실행.")
        path = os.path.join(POSTS_DIR, files[-1])
    with open(path, "r", encoding="utf-8") as f:
        publish(json.load(f))
