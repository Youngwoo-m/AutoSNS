"""개인 GeoAI 유튜브 채널(@geoai-safety) 최초 인증 — 사용자가 직접 1회 실행.

    ./.venv/bin/python geoai_youtube_auth.py

브라우저가 열리면 **@geoai-safety 채널을 소유한 구글 계정**으로 로그인한다
(학과 채널 semyungds 계정이 아니다). 성공하면 token_youtube_geoai.json 이 생기고,
어느 채널에 연결됐는지 즉시 확인해서 보여준다 — 계정을 잘못 고르면 여기서 걸린다.

같은 OAuth 클라이언트(client_secret.json)를 쓴다. 클라이언트가 '테스트' 상태라면
구글 클라우드 콘솔 > OAuth 동의 화면 > 테스트 사용자에 그 계정이 있어야 한다.
"""
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from common import BASE_DIR, CLIENT_SECRET_PATH
from youtube_upload import SCOPES

TOKEN_PATH = os.path.join(BASE_DIR, "token_youtube_geoai.json")
WANT_HANDLE = "geoai-safety"   # 2026-09-16 사용자가 @geoai-na 에서 바꿈

sys.path.insert(0, os.path.dirname(os.path.dirname(BASE_DIR)))
from shared import token_store  # noqa: E402  OAuth 클라이언트·토큰은 암호화 저장소에

if not token_store.exists(CLIENT_SECRET_PATH):
    raise SystemExit("client_secret.json(GOOGLE_OAUTH_CLIENT) 이 없습니다")
if token_store.exists(TOKEN_PATH):
    ans = input(f"{os.path.basename(TOKEN_PATH)} 이 이미 있습니다. 다시 인증할까요? [y/N] ")
    if ans.strip().lower() not in ("y", "yes"):
        raise SystemExit("취소했습니다.")

print(f"브라우저에서 **@{WANT_HANDLE} 채널 소유 계정**으로 로그인하세요.")
flow = InstalledAppFlow.from_client_config(token_store.client_config(CLIENT_SECRET_PATH), SCOPES)
creds = flow.run_local_server(port=0, prompt="consent select_account")
token_store.write_text(TOKEN_PATH, creds.to_json())
print("토큰 저장:", token_store.name_for(TOKEN_PATH))

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
