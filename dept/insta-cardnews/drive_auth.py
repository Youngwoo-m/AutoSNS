"""인스타 릴을 구글 드라이브에 올릴 토큰을 만든다(2026-11-25 사용자 지시: 릴은 줄이지 않고 드라이브 링크로).

개인 계정(config instagram.email_from)으로 drive.file 권한만 받는다 — 이 앱이 올린 파일만 다룰 수 있다.
SMUD 설치형 클라이언트(암호화 저장소 GOOGLE_OAUTH_CLIENT)의 localhost 리디렉션을 쓴다.
    python drive_auth.py      # 로그인 주소를 drive_auth_url.txt 에 쓰고, 브라우저에서 허용하면 토큰 저장
"""
import json
import os
import sys

from common import BASE_DIR

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "common"))
from shared.secret_get import get  # noqa: E402
from shared import token_store  # noqa: E402

TOKEN = "token_drive_insta.json"          # 암호화 저장소 TOKEN_TOKEN_DRIVE_INSTA
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

if __name__ == "__main__":
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_config(json.loads(get("GOOGLE_OAUTH_CLIENT")), SCOPES)
    port = 8799 if len(sys.argv) < 2 else int(sys.argv[1])
    msg = os.path.join(BASE_DIR, "drive_auth_url.txt")

    class _W:                                   # run_local_server 가 찍는 주소를 파일로 받는다
        def write(self, s):
            if "https://" in s:
                with open(msg, "w", encoding="utf-8") as f:
                    f.write(s[s.index("https://"):].split()[0])

        def flush(self):
            pass
    import contextlib
    with contextlib.redirect_stdout(_W()):
        creds = flow.run_local_server(port=port, open_browser=False, authorization_prompt_message="{url}",
                                      success_message="허용 완료 — 이 창을 닫아도 됩니다.")
    os.remove(msg)
    token_store.write_text(TOKEN, creds.to_json())
    print("저장 완료")
