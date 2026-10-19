"""공용 모듈 재수출 shim. 실제 구현은 ../shared/fetch_news.py 에 있다(2026-10-19 세 모듈의 복사본을 합침)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.fetch_news import (_norm_title, fetch_news, fetch_recent_raw, main)  # noqa: E402,F401

if __name__ == "__main__":
    main()
