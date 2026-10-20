"""공용 모듈 재수출 shim. 실제 구현은 ../shared/ieum_feed.py 에 있다."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.ieum_feed import fetch_ieum_news  # noqa: E402,F401
