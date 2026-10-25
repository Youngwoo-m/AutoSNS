"""네이버 블로그 게시물별 누적 조회수·공감·댓글을 붙인다. naver-blog-auto/.venv 로 실행할 것.

collect_web.py 가 공개 목록으로 모은 snapshots/parts/blog.json 에 수치만 덧붙인다
(그래서 collect_web 다음에 돌린다). 조회수는 공개 화면에 없고 블로그 주인만 보는
'내 블로그 통계'에 있다 — 발행에 쓰는 로그인된 크롬 프로필을 열어 읽기만 한다.

통계 화면이 부르는 내부 주소(2026-09-29 확인):
  https://blog.stat.naver.com/api/blog/article/cv?timeDimension=DATE&startDate=<오늘>&contentId=<글번호>
  → result.statDataList 의 dashboard.value = {cvTotal, likeTotal, commentTotal}
다른 도메인에서 부르면 CORS 로 막혀서, 통계 화면(blog.stat.naver.com)을 먼저 연 뒤
같은 출처에서 요청한다.

발행 작업(매일 19:00)과 같은 프로필을 쓰므로 그 시간대에는 돌리지 않는다.
"""
import json
import os
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "channels", "naver-blog-auto"))
from analytics.common import load_part, log, save_part   # noqa: E402

BLOG_ID = "studs23"
STAT_PAGE = f"https://blog.stat.naver.com/blog/daily/daily/cv?blogId={BLOG_ID}&isIE8=false"
JS_GET = """const x = new XMLHttpRequest(); x.open('GET', arguments[0], false);
try { x.send(); return x.status + '\\n' + x.responseText; } catch (e) { return '0\\n' + e; }"""


def _dashboard(d, log_no, today):
    raw = d.execute_script(JS_GET, f"/api/blog/article/cv?timeDimension=DATE&startDate={today}"
                                   f"&contentId={log_no}&exclude=")
    status, _, body = raw.partition("\n")
    if status != "200":
        raise RuntimeError(f"http {status}: {body[:120]}")
    for s in json.loads(body)["result"]["statDataList"]:
        if s.get("dataId") == "dashboard":
            return s["data"]["value"]
    raise RuntimeError("dashboard 항목 없음")


def main():
    part = load_part("blog")
    if not part or not part.get("items"):
        log("네이버 통계: blog.json 이 없다 — collect_web.py 를 먼저 돌릴 것")
        return 1
    from publish_naver import build_driver
    d = build_driver(headless=True)
    today = datetime.now().strftime("%Y-%m-%d")
    ok = fail = 0
    try:
        d.get(STAT_PAGE)
        time.sleep(5)
        if "blog.stat.naver.com" not in d.current_url:
            log(f"네이버 통계: 통계 화면이 열리지 않음(로그인 만료?) → {d.current_url}")
            return 1
        for it in part["items"]:
            log_no = it["url"].rstrip("/").split("/")[-1]
            try:
                v = _dashboard(d, log_no, today)
                it["views"] = int(v.get("cvTotal") or 0)
                it["likes"] = int(v.get("likeTotal") or 0)
                it["comments"] = int(v.get("commentTotal") or 0)
                ok += 1
            except Exception as e:
                fail += 1
                if fail <= 3:
                    log(f"네이버 통계 실패 {log_no}: {type(e).__name__}: {str(e)[:100]}")
                if fail >= 10 and ok == 0:
                    log("네이버 통계: 연속 실패 — 중단(이전 수치 유지)")
                    return 1
            time.sleep(0.3)
    finally:
        d.quit()
    part["views_at"] = today
    save_part("blog", part)
    total = sum(x.get("views", 0) for x in part["items"])
    log(f"네이버 블로그 조회수: {ok}건 반영, 실패 {fail}건, 누적 합계 {total:,}회")
    return 0


if __name__ == "__main__":
    sys.exit(main())
