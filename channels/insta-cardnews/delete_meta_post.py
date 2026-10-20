"""인스타그램·스레드에서 본문에 특정 문구가 든 최근 게시물을 찾아(선택) 삭제한다.

  .venv/bin/python delete_meta_post.py instagram "가을 산, 작은 불씨"          # 찾기만(스크린샷)
  .venv/bin/python delete_meta_post.py instagram "가을 산, 작은 불씨" --go     # 찾은 1개 삭제
  .venv/bin/python delete_meta_post.py threads   "가을 산, 작은 불씨" --go
같은 문구가 든 게시물이 2개 이상이면 지우지 않고 멈춘다(엉뚱한 글 삭제 방지).
로그인 세션은 게시용 크롬 프로필(chrome-profile-insta)을 그대로 쓴다.
"""
import sys
import time

from selenium.webdriver.common.by import By

from common import load_config, log
from post_instagram import build_driver, shot, _click_by_labels

DEL = ["삭제", "Delete"]
MORE = ["옵션 더 보기", "More options", "더 보기", "More"]


def _visible_text(d):
    try:
        return d.find_element(By.TAG_NAME, "body").text
    except Exception:
        return ""


def _click_more(d):
    """게시물의 '…'(옵션 더 보기) 버튼 — aria-label 이 붙은 svg 의 버튼을 누른다."""
    for lab in MORE:
        for el in d.find_elements(By.CSS_SELECTOR, f"svg[aria-label='{lab}']"):
            try:
                btn = el.find_element(By.XPATH, "./ancestor::*[@role='button' or self::button][1]")
                if btn.is_displayed():
                    d.execute_script("arguments[0].click();", btn)
                    return True
            except Exception:
                continue
    return False


def instagram(d, needle, go):
    user = load_config().get("instagram", {}).get("username", "smu_ds_official")
    d.get(f"https://www.instagram.com/{user}/reels/")
    time.sleep(7)
    links = []
    for a in d.find_elements(By.CSS_SELECTOR, "a[href*='/reel/'], a[href*='/p/']"):
        h = a.get_attribute("href") or ""
        if h and h not in links:
            links.append(h)
    log(f"인스타 최근 게시물 {len(links)}개 확인")
    hits = []
    for h in links[:9]:
        d.get(h); time.sleep(5)
        if needle in _visible_text(d):
            hits.append(h)
    log(f"'{needle}' 포함 게시물: {hits}")
    if len(hits) != 1:
        shot(d, "del_ig_ambiguous"); return f"멈춤: 일치 {len(hits)}개"
    d.get(hits[0]); time.sleep(5); shot(d, "del_ig_found")
    if not go:
        return f"찾음(삭제 안 함): {hits[0]}"
    if not _click_more(d):
        shot(d, "del_ig_no_more"); return "멈춤: '옵션 더 보기' 버튼 못 찾음"
    time.sleep(2); shot(d, "del_ig_menu")
    if not _click_by_labels(d, DEL, timeout=5):
        return "멈춤: 메뉴에 '삭제' 없음"
    time.sleep(2); shot(d, "del_ig_confirm")
    if not _click_by_labels(d, DEL, timeout=5):
        return "멈춤: 확인 창 '삭제' 못 누름"
    time.sleep(5); shot(d, "del_ig_after")
    return f"삭제함: {hits[0]}"


def threads(d, needle, go):
    d.get("https://www.threads.com/")
    time.sleep(6)
    _click_by_labels(d, ["프로필", "Profile"], timeout=5)
    time.sleep(6)
    shot(d, "del_th_profile")
    posts = [el for el in d.find_elements(By.CSS_SELECTOR, "div[data-pressable-container='true']")
             if needle in (el.text or "")]
    log(f"스레드 '{needle}' 포함 게시물 {len(posts)}개")
    if len(posts) != 1:
        return f"멈춤: 일치 {len(posts)}개"
    post = posts[0]
    d.execute_script("arguments[0].scrollIntoView({block:'center'});", post)
    time.sleep(1); shot(d, "del_th_found")
    if not go:
        return "찾음(삭제 안 함)"
    more = None
    for lab in MORE:
        els = post.find_elements(By.CSS_SELECTOR, f"svg[aria-label='{lab}']")
        if els:
            more = els[0].find_element(By.XPATH, "./ancestor::*[@role='button' or self::button][1]"); break
    if more is None:
        return "멈춤: '더 보기' 버튼 못 찾음"
    d.execute_script("arguments[0].click();", more)
    time.sleep(2); shot(d, "del_th_menu")
    if not _click_by_labels(d, DEL, timeout=5):
        return "멈춤: 메뉴에 '삭제' 없음"
    time.sleep(2); shot(d, "del_th_confirm")
    if not _click_by_labels(d, DEL, timeout=5):
        return "멈춤: 확인 창 '삭제' 못 누름"
    time.sleep(4); shot(d, "del_th_after")
    return "삭제함"


if __name__ == "__main__":
    where, needle = sys.argv[1], sys.argv[2]
    go = "--go" in sys.argv
    d = build_driver(False)
    try:
        r = (instagram if where == "instagram" else threads)(d, needle, go)
        log(f"{where}: {r}")
        print(r)
    finally:
        d.quit()
