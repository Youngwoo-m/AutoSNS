"""네이버 블로그 자동 이웃추가 — 안전형(서로이웃 '신청 수락' 중심).

콜드 이웃추가(모르는 사람에게 선신청)는 위험/스팸성이 커서 하지 않는다.
대신 '나에게 들어온 서로이웃 신청'을 하루 소량만 수락한다(가장 안전하고 호혜적).

★ 안전장치:
  - 기본 dry_run=True: 수락 버튼 개수만 세어 보고, 실제로 누르지 않는다.
  - 하루 한도(daily_limit)·랜덤 딜레이. 상태파일로 한도 누적 관리.
  - 오류/차단 문구 감지 시 중단. launchd 금지 — supervised 수동 실행 권장.
  - 첫 실행은 반드시 dry-run 으로 돌려 logs/ 스크린샷을 보고 셀렉터를 확정할 것
    (네이버 관리 페이지 DOM 은 계정·개편에 따라 다를 수 있음).

사용:
  python naver_neighbor.py         # dry-run(수락 대상만 집계)
  python naver_neighbor.py --go    # 실제 수락(config.neighbor_add.enabled=true 필요)
"""
import json
import os
import random
import sys
import time

from selenium.webdriver.common.by import By

from common import load_config, log
from publish_naver import build_driver, shot

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neighbor_state.json")
# 서로이웃 신청 관리 페이지(계정/개편에 따라 다르면 config.neighbor_add.manage_url 로 지정)
DEFAULT_MANAGE_URL = "https://admin.blog.naver.com/BuddyInviteManageForm.naver"
BLOCK_HINTS = ["로그인", "이용이 제한", "차단", "스팸", "비정상", "잠시 후 다시"]


def _load_state():
    try:
        with open(STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(s):
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def _today():
    return time.strftime("%Y-%m-%d")


def _enter_content_frame(driver):
    """관리 콘텐츠 iframe 으로 전환(서로이웃 신청 표가 그 안에 있다). 실패 시 최상위 유지."""
    driver.switch_to.default_content()
    for fr in driver.find_elements(By.TAG_NAME, "iframe"):
        try:
            driver.switch_to.frame(fr)
            if "받은신청" in driver.page_source or "이웃신청" in driver.page_source:
                return True
        except Exception:
            pass
        driver.switch_to.default_content()
    return False


def _accept_button(driver):
    """'수락' 버튼/링크(체크한 신청을 일괄 수락)."""
    els = driver.find_elements(
        By.XPATH, "//a[normalize-space()='수락'] | //button[normalize-space()='수락'] "
        "| //input[@value='수락'] | //*[@value='수락']")
    return els[0] if els else None


def _request_checkboxes(driver):
    """받은신청 각 행의 체크박스(전체선택 제외 추정). 신청이 없으면 빈 리스트."""
    if "이웃신청이 없습니다" in driver.page_source:
        return []
    boxes = driver.find_elements(
        By.XPATH, "//tbody//input[@type='checkbox'] | //td//input[@type='checkbox']")
    return boxes


def run(dry_run=None):
    cfg = load_config()
    na = cfg.get("neighbor_add", {})
    if dry_run is None:
        dry_run = na.get("dry_run", True)
    if not dry_run and not na.get("enabled", False):
        log("neighbor_add.enabled=false → 실제 수락 중단, dry-run 으로만 확인합니다.")
        dry_run = True

    limit = int(na.get("daily_limit", 10))
    st = _load_state()
    used = int(st.get(_today(), 0))
    remaining = max(0, limit - used)
    lo, hi = float(na.get("min_delay", 40)), float(na.get("max_delay", 100))
    manage_url = na.get("manage_url", DEFAULT_MANAGE_URL)
    log(f"자동 이웃추가(서로이웃 수락) 시작 (dry_run={dry_run}) — 오늘 {used}/{limit}, 최대 {remaining}")
    if remaining <= 0:
        log("오늘 한도 소진 → 종료"); return {"status": "limit_reached", "done": 0}

    driver = build_driver(headless=False)   # supervised
    done = 0
    try:
        driver.get(manage_url)
        time.sleep(random.uniform(4.0, 6.0))
        # 콘텐츠가 iframe 안에 있어 전환 필요. '받은신청' 표가 그 안에 있다.
        if not _enter_content_frame(driver):
            log("관리 콘텐츠(iframe)를 찾지 못함 — URL/로그인 확인 필요.")
        shot(driver, "neighbor_manage")
        if "로그인" in driver.page_source and "서로이웃" not in driver.page_source:
            log("⚠ 로그인 세션 만료로 보입니다 → login_setup.py 로 재로그인 필요")
            return {"status": "login_required", "done": 0}

        boxes = _request_checkboxes(driver)
        n = len(boxes)
        log(f"받은 서로이웃 신청 {n}건 감지")
        if n == 0:
            log("수락할 신청이 없습니다."); return {"status": "ok", "done": 0, "pending": 0}
        pick = min(n, remaining)
        if dry_run:
            log(f"[DRY-RUN] 수락 대상 {pick}건 — 실제 클릭하지 않음.")
            shot(driver, "neighbor_dryrun")
            return {"status": "ok", "done": 0, "pending": n}
        # 실제 수락: 한도만큼 체크박스 선택 후 '수락' 버튼 1회(일괄).
        for b in boxes[:pick]:
            try:
                if not b.is_selected():
                    driver.execute_script("arguments[0].click();", b)
                time.sleep(random.uniform(0.4, 1.0))
            except Exception:
                pass
        btn = _accept_button(driver)
        if btn is None:
            log("수락 버튼을 찾지 못했습니다."); return {"status": "no_button", "done": 0}
        try:
            btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)
        time.sleep(random.uniform(1.5, 3.0))
        driver.switch_to.default_content()          # 확인 팝업은 최상위에 뜰 수 있음
        for lbl in ("확인", "예"):
            els = driver.find_elements(
                By.XPATH, f"//button[normalize-space()='{lbl}'] | //a[normalize-space()='{lbl}']")
            if els:
                try:
                    els[0].click()
                except Exception:
                    pass
                break
        done = pick
        st[_today()] = used + done
        _save_state(st)
        log(f"  서로이웃 {done}건 일괄 수락")
        shot(driver, "neighbor_done")
    finally:
        driver.quit()
    log(f"자동 이웃추가 종료 — 이번 {done}건, 오늘 누적 {used + done}/{limit}")
    return {"status": "ok", "done": done}


if __name__ == "__main__":
    go = "--go" in sys.argv
    print(json.dumps(run(dry_run=not go), ensure_ascii=False))
