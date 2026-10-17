"""최초 1회: Google 계정으로 로그인해 업로드 권한 토큰(token.json)을 저장한다.

사전 준비(최초 1회, 사용자):
  1) https://console.cloud.google.com 에서 프로젝트 생성
  2) 'YouTube Data API v3' 사용 설정
  3) OAuth 동의 화면 구성(외부/테스트 → 본인 계정을 테스트 사용자로 추가)
  4) 사용자 인증 정보 → OAuth 클라이언트 ID → '데스크톱 앱' 생성 → JSON 다운로드
  5) 그 JSON 을 이 폴더에 client_secret.json 으로 저장

그다음 이 스크립트를 실행하면 브라우저가 열리고, 업로드할 유튜브 계정
(semyungds@gmail.com)으로 로그인/동의하면 token.json 이 저장된다.
토큰은 refresh_token 으로 자동 갱신되므로 보통 한 번만 하면 된다.
"""
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from common import CLIENT_SECRET_PATH, TOKEN_PATH, log
from youtube_upload import SCOPES  # 업로드+읽기+애널리틱스+댓글(force-ssl) 단일 정의 재사용


def main():
    # OAuth 클라이언트·토큰은 암호화 저장소에 있다(shared/token_store.py).
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from shared import token_store
    if not token_store.exists(CLIENT_SECRET_PATH):
        raise SystemExit(
            "client_secret.json 이 없습니다.\n"
            "Google Cloud Console 에서 '데스크톱 앱' OAuth 클라이언트 JSON 을 받아\n"
            f"{CLIENT_SECRET_PATH} 로 저장한 뒤 다시 실행하세요.\n"
            "(자세한 절차는 이 파일 상단 주석 / README 참고)"
        )
    flow = InstalledAppFlow.from_client_config(token_store.client_config(CLIENT_SECRET_PATH), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    where = token_store.write_text(TOKEN_PATH, creds.to_json())
    log(f"인증 완료. 토큰 저장됨: {token_store.name_for(TOKEN_PATH)} ({where})")
    print("\n로그인/인증 완료! 이제 업로드가 가능합니다.")


if __name__ == "__main__":
    main()
