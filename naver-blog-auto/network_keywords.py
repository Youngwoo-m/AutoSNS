"""네이버 '이웃새글' 피드에서 재난 관련 검색어를 뽑는다.

목적: 재난 관련 이웃이 지금 쓰는 글의 주제를 뉴스 검색어에 더한다.
핵심: 이웃 글은 요리·일상 등 재난과 무관한 게 대부분이므로, 반드시 '재난 키워드가
     든 제목'만 골라 '지역+재난' 조합으로만 뽑는다(검색 오염 방지).

네이버는 이웃새글 공식 API 가 없어, 로그인된 크롬 프로필로 피드를 읽는다(스크래핑).
실패하거나 로그인 만료면 빈 목록을 돌려주어 뉴스 수집에 지장이 없게 한다.
"""
import os
import sys
import time

from selenium.webdriver.common.by import By

from common import log

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.keyword_terms import queries_from_titles  # noqa: E402

FEED_URL = ("https://section.blog.naver.com/BlogHome.naver"
            "?directoryNo=0&currentPage=1&groupId=0")


def naver_neighbor_keywords(limit=5):
    """이웃새글 제목에서 뽑은 재난 검색어 목록. 실패 시 []."""
    try:
        from publish_naver import build_driver
    except Exception:
        return []
    driver = None
    try:
        driver = build_driver(headless=True)
        driver.get(FEED_URL)
        time.sleep(6)
        if "nid.naver" in driver.current_url or "login" in driver.current_url.lower():
            log("이웃새글: 로그인 만료 → 건너뜀")
            return []
        titles = [e.text.strip() for e in driver.find_elements(By.CSS_SELECTOR, ".title")
                  if e.text.strip()]
        qs = queries_from_titles(titles)
        return qs[:limit]
    except Exception as e:
        log(f"이웃새글 키워드 수집 실패({type(e).__name__}) → 건너뜀")
        return []
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    kws = naver_neighbor_keywords()
    print("추출된 재난 검색어:", kws or "(없음 — 이웃 새글에 재난 주제가 없음)")
