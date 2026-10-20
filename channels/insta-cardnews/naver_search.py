"""공용 모듈 재수출 shim. 실제 구현은 ../shared/naver_search.py 에 있다."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.naver_search import naver_blog_search, naver_news_search  # noqa: E402,F401
