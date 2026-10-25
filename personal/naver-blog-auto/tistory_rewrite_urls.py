"""티스토리(na-geoai) 공개 글에 박힌 이미지 저장소 주소를 새 주소로 고친다 — geoai-assets 이전(SMUDS-m → Youngwoo-m)용.

공개 글을 훑어 옛 주소가 든 글을 찾고, 그 글의 편집 화면(기존 seo_edit 와 같은 길)에서 본문 속 주소만 바꿔 다시 저장한다.
제목·카테고리·공개 상태·태그는 건드리지 않는다. profile:tistory 잠금을 잡고 돈다.

    ./.venv/bin/python tistory_rewrite_urls.py --plan               # 어떤 글이 해당하는지만
    ./.venv/bin/python tistory_rewrite_urls.py --dry --limit 1      # 편집 화면까지 채우고 저장 직전에 멈춤
    ./.venv/bin/python tistory_rewrite_urls.py --go                 # 실제 수정(글마다 저장 뒤 공개 페이지로 확인)

원본 본문은 backups/asset_urls_<날짜>/tistory/<글번호>.html 에 먼저 저장한다.
"""
import argparse
import concurrent.futures
import datetime
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
from common import log  # noqa: E402
import tistory_crosspost as tc  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
OLD, NEW = "SMUDS-m/geoai-assets", "Youngwoo-m/geoai-assets"
BK = os.path.join(ROOT, "backups", f"asset_urls_{datetime.date.today():%Y%m%d}", "tistory")


def public_count(n):
    try:
        h = urllib.request.urlopen(urllib.request.Request(f"{tc.BLOG}/{n}", headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read().decode("utf-8", "ignore")
        return n, h.count(OLD), h.count(NEW)
    except Exception:
        return n, -1, -1


def find_posts(last=200):
    with concurrent.futures.ThreadPoolExecutor(8) as ex:
        rs = list(ex.map(public_count, range(1, last + 1)))
    return [n for n, o, _ in rs if o > 0]


def edit_one(d, n, go):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    W = WebDriverWait(d, 25)
    d.get(f"{tc.BLOG}/manage/newpost/{n}?type=post&returnURL=ENTRY")
    if "/manage/newpost" not in tc._cur_url(d) and tc.kakao_relogin(d):
        d.get(f"{tc.BLOG}/manage/newpost/{n}?type=post&returnURL=ENTRY")
    W.until(lambda x: x.execute_script("return !!(window.tinymce && tinymce.activeEditor && tinymce.activeEditor.initialized)"))
    time.sleep(1.5)
    cur = d.execute_script("return tinymce.activeEditor.getContent();")
    c = cur.count(OLD)
    if not c:
        return f"편집 본문에 옛 주소 없음(공개 글에만 있음?) — 건너뜀"
    os.makedirs(BK, exist_ok=True)
    open(os.path.join(BK, f"{n}.html"), "w", encoding="utf-8").write(cur)
    d.execute_script("tinymce.activeEditor.setContent(arguments[0]); tinymce.activeEditor.fire('change');"
                     "tinymce.activeEditor.save();", cur.replace(OLD, NEW))
    after = d.execute_script("return tinymce.activeEditor.getContent();")
    if OLD in after or after.count(NEW) < c:
        raise RuntimeError(f"본문 바꾸기가 어긋남(옛 {after.count(OLD)}, 새 {after.count(NEW)}/{c}) — 저장하지 않음")
    if not go:
        return f"dry-ok ({c}곳)"
    d.execute_script("arguments[0].click();", d.find_element(By.ID, "publish-layer-btn"))
    W.until(EC.presence_of_element_located((By.ID, "publish-btn")))
    time.sleep(0.8)
    d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();",
                     d.find_element(By.ID, "publish-btn"))
    W.until(lambda x: "/manage/newpost" not in x.current_url)
    time.sleep(3)
    _, o, nw = public_count(n)
    if o != 0 or nw < c:
        raise RuntimeError(f"저장은 했지만 공개 글에서 확인 안 됨(옛 {o}, 새 {nw}/{c})")
    return f"saved ({c}곳)"


def main():
    ap = argparse.ArgumentParser(description="티스토리 글의 이미지 저장소 주소 고치기")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true")
    g.add_argument("--dry", action="store_true")
    g.add_argument("--go", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", type=int, nargs="*", help="이 글 번호만")
    a = ap.parse_args()
    nums = a.only or find_posts()
    if a.limit:
        nums = nums[:a.limit]
    print(f"해당 글 {len(nums)}편: {nums}")
    if a.plan:
        return 0
    from shared.axlock import hold, stopped
    if a.go and stopped():
        print("비상 정지 중이라 수정하지 않았습니다")
        return 1
    ok = bad = 0
    with hold(["profile:tistory"], job="tistory_rewrite_urls", wait=2400):
        os.environ["AX_LOCKED"] = "1"
        d = tc.build_driver(headless=True)
        try:
            for n in nums:
                try:
                    r = edit_one(d, n, a.go)
                    ok += 1
                    log(f"  티스토리 /{n}: {r}")
                    print(f"  /{n}: {r}")
                except Exception as e:
                    bad += 1
                    log(f"  티스토리 /{n} 실패: {type(e).__name__}: {str(e)[:150]}")
                    print(f"  /{n} 실패: {type(e).__name__}: {str(e)[:150]}")
        finally:
            tc.close(d)
    print(f"끝: 성공 {ok}편, 실패 {bad}편")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
