"""최초 1회: 스레드 계정으로 로그인해 발행 권한 토큰(threads_token.json)을 저장한다.

tiktok_login_setup.py 와 같은 방식이다. Redirect URI 가 https 여야 해서
localhost 를 못 쓰므로, 검증된 도메인의 콜백 페이지로 코드를 받아 수동으로
넘긴다.

사용법:
  1) 인증 URL 출력:          python threads_login_setup.py
     → 출력된 URL 로 로그인/동의 → 콜백 페이지에 표시된 'code' 복사
  2) 코드로 토큰 교환/저장:  python threads_login_setup.py --code <복사한코드>

사전 준비(Meta 개발자 포털 developers.facebook.com):
  · 앱 생성 후 'Threads API' 제품 추가
  · Redirect Callback URL = config.threads.redirect_uri 와 정확히 동일
  · 권한(scope): threads_basic, threads_content_publish
  · 앱이 개발 모드면 해당 스레드 계정을 테스터로 추가

토큰 수명: 단기 1시간 → 장기 60일로 교환해 저장한다. 장기 토큰은 만료 전에
refresh_access_token 으로 갱신되며, post_threads.py 가 발행 때마다 자동 확인한다.
"""
import json
import sys
import time
import urllib.parse

import requests

from common import load_config, log
from threads_token import TOKEN_PATH, save_token

AUTH_URL = "https://threads.net/oauth/authorize"
TOKEN_URL = "https://graph.threads.net/oauth/access_token"
LONG_URL = "https://graph.threads.net/access_token"
SCOPES = "threads_basic,threads_content_publish"


def _cfg():
    t = (load_config().get("threads") or {})
    for k in ("app_id", "app_secret", "redirect_uri"):
        if not t.get(k):
            raise SystemExit(
                f"config.json 의 threads.{k} 가 비어 있습니다.\n"
                "  Meta 개발자 포털에서 앱을 만든 뒤 app_id/app_secret/redirect_uri 를 채우세요.")
    return t


def print_auth_url():
    t = _cfg()
    q = urllib.parse.urlencode({
        "client_id": t["app_id"],
        "redirect_uri": t["redirect_uri"],
        "scope": SCOPES,
        "response_type": "code",
    })
    print("\n아래 URL 을 브라우저에서 열어 스레드 계정으로 로그인·동의하세요.\n")
    print(f"  {AUTH_URL}?{q}\n")
    print("동의하면 콜백 페이지에 'code' 가 표시됩니다. 그 값을 복사해서:\n")
    print("  python threads_login_setup.py --code <복사한코드>\n")
    print("※ 코드는 1시간 동안, 단 한 번만 쓸 수 있습니다.")


def exchange(code):
    t = _cfg()
    # 1) 인가코드 → 단기 토큰(1시간)
    r = requests.post(TOKEN_URL, data={
        "client_id": t["app_id"],
        "client_secret": t["app_secret"],
        "grant_type": "authorization_code",
        "redirect_uri": t["redirect_uri"],
        "code": code.strip(),
    }, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"단기 토큰 교환 실패({r.status_code}): {r.text[:300]}")
    short = r.json()
    user_id = str(short.get("user_id", ""))
    log(f"단기 토큰 발급됨 (user_id={user_id}).")

    # 2) 단기 → 장기 토큰(60일)
    r2 = requests.get(LONG_URL, params={
        "grant_type": "th_exchange_token",
        "client_secret": t["app_secret"],
        "access_token": short["access_token"],
    }, timeout=30)
    if r2.status_code != 200:
        raise SystemExit(f"장기 토큰 교환 실패({r2.status_code}): {r2.text[:300]}")
    lng = r2.json()

    save_token({
        "access_token": lng["access_token"],
        "user_id": user_id,
        "expires_at": time.time() + int(lng.get("expires_in", 60 * 24 * 3600)),
    })
    days = int(lng.get("expires_in", 0)) // 86400
    print(f"\n✅ 저장 완료: {TOKEN_PATH}  (유효기간 약 {days}일)")
    print("   이후 갱신은 발행 때 자동으로 처리됩니다.")


if __name__ == "__main__":
    if "--code" in sys.argv:
        exchange(sys.argv[sys.argv.index("--code") + 1])
    else:
        print_auth_url()
