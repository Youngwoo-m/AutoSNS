"""Blogger 최초 인증(사용자가 직접 1회 실행).

브라우저가 열리면 구글 계정으로 로그인하고 권한을 허용한다.
성공하면 token_blogger.json 이 생기고, 이후에는 자동 갱신된다.

    python blogger_auth_setup.py
"""
import os

from google_auth_oauthlib.flow import InstalledAppFlow

from post_blogger import CLIENT_SECRET, SCOPES, _token_path

TOKEN_PATH = _token_path()

if not os.path.exists(CLIENT_SECRET):
    raise SystemExit(f"client_secret.json 을 찾을 수 없습니다: {CLIENT_SECRET}")
flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
creds = flow.run_local_server(port=0, prompt="consent")
with open(TOKEN_PATH, "w", encoding="utf-8") as f:
    f.write(creds.to_json())
print("완료:", TOKEN_PATH)
