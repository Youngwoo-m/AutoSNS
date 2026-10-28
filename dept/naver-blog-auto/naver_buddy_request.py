"""네이버 서로이웃 '선신청' — 안전형(콜드 신청이라 리스크 높음 → 강한 안전장치).

재난안전·지역 키워드로 블로그를 검색해 관련 블로거에게 서로이웃을 먼저 신청한다.
네이버는 선신청 자동화를 스팸으로 탐지해 계정 제한 위험이 크므로, 아래를 지킨다:
  - 기본 dry_run=True: 대상 목록만 뽑고, 첫 대상의 '신청 폼 화면'만 열어 확인(제출 안 함).
  - 하루 한도(작게, 기본 5)·요청 간 긴 랜덤 딜레이(기본 60~150초).
  - 이미 신청한 대상·내 블로그·제외목록은 건너뜀(상태파일 누적).
  - '하루 신청 한도/제한/스팸' 문구 감지 즉시 중단.
  - 스케줄은 저빈도만 허용: 매주 금 21:00 launchd(com.smuds.naverbuddy.weekly),
    1회 5명 이하(=주 5명). 빈도를 올리면 계정 제한 위험이 급격히 커진다.

사용:
  python naver_buddy_request.py        # dry-run(대상 목록 + 폼 화면 확인, 신청 안 함)
  python naver_buddy_request.py --go   # 실제 선신청(config.buddy_request.enabled=true 필요)
"""
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request

from selenium.webdriver.common.by import By

from common import load_config, log
from publish_naver import build_driver, shot

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "buddy_request_state.json")
BLOCK_HINTS = ["하루", "한도", "초과", "제한", "스팸", "비정상", "잠시 후", "차단"]
OWN_IDS = {"studs23", "smuds"}


def _load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"sent": [], "daily": {}}


def _save_state(s):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def _today():
    return time.strftime("%Y-%m-%d")


def _search_blog_ids(cfg, keywords, per=20):
    """네이버 블로그 검색 API 로 키워드별 블로거 ID 를 모은다(최신순)."""
    ns = cfg.get("news", {}).get("naver_search", {})
    cid, sec = ns.get("client_id"), ns.get("client_secret")
    ids = []
    if not (cid and sec):
        log("naver_search client_id/secret 없음 → 대상 검색 불가")
        return ids
    for kw in keywords:
        try:
            url = "https://naverapihub.apigw.ntruss.com/search/v1/blog?" + urllib.parse.urlencode(
                {"query": kw, "display": per, "sort": "date"})
            req = urllib.request.Request(
                url, headers={"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": sec})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.load(r)
            for it in data.get("items", []):
                link = it.get("bloggerlink") or it.get("link", "")
                m = re.search(r"blog\.naver\.com/([A-Za-z0-9_-]+)", link)
                if m:
                    ids.append(m.group(1))
        except Exception as e:
            log(f"검색 실패({kw}): {type(e).__name__}")
    # 중복 제거(순서 유지)
    return list(dict.fromkeys(ids))


def _pick_targets(cfg):
    br = cfg.get("buddy_request", {})
    kws = br.get("keywords", ["제천 재난안전", "충북 안전", "재난안전 정보"])
    excludes = set(cfg.get("news", {}).get("naver_search", {}).get("exclude", []))
    st = _load_state()
    sent = set(st.get("sent", []))
    ids = _search_blog_ids(cfg, kws)
    out = []
    for bid in ids:
        if bid in OWN_IDS or bid in sent:
            continue
        if any(bid in e for e in excludes):
            continue
        out.append(bid)
    return out


def _select_seroibut(driver):
    """'서로이웃' 라디오 선택. 폼: '(○)이웃 (○)서로이웃으로 추가합니다' — 2번째가 서로이웃."""
    for xp in ("//label[contains(.,'서로이웃')]//input[@type='radio']",
               "//input[@type='radio'][following::*[1][contains(.,'서로이웃')]]",
               "//*[contains(text(),'서로이웃')]/preceding::input[@type='radio'][1]",
               "//input[@type='radio' and (@value='both' or @value='2')]",
               "(//input[@type='radio'])[2]"):
        els = driver.find_elements(By.XPATH, xp)
        if els:
            try:
                driver.execute_script("arguments[0].click();", els[0])
                return True
            except Exception:
                pass
    els = driver.find_elements(By.XPATH, "//*[normalize-space()='서로이웃']")
    if els:
        try:
            els[0].click(); return True
        except Exception:
            pass
    return False


def _click_text(driver, labels):
    for lb in labels:
        els = driver.find_elements(
            By.XPATH, f"//a[normalize-space()='{lb}'] | //button[normalize-space()='{lb}'] "
            f"| //input[@value='{lb}'] | //*[@role='button'][normalize-space()='{lb}']")
        if els:
            try:
                els[0].click(); return True
            except Exception:
                try:
                    driver.execute_script("arguments[0].click();", els[0]); return True
                except Exception:
                    pass
    return False


def _switch_mainframe(driver):
    driver.switch_to.default_content()
    for f in driver.find_elements(By.TAG_NAME, "iframe"):
        if (f.get_attribute("id") or "") == "mainFrame":
            driver.switch_to.frame(f)
            return True
    return False


