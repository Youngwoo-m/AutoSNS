"""사이트 + 함수 배포 (Firebase). 옛 Netlify 방식은 2026-11-05 에 이 방식으로 바뀌었다.

  python3 deploy_full.py          # 사이트·함수·규칙 배포
  python3 deploy_full.py --check  # 배포 안 하고 대상만 보고 끝
함수 키(DATA_GO_KR_KEY·KAKAO_REST_KEY·COLLECTOR_KEY)는 Firebase Secret Manager 에 있다(사이트 파일에 없음).
"""
import sys
from firebase_api import deploy, SITE_DIR

def main():
    if "--check" in sys.argv:
        print("deploy target:", SITE_DIR, "-> project geoai-na"); return
    deploy()

if __name__ == "__main__":
    main()
