"""서치콘솔 최초 인증(사용자가 직접 1회 실행).

    python searchconsole_auth_setup.py                 # 개인 계정(기본 토큰)
    python searchconsole_auth_setup.py dept            # 학과 계정 → token_searchconsole_dept.json

계정을 나누는 이유: 속성이 계정별로 등록되므로 토큰도 계정별로 있어야 양쪽을 함께
집계할 수 있다. 수집기는 token_searchconsole*.json 을 모두 읽는다.
브라우저 동의 화면에서 '어느 계정으로 로그인할지'를 사람이 고른다 — 비밀번호는
이 스크립트도, 다른 어떤 코드도 받지 않는다.
"""
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from collect_searchconsole import CLIENT_SECRET, SCOPES, TOKEN_PATH

suffix = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lstrip("_")
out = TOKEN_PATH if not suffix else TOKEN_PATH.replace(".json", f"_{suffix}.json")

if not os.path.exists(CLIENT_SECRET):
    raise SystemExit(f"client_secret.json 없음: {CLIENT_SECRET}")
if os.path.exists(out):
    ans = input(f"{os.path.basename(out)} 가 이미 있습니다. 덮어쓸까요? [y/N] ").strip().lower()
    if ans != "y":
        raise SystemExit("취소했습니다.")
flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
creds = flow.run_local_server(port=0, prompt="consent")
with open(out, "w", encoding="utf-8") as f:
    f.write(creds.to_json())
print("완료:", out)
