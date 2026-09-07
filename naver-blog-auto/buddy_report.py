"""서로이웃 선신청 결과 집계 → 카카오톡 알림.

'내가 추가한 이웃' 관리 목록(BuddyListManage.naver)에서 blogId·관계(서로이웃/이웃)를
읽어, buddy_request_state.json 의 sent 목록과 대조해 수락 현황을 집계한다.

  수락   : 목록에 있고 관계가 '서로이웃'      (선신청이 받아들여짐)
  일방   : 목록에 있고 관계가 '이웃'          (상대가 서로이웃은 거절/미설정)
  대기   : 목록에 없음                        (아직 응답 없음 또는 거절)

수락 상태는 state 에 누적 기록해, 다음 주에는 '이번 주 새로 수락된 수'를 낼 수 있다.
읽기 전용(목록 조회)만 하며, 실패해도 선신청 작업 자체에는 영향을 주지 않는다.

사용: python buddy_report.py [--no-kakao]
"""
import json
import os
import re
import sys
import time

from selenium.webdriver.common.by import By

from common import log
from naver_buddy_request import STATE, _load_state, _save_state
from publish_naver import build_driver

LIST_URL = "https://admin.blog.naver.com/BuddyListManage.naver?blogId=studs23&currentPage={page}"
MAX_PAGES = 20


def fetch_relations(driver):
    """{blogId: '서로이웃'|'이웃'} — 내가 추가한 이웃 전체(페이지 순회)."""
    rel = {}
    for page in range(1, MAX_PAGES + 1):
        driver.get(LIST_URL.format(page=page))
        time.sleep(2.5)
        rows = driver.find_elements(By.XPATH, "//tr[.//input[@type='checkbox']]")
        found = 0
        for r in rows:
            txt = " ".join(r.text.split())
            bid = ""
            for a in r.find_elements(By.XPATH, ".//a"):
                h = a.get_attribute("href") or ""
                m = (re.search(r"blog\.naver\.com/([A-Za-z0-9_-]+)", h)
                     or re.search(r"blogId=([A-Za-z0-9_-]+)", h))
                if m and m.group(1) != "studs23":
                    bid = m.group(1)
                    break
            if not bid or bid in rel:
                continue
            rel[bid] = "서로이웃" if "서로이웃" in txt else "이웃"
            found += 1
        if not found:            # 빈 페이지 = 목록 끝
            break
    return rel


def summarize(rel, st):
    """sent 목록 대비 수락/일방/대기 집계 + 이번 회차에 새로 수락된 대상."""
    sent = list(dict.fromkeys(st.get("sent", [])))
    known = set(st.get("accepted", []))
    accepted = [b for b in sent if rel.get(b) == "서로이웃"]
    oneway = [b for b in sent if rel.get(b) == "이웃"]
    pending = [b for b in sent if b not in rel]
    return {
        "sent": sent, "accepted": accepted, "oneway": oneway, "pending": pending,
        "new_accepted": [b for b in accepted if b not in known],
        "total_buddies": sum(1 for v in rel.values() if v == "서로이웃"),
    }


def report_text(s):
    n = len(s["sent"]) or 1
    lines = [
        "[SMUDS 서로이웃 현황]",
        f"신청 누적 {len(s['sent'])}명 → 수락 {len(s['accepted'])}명"
        f"({len(s['accepted'])*100//n}%), 일방이웃 {len(s['oneway'])}명, 대기 {len(s['pending'])}명",
        f"블로그 전체 서로이웃 {s['total_buddies']}명",
    ]
    if s["new_accepted"]:
        lines.append("이번에 새로 수락: " + ", ".join(s["new_accepted"][:10]))
    return "\n".join(lines)


def run(send_kakao=True):
    st = _load_state()
    if not st.get("sent"):
        log("선신청 이력이 없어 집계를 건너뜁니다.")
        return {"status": "no_sent"}
    driver = build_driver(headless=True)
    try:
        rel = fetch_relations(driver)
    finally:
        driver.quit()
    log(f"이웃 목록 {len(rel)}명 조회")
    s = summarize(rel, st)
    st["accepted"] = s["accepted"]
    st["checked_at"] = time.strftime("%Y-%m-%d %H:%M")
    _save_state(st)
    text = report_text(s)
    log(text.replace("\n", " | "))
    if send_kakao:
        try:
            from kakao_notify import notify
            log(f"카톡 알림: {notify(text, 'https://admin.blog.naver.com/studs23/buddy/relation')}")
        except Exception as e:
            log(f"카톡 알림 건너뜀: {type(e).__name__}: {e}")
    return {"status": "ok", **{k: len(v) for k, v in s.items() if isinstance(v, list)}}


if __name__ == "__main__":
    print(json.dumps(run(send_kakao="--no-kakao" not in sys.argv), ensure_ascii=False))
