"""개인 GeoAI 유튜브 채널(@geoai-safety) 최초 인증 — 사용자가 직접 1회 실행.

    ./.venv/bin/python geoai_youtube_auth.py

브라우저가 열리면 **@geoai-safety 채널을 소유한 구글 계정**으로 로그인한다
(학과 채널 semyungds 계정이 아니다). 성공하면 token_youtube_geoai.json 이 생기고,
어느 채널에 연결됐는지 즉시 확인해서 보여준다 — 계정을 잘못 고르면 여기서 걸린다.

같은 OAuth 클라이언트(client_secret.json)를 쓴다. 클라이언트가 '테스트' 상태라면
구글 클라우드 콘솔 > OAuth 동의 화면 > 테스트 사용자에 그 계정이 있어야 한다.
"""
import os

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from common import BASE_DIR, CLIENT_SECRET_PATH
from youtube_upload import SCOPES

TOKEN_PATH = os.path.join(BASE_DIR, "token_youtube_geoai.json")
WANT_HANDLE = "geoai-safety"   # 2026-09-16 사용자가 @geoai-na 에서 바꿈

if not os.path.exists(CLIENT_SECRET_PATH):
    raise SystemExit(f"client_secret.json 이 없습니다: {CLIENT_SECRET_PATH}")
if os.path.exists(TOKEN_PATH):
    ans = input(f"{os.path.basename(TOKEN_PATH)} 이 이미 있습니다. 다시 인증할까요? [y/N] ")
    if ans.strip().lower() not in ("y", "yes"):
        raise SystemExit("취소했습니다.")

print(f"브라우저에서 **@{WANT_HANDLE} 채널 소유 계정**으로 로그인하세요.")
flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
creds = flow.run_local_server(port=0, prompt="consent select_account")
with open(TOKEN_PATH, "w", encoding="utf-8") as f:
    f.write(creds.to_json())
print("토큰 저장:", TOKEN_PATH)

yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
r = yt.channels().list(part="snippet,contentDetails", mine=True).execute()
items = r.get("items", [])
if not items:
    print("주의: 이 계정에 유튜브 채널이 없습니다. 채널을 만든 뒤 다시 실행하세요.")
else:
    sn = items[0]["snippet"]
    handle = (sn.get("customUrl") or "").lstrip("@")
    print(f"연결된 채널: {sn.get('title')} (@{handle or '핸들없음'}) / id={items[0]['id']}")
    if handle and handle.lower() != WANT_HANDLE:
        print(f"주의: 원하는 채널(@{WANT_HANDLE})이 아닙니다 — 다른 계정으로 다시 실행하세요.")
    else:
        print("확인 완료 — 이 채널로 업로드합니다.")
