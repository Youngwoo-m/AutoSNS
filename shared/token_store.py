"""OAuth 토큰·클라이언트 파일을 암호화 저장소(secrets.env.enc)에 두고 읽고 쓴다 — 프로젝트 공용.

예전에는 token.json 같은 평문 파일이었다. 파일만 있으면 채널에 영상을 올리거나 카톡을
보낼 수 있어서 2026-10-17 저장소로 옮겼다(열쇠는 키체인에만 있다). 블로거 토큰은
naver-blog-auto/blogger_token.py 가 같은 방식으로 다룬다.

코드에서는 지금까지 쓰던 '파일 경로'를 그대로 넘긴다 — 경로의 파일 이름으로 저장소 이름을
정한다(NAMES). 그래서 호출하는 쪽은 open(path) 대신 read_json(path)/write_json(path) 만 바꾸면 된다.

- 읽기: 저장소 → (없으면) 옛 평문 파일.
- 쓰기: 저장소에 쓴다. 저장소를 못 쓰면(열쇠 없음 등) 예전처럼 파일에 쓴다.
- 저장소에 옮긴 뒤 남은 평문 파일은 migrate.py 가 지운다(읽기는 저장소가 우선이라 남아도 무해).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NAMES = {
    "token.json": "YOUTUBE_TOKEN_DEPT",                  # 학과 유튜브(semyungds) 업로드
    "token_youtube_geoai.json": "YOUTUBE_TOKEN_GEOAI",   # 개인 GeoAI 유튜브
    "token_manage.json": "YOUTUBE_TOKEN_MANAGE",         # 공개 상태 바꾸기(force-ssl)
    "x_token.json": "X_TOKEN",
    "tiktok_token.json": "TIKTOK_TOKEN",
    "kakao_token.json": "KAKAO_TOKEN",
    "threads_token.json": "THREADS_TOKEN",
    "client_secret.json": "GOOGLE_OAUTH_CLIENT",         # Google OAuth 클라이언트(유튜브·Blogger·서치콘솔)
    "token_searchconsole.json": "SEARCHCONSOLE_TOKEN",
    "token_searchconsole_dept.json": "SEARCHCONSOLE_TOKEN_DEPT",
    "token_blogger.json": "BLOGGER_TOKEN_DEPT",
    "token_blogger_geoai.json": "BLOGGER_TOKEN_GEOAI",
}


def name_for(path):
    base = os.path.basename(path)
    if base in NAMES:
        return NAMES[base]
    stem = os.path.splitext(base)[0]
    if stem.startswith("token_searchconsole_"):          # 서치콘솔은 계정마다 하나씩
        return "SEARCHCONSOLE_TOKEN_" + stem[len("token_searchconsole_"):].upper()
    return "TOKEN_" + stem.upper()


def stored_names():
    """저장소에 있는 이름 목록(열지 못하면 빈 목록)."""
    return list(_store() or {})


def _env():
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from shared import secret_env
    return secret_env


def _store():
    """저장소 내용. 열지 못하면 None(그때는 파일로 동작)."""
    try:
        return _env().read()
    except BaseException:                    # 키체인 거부는 SystemExit 로 온다
        return None


def read_text(path):
    st = _store()
    if st and st.get(name_for(path)):
        return st[name_for(path)]
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return None


def read_json(path):
    t = read_text(path)
    return json.loads(t) if t else None


def exists(path):
    return read_text(path) is not None


def write_text(path, text):
    try:
        _env().update({name_for(path): text})
        return "store"
    except BaseException:
        tmp = path + ".part"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w",
                  encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
        return "file"


def write_json(path, obj):
    return write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


def google_creds(path, scopes=None):
    """저장된 Google 사용자 토큰 → Credentials(갱신은 호출하는 쪽이 하고 write_text 로 저장)."""
    from google.oauth2.credentials import Credentials
    info = read_json(path)
    if not info:
        raise FileNotFoundError(f"{os.path.basename(path)} 토큰이 없습니다({name_for(path)})")
    return Credentials.from_authorized_user_info(info, scopes)


def client_config(path):
    """client_secret.json 내용(dict) — InstalledAppFlow.from_client_config 에 넘긴다."""
    c = read_json(path)
    if not c:
        raise FileNotFoundError(f"{os.path.basename(path)} 이 없습니다({name_for(path)})")
    return c


def load_google(path, scopes=None, save=True):
    """저장된 Google 토큰 → 유효한 Credentials. 만료됐으면 갱신하고, save=True 면 갱신한 토큰을
    저장한다. 다른 스코프로 잠깐 빌려 쓰는 스크립트는 save=False — 저장하면 토큰의 scopes 가
    그 스크립트 것으로 바뀌어 원래 주인이 갱신할 때 깨진다(retention_report 2026-10 사례)."""
    from google.auth.transport.requests import Request
    c = google_creds(path, scopes)
    if not c.valid and c.expired and c.refresh_token:
        c.refresh(Request())
        if save:
            write_text(path, c.to_json())
    return c
