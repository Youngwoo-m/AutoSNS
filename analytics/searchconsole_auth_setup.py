"""서치콘솔 최초 인증(사용자가 직접 1회 실행).

    python searchconsole_auth_setup.py
"""
import os

from google_auth_oauthlib.flow import InstalledAppFlow

from collect_searchconsole import CLIENT_SECRET, SCOPES, TOKEN_PATH

if not os.path.exists(CLIENT_SECRET):
    raise SystemExit(f"client_secret.json 없음: {CLIENT_SECRET}")
flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
creds = flow.run_local_server(port=0, prompt="consent")
with open(TOKEN_PATH, "w", encoding="utf-8") as f:
    f.write(creds.to_json())
print("완료:", TOKEN_PATH)
