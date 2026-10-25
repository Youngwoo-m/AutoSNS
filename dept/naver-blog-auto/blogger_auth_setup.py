"""Blogger 최초 인증(사용자가 직접 1회 실행).

브라우저가 열리면 구글 계정으로 로그인하고 권한을 허용한다.
성공하면 token_blogger.json 이 생기고, 이후에는 자동 갱신된다.

    python blogger_auth_setup.py
"""
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from post_blogger import CLIENT_SECRET, SCOPES, _token_path

TOKEN_PATH = _token_path()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared import token_store  # noqa: E402  OAuth 클라이언트는 암호화 저장소(GOOGLE_OAUTH_CLIENT)에

if not token_store.exists(CLIENT_SECRET):
    raise SystemExit("client_secret.json(GOOGLE_OAUTH_CLIENT) 을 찾을 수 없습니다")
flow = InstalledAppFlow.from_client_config(token_store.client_config(CLIENT_SECRET), SCOPES)
creds = flow.run_local_server(port=0, prompt="consent")
import blogger_token  # noqa: E402
blogger_token.save(TOKEN_PATH, creds.to_json())       # 평문 파일 대신 암호화 저장소
print("완료:", blogger_token.secret_name(TOKEN_PATH))
