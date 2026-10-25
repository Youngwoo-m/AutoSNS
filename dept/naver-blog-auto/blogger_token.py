"""Blogger OAuth 토큰을 암호화 저장소(secrets.env.enc)에 두고 읽고 쓴다.

예전에는 token_blogger*.json 평문 파일이었다(갱신 토큰이 들어 있어 파일만 있으면 누구나
블로그에 글을 쓸 수 있다). 2026-10-17 부터 저장소로 옮겼다. 열쇠는 키체인에만 있다.

- 파일 이름 → 저장소 이름: NAMES. config.blogger.token_file 이 가리키는 이름 그대로 쓴다.
- 저장소에 없고 옛 파일이 있으면 파일을 읽는다(옮기기 전 상태 호환).
- 토큰이 갱신되면 읽어 온 곳(저장소/파일)에 다시 쓴다.
"""
import json
import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from common import BASE_DIR, log

ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from shared import secret_env  # noqa: E402

NAMES = {"token_blogger.json": "BLOGGER_TOKEN_DEPT",
         "token_blogger_geoai.json": "BLOGGER_TOKEN_GEOAI"}


def secret_name(filename):
    return NAMES.get(os.path.basename(filename)) or (
        "BLOGGER_TOKEN_" + os.path.splitext(os.path.basename(filename))[0].upper())


def save(filename, creds_json):
    """새로 받았거나 갱신한 토큰을 저장소에 둔다(평문 파일은 만들지 않는다)."""
    secret_env.update({secret_name(filename): creds_json})


def exists(filename):
    try:
        if secret_env.read().get(secret_name(filename)):
            return True
    except BaseException:
        pass
    return os.path.exists(os.path.join(BASE_DIR, os.path.basename(filename)))


def load(filename, scopes, label="Blogger"):
    """Credentials. 없으면 RuntimeError. 만료됐으면 갱신해서 저장한다."""
    name = secret_name(filename)
    path = os.path.join(BASE_DIR, os.path.basename(filename))
    raw, src = None, None
    try:
        raw = secret_env.read().get(name)
        src = "store" if raw else None
    except BaseException as e:               # 키체인 거부는 SystemExit 로 온다
        log(f"⚠ 암호화 저장소를 열지 못함({type(e).__name__}) — 옛 토큰 파일을 찾습니다")
    if not raw and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            raw, src = f.read(), "file"
    if not raw:
        raise RuntimeError(f"{label} 토큰이 없습니다({name}) — 해당 계정으로 1회 인증이 필요합니다.")
    c = Credentials.from_authorized_user_info(json.loads(raw), scopes)
    if not c.valid and c.expired and c.refresh_token:
        c.refresh(Request())
        if src == "store":
            save(filename, c.to_json())
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(c.to_json())
        log(f"{label} 토큰 자동 갱신됨.")
    return c
