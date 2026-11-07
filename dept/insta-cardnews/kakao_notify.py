"""공용 모듈 재수출 shim. 실제 구현은 ../shared/kakao_notify.py 에 있다(2026-11-06 세 모듈의 복사본을 합침)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.kakao_notify import TOKEN_PATH, notify  # noqa: E402,F401

if __name__ == "__main__":
    a = sys.argv[1:]
    import json
    print(json.dumps(notify(a[0] if a else "[SMUDS] 카카오 알림 테스트 ✅", a[1] if len(a) > 1 else None), ensure_ascii=False))
