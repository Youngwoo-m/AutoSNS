"""GeoAI 블로그(geoaina.blogspot.com) 최초 인증 — 사용자가 직접 1회 실행.

    ./.venv/bin/python geoai_auth_setup.py

브라우저가 열리면 **geoaina 블로그를 소유한 구글 계정**으로 로그인한다
(학과 블로그용 ds2eye 계정이 아니다 — 계정을 잘못 고르면 발행 때 403 이 난다).
성공하면 token_blogger_geoai.json 이 생기고, 이후에는 자동 갱신된다.

OAuth 클라이언트는 유튜브·Blogger 와 같은 client_secret.json 을 쓴다. 이 클라이언트가
'테스트' 상태라면 구글 클라우드 콘솔 > OAuth 동의 화면 > 테스트 사용자에 그 계정을
먼저 추가해야 로그인이 통과된다(403: access_denied 가 나오면 이 경우다).
"""
import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from common import load_config
from post_blogger import CLIENT_SECRET, SCOPES
from geoai_blogger import TOKEN_PATH, blog_id

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import token_store  # noqa: E402  OAuth 클라이언트는 암호화 저장소(GOOGLE_OAUTH_CLIENT)에

if not token_store.exists(CLIENT_SECRET):
    raise SystemExit("client_secret.json(GOOGLE_OAUTH_CLIENT) 을 찾을 수 없습니다")
import blogger_token  # noqa: E402
if blogger_token.exists(TOKEN_PATH):
    ans = input(f"{os.path.basename(TOKEN_PATH)} 이 이미 있습니다. 다시 인증할까요? [y/N] ")
    if ans.strip().lower() not in ("y", "yes"):
        raise SystemExit("취소했습니다.")

print("브라우저에서 **geoaina.blogspot.com 소유 계정**으로 로그인하세요.")
# prompt='consent' + 계정 선택을 강제해 '이미 로그인된 다른 계정'으로 새어나가지 않게 한다.
flow = InstalledAppFlow.from_client_config(token_store.client_config(CLIENT_SECRET), SCOPES)
c = flow.run_local_server(port=0, prompt="consent select_account")
blogger_token.save(TOKEN_PATH, c.to_json())           # 평문 파일 대신 암호화 저장소
print("토큰 저장:", blogger_token.secret_name(TOKEN_PATH))

# 인증한 계정이 정말 그 블로그에 글을 쓸 수 있는지 즉시 확인한다(나중에 발행 때 403 나는 걸 막는다).
cfg = load_config()
svc = build("blogger", "v3", credentials=c, cache_discovery=False)
bid = blog_id(cfg)
try:
    b = svc.blogs().get(blogId=bid).execute()
    svc.posts().list(blogId=bid, maxResults=1, view="ADMIN", status=["DRAFT", "LIVE"],
                     fetchBodies=False, fields="items(title)").execute()
    print(f"쓰기 권한 확인 완료 — {b.get('name')} ({b.get('url')})")
except Exception as e:
    print(f"주의: 이 계정으로는 블로그에 글을 쓸 수 없습니다 — {str(e)[:150]}")
    print("→ 다른 계정(블로그 소유자)으로 다시 실행하거나, Blogger 설정 > 권한에서 작성자로 추가하세요.")