def _send_one(driver, tid, message, dry):
    """한 블로그에 서로이웃 신청(팝업 흐름). dry 면 '서로이웃 선택'까지만.

    흐름: 블로그 방문 → mainFrame → '이웃추가' 클릭 → BuddyAdd 팝업창 →
          서로이웃 라디오 → 다음 → (메시지) → 확인. (BuddyAdd.naver 직접이동은 안 됨)
    """
    main_handle = driver.current_window_handle
    driver.get(f"https://blog.naver.com/{urllib.parse.quote(tid)}")
    time.sleep(random.uniform(2.5, 4.0))
    _switch_mainframe(driver)
    links = driver.find_elements(By.XPATH, "//a[normalize-space()='이웃추가']")
    if not links:
        log(f"  {tid}: '이웃추가' 버튼 없음(비공개/차단 등) → 건너뜀")
        return "skip"
    before = set(driver.window_handles)
    try:
        driver.execute_script("arguments[0].click();", links[0])
    except Exception:
        links[0].click()
    time.sleep(random.uniform(2.0, 3.5))
    new = set(driver.window_handles) - before
    if not new:
        log(f"  {tid}: 신청 팝업이 안 열림 → 건너뜀")
        driver.switch_to.default_content()
        return "skip"
    popup = list(new)[0]
    result = "sent"
    try:
        driver.switch_to.window(popup)
        time.sleep(1.5)
        src = driver.page_source
        if any(h in src for h in ("이미 서로이웃", "이미 이웃", "신청할 수 없", "허용하지 않")):
            log(f"  {tid}: 신청 불가(이미 이웃/서로이웃 비허용) → 건너뜀")
            result = "skip"
        elif not _select_seroibut(driver):
            log(f"  {tid}: '서로이웃' 옵션 없음(선택 불가) → 건너뜀")
            shot(driver, f"buddy_norad_{tid}")
            result = "no_radio"
        elif dry:
            shot(driver, f"buddy_ready_{tid}")   # 서로이웃 선택 상태 확인(제출 안 함)
            result = "dry"
        else:
            _click_text(driver, ["다음", "다음 단계"])
            time.sleep(1.5)
            box = driver.find_elements(By.XPATH, "//textarea")
            if box and message:
                try:
                    box[0].clear(); box[0].send_keys(message[:100])
                except Exception:
                    pass
            if not _click_text(driver, ["다음", "확인", "신청"]):
                log(f"  {tid}: 제출 버튼 못 찾음"); result = "no_button"
            else:
                time.sleep(random.uniform(1.5, 3.0))
                body = ""
                try:
                    body = driver.find_element(By.TAG_NAME, "body").text
                except Exception:
                    pass
                if any(h in body for h in BLOCK_HINTS):
                    shot(driver, "buddy_blocked"); result = "blocked"
    finally:
        # 팝업 닫고 원래 창으로
        try:
            if driver.current_window_handle != main_handle:
                driver.close()
        except Exception:
            pass
        driver.switch_to.window(main_handle)
        driver.switch_to.default_content()
    return result


def run(dry_run=None):
    cfg = load_config()
    br = cfg.get("buddy_request", {})
    if dry_run is None:
        dry_run = br.get("dry_run", True)
    if not dry_run and not br.get("enabled", False):
        log("buddy_request.enabled=false → 실제 신청 중단, dry-run 으로만 확인합니다.")
        dry_run = True

    limit = int(br.get("daily_limit", 5))
    lo, hi = float(br.get("min_delay", 60)), float(br.get("max_delay", 150))
    message = br.get("message", "세명대 재난안전학과입니다. 재난안전 소식 나누고 싶어 서로이웃 신청드려요!")
    st = _load_state()
    used = int(st.get("daily", {}).get(_today(), 0))
    remaining = max(0, limit - used)
    log(f"서로이웃 선신청 시작 (dry_run={dry_run}) — 오늘 {used}/{limit}, 최대 {remaining}")
    if remaining <= 0:
        log("오늘 한도 소진 → 종료"); return {"status": "limit_reached", "done": 0}

    targets = _pick_targets(cfg)
    log(f"신청 대상 후보 {len(targets)}명(이미 신청/내블로그/제외 제외 후)")
    if not targets:
        log("대상이 없습니다(키워드 조정 필요)."); return {"status": "no_targets", "done": 0}

    pick = targets[:remaining]
    if dry_run:
        log(f"[DRY-RUN] 신청 예정 {len(pick)}명: {', '.join(pick)}")
        driver = build_driver(headless=br.get("headless", False))
        try:
            _send_one(driver, pick[0], message, dry=True)   # 첫 대상 폼만 열어 확인
            log(f"[DRY-RUN] 첫 대상({pick[0]}) 신청 폼 화면 확인 — 제출 안 함")
        finally:
            driver.quit()
        return {"status": "ok", "done": 0, "targets": pick}

    driver = build_driver(headless=br.get("headless", False))
    done = 0
    try:
        for tid in pick:
            res = _send_one(driver, tid, message, dry=False)
            if res == "blocked":
                log("⚠ 네이버 신청 제한 감지 → 즉시 중단"); break
            if res == "sent":
                done += 1
                st.setdefault("sent", []).append(tid)
                st.setdefault("daily", {})[_today()] = used + done
                _save_state(st)
                log(f"  서로이웃 신청 {done}/{len(pick)} → {tid}")
                time.sleep(random.uniform(lo, hi))
            else:
                time.sleep(random.uniform(3, 6))
        shot(driver, "buddy_done")
    finally:
        driver.quit()
    log(f"서로이웃 선신청 종료 — 이번 {done}명, 오늘 누적 {used + done}/{limit}")
    return {"status": "ok", "done": done}


if __name__ == "__main__":
    go = "--go" in sys.argv
    print(json.dumps(run(dry_run=not go), ensure_ascii=False))
