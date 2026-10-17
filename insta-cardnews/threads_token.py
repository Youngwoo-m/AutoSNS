"""스레드 장기 토큰 저장·자동 갱신.

장기 토큰은 60일짜리라 그냥 두면 조용히 만료된다. 발행 직전에 남은 기간을
확인해서 임계일 아래로 내려가면 refresh_access_token 으로 연장한다.
(갱신은 최소 24시간 이상 된 토큰에만 동작한다.)
"""
import json
import os
import time

import requests

from common import BASE_DIR, log

TOKEN_PATH = os.path.join(BASE_DIR, "threads_token.json")
REFRESH_URL = "https://graph.threads.net/refresh_access_token"
# 만료 이 일수 이전이면 미리 갱신한다.
REFRESH_BEFORE_DAYS = 10


def _token_store():
    """토큰은 암호화 저장소(shared/token_store.py, THREADS_TOKEN)에 둔다(2026-10-17)."""
    import sys
    root = os.path.dirname(BASE_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared import token_store
    return token_store


def save_token(tok):
    _token_store().write_json(TOKEN_PATH, tok)


def load_token():
    tok = _token_store().read_json(TOKEN_PATH)
    if not tok:
        raise RuntimeError(
            "스레드 토큰이 없습니다.\n"
            "  먼저 1회 로그인하세요:  python threads_login_setup.py")
    return tok


def valid_token():
    """유효한 액세스 토큰과 user_id 를 돌려준다. 만료가 임박하면 갱신한다."""
    tok = load_token()
    left = tok.get("expires_at", 0) - time.time()
    if left <= 0:
        raise RuntimeError(
            "스레드 토큰이 만료됐습니다(60일 경과).\n"
            "  다시 로그인하세요:  python threads_login_setup.py")
    if left < REFRESH_BEFORE_DAYS * 86400:
        try:
            r = requests.get(REFRESH_URL, params={
                "grant_type": "th_refresh_token",
                "access_token": tok["access_token"],
            }, timeout=30)
            if r.status_code == 200:
                d = r.json()
                tok["access_token"] = d["access_token"]
                tok["expires_at"] = time.time() + int(d.get("expires_in", 60 * 86400))
                save_token(tok)
                log(f"스레드 토큰 자동 갱신됨(약 {int(d.get('expires_in', 0)) // 86400}일 연장).")
            else:
                log(f"스레드 토큰 갱신 실패({r.status_code}) → 기존 토큰으로 진행.")
        except Exception as e:
            log(f"스레드 토큰 갱신 중 오류({type(e).__name__}) → 기존 토큰으로 진행.")
    return tok["access_token"], tok["user_id"]
