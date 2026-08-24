"""공용 모듈 재수출 shim. 실제 구현은 ../shared/esri_feed.py 에 있다."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.esri_feed import fetch_esri_blog  # noqa: E402,F401
