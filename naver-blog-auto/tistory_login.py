"""최초 1회(또는 로그인이 풀렸을 때): 티스토리에 '직접' 로그인해 쿠키를 받아 둔다.

창이 뜨면 '카카오계정으로 로그인'으로 평소처럼 로그인한다(2단계 인증 포함).
티스토리 로그인 쿠키는 세션 쿠키라 Chrome 을 닫으면 프로필에서 사라진다 — 그래서 로그인을
감지하면 쿠키를 tistory_cookies.json 에 받아 두고(tistory_crosspost.save_cookies), 창을
새로 띄워 그 쿠키만으로 관리 화면이 열리는지까지 확인한다.
비밀번호는 어디에도 저장하지 않는다.
"""
import time

from tistory_crosspost import BLOG, build_driver, save_cookies
from common import log

TIMEOUT = 600


def logged_in(d):
    d.get(f"{BLOG}/manage")
    time.sleep(3)
    return "/manage" in d.current_url and "login" not in d.current_url


def main():
    d = build_driver(headless=False)
    if logged_in(d):
        log("받아 둔 쿠키로 아직 로그인돼 있지만, 카카오 '로그인 상태 유지'를 다시 받기 위해 새로 로그인합니다.")
        d.delete_all_cookies()
    d.get("https://www.tistory.com/auth/login")
    log("열린 창에서 '카카오계정으로 로그인'으로 로그인하세요. 최대 10분")
    waited = 0
    while waited < TIMEOUT:
        time.sleep(5)
        waited += 5
        if "TSSESSION" not in {c["name"] for c in d.get_cookies()}:
            continue
        if not logged_in(d):
            d.get("https://www.tistory.com/auth/login")
            continue
        kawlt = [c for c in d.execute_cdp_cmd("Network.getAllCookies", {})["cookies"]
                 if c["name"] == "_kawlt"]
        if not kawlt or kawlt[0].get("expires", -1) in (-1, 0):
            log("⚠ 카카오 '로그인 상태 유지'가 꺼져 있습니다. 티스토리 세션은 몇 시간이면 끊기고, "
                "그때 카카오 로그인으로 자동 재진입하려면 이게 켜져 있어야 합니다. "
                "티스토리에서 로그아웃 → 카카오 로그인 화면의 '로그인 상태 유지'를 켜고 다시 로그인해 주세요.")
            time.sleep(10)
            continue
        n = save_cookies(d)
        log(f"로그인 확인 — 쿠키 {n}개를 받아 뒀습니다. 창을 새로 열어 확인합니다...")
        d.quit()
        d = build_driver(headless=False)          # 받아 둔 쿠키를 넣고 뜬다
        ok = logged_in(d)
        d.quit()
        log("✅ 완료 — 새 창에서도 로그인돼 있습니다." if ok else
            "⚠ 새 창에서는 로그인이 안 됩니다. 다시 실행해 주세요.")
        return
    d.quit()
    log("시간 초과: 로그인이 감지되지 않았습니다. 다시 실행해 주세요.")


if __name__ == "__main__":
    main()
