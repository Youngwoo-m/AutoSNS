"""인스타 자동 맞팔(팔로우백) — 안전형.

'나를 팔로우하는데 내가 안 맞팔한 계정'만 하루 소량, 사람처럼 랜덤 딜레이로 팔로우백한다.
콜드 팔로우(모르는 사람 선팔)는 하지 않는다 → 상대적으로 안전(그래도 0 위험은 아님).

★ 안전장치(인스타 계정 정지 위험 최소화):
  - 기본 dry_run=True: 실제로 팔로우하지 않고 '맞팔 대상 수'만 세어 보고한다.
  - 하루 한도(daily_limit)·요청 간 랜덤 딜레이(min/max_delay). 상태파일로 한도 누적 관리.
  - '작업이 차단/나중에 다시/챌린지' 등 감지 즉시 중단.
  - launchd 스케줄에 넣지 말 것 — 사람이 지켜보는 supervised 수동 실행 권장.

사용:
  python ig_follow_back.py          # dry-run(대상만 집계, 클릭 안 함)
  python ig_follow_back.py --go     # 실제 맞팔(config.follow_back.enabled=true 필요)
"""
import json
import os
import random
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from common import load_config, log
from post_instagram import build_driver, shot

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "follow_back_state.json")
# 계정 보호용 중단 신호. page_source(스크립트 포함)가 아니라 '화면에 보이는 본문 텍스트'에서만
# 찾는다. 스크립트에 흔한 'challenge/제한' 같은 단어로 오탐하지 않도록 구체적 문구만 쓴다.
BLOCK_HINTS = ["작업이 차단되었습니다", "나중에 다시 시도", "이 작업을 완료할 수 없",
               "행동이 차단", "잠시 후 다시 시도", "Action Blocked", "Try Again Later",
               "We restrict certain activity", "Please wait a few minutes"]


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


def _blocked(driver):
    # page_source 가 아니라 '화면에 보이는 본문 텍스트'만 검사(스크립트 오탐 방지).
    try:
        body = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        return False
    return any(h in body for h in BLOCK_HINTS)


def _open_followers(driver, user):
    """프로필의 '팔로워' 링크를 눌러 팔로워 모달을 연다(/followers/ URL 단독으론 안 열림)."""
    driver.get(f"https://www.instagram.com/{user}/")
    time.sleep(random.uniform(3.5, 5.0))
    shot(driver, "followback_profile")
    # 인스타 개편으로 팔로워 카운트가 <a href=.../followers/> 가 아니라 클릭 가능한 텍스트다.
    # '팔로워' 글자를 포함한 요소를 클릭하면 팔로워 모달(dialog)이 열린다.
    opened = False
    for e in driver.find_elements(By.XPATH, "//*[contains(text(),'팔로워')]"):
        try:
            ActionChains(driver).move_to_element(e).click().perform()
            WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']")))
            opened = True
            break
        except Exception:
            continue
    if not opened:
        log("팔로워 모달을 열지 못했습니다(로그인/DOM 확인 필요).")
    time.sleep(random.uniform(2.0, 3.5))


def _scroll_dialog(driver, times=1):
    """팔로워 모달 리스트를 조금 더 로드한다."""
    try:
        box = driver.find_element(
            By.XPATH, "//div[@role='dialog']//div[contains(@style,'overflow')][last()]")
    except Exception:
        box = None
    for _ in range(times):
        if box is not None:
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", box)
        else:
            driver.execute_script("window.scrollBy(0, 600)")
        time.sleep(random.uniform(1.2, 2.2))


def _follow_buttons(driver):
    # 팔로워 모달 안에서 '팔로우'(맞팔 안 한 팔로워) 버튼만. '팔로잉/팔로우 취소'는 제외.
    return driver.find_elements(
        By.XPATH,
        "//div[@role='dialog']//button[normalize-space()='팔로우' or normalize-space()='Follow']")


def run(dry_run=None):
    cfg = load_config()
    fb = cfg.get("follow_back", {})
    if dry_run is None:
        dry_run = fb.get("dry_run", True)
    if not dry_run and not fb.get("enabled", False):
        log("follow_back.enabled=false → 실제 맞팔 중단, dry-run 으로만 확인합니다.")
        dry_run = True

    user = (cfg.get("instagram", {}) or {}).get("username", "").strip()
    if not user:
        log("config.instagram.username 이 없어 중단."); return {"status": "no_user"}

    limit = int(fb.get("daily_limit", 15))
    st = _load_state()
    used = int(st.get(_today(), 0))
    remaining = max(0, limit - used)
    lo, hi = float(fb.get("min_delay", 35)), float(fb.get("max_delay", 95))
    log(f"자동 맞팔 시작 (dry_run={dry_run}) — 오늘 {used}/{limit}, 이번에 최대 {remaining}명")
    if remaining <= 0:
        log("오늘 한도 소진 → 종료"); return {"status": "limit_reached", "done": 0}

    driver = build_driver(headless=False)   # supervised: 화면을 보며 진행
    done = 0
    try:
        _open_followers(driver, user)
        shot(driver, "followback_open")
        if _blocked(driver):
            shot(driver, "followback_blocked"); log("⚠ 차단/챌린지 감지 → 중단")
            return {"status": "blocked", "done": 0}

        _scroll_dialog(driver, times=3)      # 초기 몇 명 로드
        if dry_run:                          # 진단: 모달·버튼 라벨 분포 확인
            dlgs = driver.find_elements(By.XPATH, "//div[@role='dialog']")
            labels = {}
            for bt in driver.find_elements(By.XPATH, "//div[@role='dialog']//button"):
                t = (bt.text or "").strip()
                if t:
                    labels[t] = labels.get(t, 0) + 1
            log(f"[진단] dialog {len(dlgs)}개, 모달 내 버튼 라벨: {labels}")
        target = remaining
        while done < target:
            btns = _follow_buttons(driver)
            if not btns:
                _scroll_dialog(driver, times=2)
                btns = _follow_buttons(driver)
                if not btns:
                    log("더 이상 맞팔 대상이 없습니다."); break
            if dry_run:
                log(f"[DRY-RUN] 맞팔 대상 최소 {len(btns)}명 감지 — 실제 클릭하지 않음.")
                shot(driver, "followback_dryrun")
                break
            b = btns[0]
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", b)
                time.sleep(random.uniform(0.6, 1.4))
                b.click()
            except Exception as e:
                log(f"클릭 실패(건너뜀): {type(e).__name__}")
                time.sleep(1.0)
                continue
            time.sleep(random.uniform(2.0, 4.0))
            if _blocked(driver):
                shot(driver, "followback_blocked"); log("⚠ 차단 감지 → 즉시 중단"); break
            done += 1
            st[_today()] = used + done
            _save_state(st)
            log(f"  맞팔 {done}/{target}")
            time.sleep(random.uniform(lo, hi))   # 사람처럼 긴 간격
        shot(driver, "followback_done")
    finally:
        driver.quit()
    log(f"자동 맞팔 종료 — 이번 {done}명, 오늘 누적 {used + done}/{limit}")
    return {"status": "ok", "done": done}


if __name__ == "__main__":
    go = "--go" in sys.argv
    print(json.dumps(run(dry_run=not go), ensure_ascii=False))
