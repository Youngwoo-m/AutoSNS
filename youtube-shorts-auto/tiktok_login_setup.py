"""최초 1회: 틱톡 계정으로 로그인해 업로드 권한 토큰(tiktok_token.json)을 저장한다.

틱톡 Web 플랫폼은 Redirect URI 가 반드시 https 라 localhost(http)를 못 쓴다.
그래서 검증된 도메인의 콜백 페이지(https://smuds.netlify.app/callback.html)로 코드를 받고,
그 코드를 수동으로 넘겨 토큰으로 교환하는 방식을 쓴다.

사용법:
  0) 키가 살아 있는지 확인:    python tiktok_login_setup.py --check
  1) 인증 URL 출력:            python tiktok_login_setup.py
     → 출력된 URL 로 로그인/동의 → 콜백 페이지에 표시된 'code' 복사
  2) 코드로 토큰 교환/저장:    python tiktok_login_setup.py --code <복사한코드>

사전 준비(개발자 포털): Login Kit + Content Posting API 추가, Platform=Web,
  Redirect URI = config.tiktok.redirect_uri 와 동일, 도메인 검증 완료, Sandbox Target user 추가.
"""
import json
import os
import sys
import time
import urllib.parse

import requests

from common import TIKTOK_TOKEN_PATH, load_config, log

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
SCOPES_DEFAULT = "user.info.basic,video.publish,video.upload"


def _scopes():
    return load_config().get("tiktok", {}).get("scopes", SCOPES_DEFAULT)


def _cfg():
    cfg = load_config().get("tiktok", {})
    ck = cfg.get("client_key", "").strip()
    cs = cfg.get("client_secret", "").strip()
    ru = cfg.get("redirect_uri", "").strip()
    if not ck or not cs or ck.startswith("...") or "여기에" in ck:
        raise SystemExit("config.json 의 tiktok.client_key / client_secret 을 먼저 입력하세요.")
    if not ru.startswith("https://"):
        raise SystemExit(f"redirect_uri 는 https 여야 합니다(현재: {ru}).")
    return ck, cs, ru


def check_keys():
    """client_credentials 로 키가 유효한지만 1초 만에 확인한다(로그인 불필요).

    샌드박스 키는 만료되면 여기서 invalid_client 가 난다. 브라우저 인증을 시작하기
    전에 먼저 이걸로 걸러야 헛수고를 안 한다.
    """
    ck, cs, _ = _cfg()
    r = requests.post(TOKEN_URL, headers={
        "Content-Type": "application/x-www-form-urlencoded"
    }, data={
        "client_key": ck, "client_secret": cs, "grant_type": "client_credentials",
    }, timeout=30).json()
    if "access_token" in r:
        print(f"✅ client_key/secret 정상 ({ck[:8]}…) — 이제 1) 인증 URL 단계로 가세요.")
        return 0
    print(f"❌ 키가 거부됐습니다: {r.get('error')} / {r.get('error_description')}")
    print("   developers.tiktok.com → Manage apps → 해당 앱에서 Client key/secret 을 다시 확인하고")
    print("   config.json 의 tiktok.client_key / client_secret 을 바꿔 주세요.")
    return 1


def print_auth_url():
    ck, _, ru = _cfg()
    params = {
        "client_key": ck,
        "scope": _scopes(),
        "response_type": "code",
        "redirect_uri": ru,
        "state": f"smu{int(time.time())}",
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(params)
    print("\n[1] 아래 URL 을 브라우저에서 열어 틱톡 로그인/동의하세요:\n")
    print(url + "\n")
    print("[2] 로그인 후 이동하는 콜백 페이지에 표시된 'code' 값을 복사해서:")
    print("    python tiktok_login_setup.py --code <복사한코드>\n")


def exchange(code):
    ck, cs, ru = _cfg()
    code = urllib.parse.unquote(code).strip()
    resp = requests.post(TOKEN_URL, headers={
        "Content-Type": "application/x-www-form-urlencoded"
    }, data={
        "client_key": ck,
        "client_secret": cs,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": ru,
    }, timeout=30)
    tok = resp.json()
    if "access_token" not in tok:
        raise SystemExit(f"토큰 교환 실패: {tok}")
    tok["_obtained_at"] = int(time.time())
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from shared import token_store                 # 평문 파일 대신 암호화 저장소
    where = token_store.write_json(TIKTOK_TOKEN_PATH, tok)
    log(f"틱톡 인증 완료. 토큰 저장됨: {token_store.name_for(TIKTOK_TOKEN_PATH)} ({where})")
    print("로그인/인증 완료! 이제 틱톡 업로드가 가능합니다.")


if __name__ == "__main__":
    if "--check" in sys.argv:
        raise SystemExit(check_keys())
    if "--code" in sys.argv:
        i = sys.argv.index("--code")
        if i + 1 >= len(sys.argv):
            raise SystemExit("사용법: python tiktok_login_setup.py --code <코드>")
        exchange(sys.argv[i + 1])
    else:
        print_auth_url()
