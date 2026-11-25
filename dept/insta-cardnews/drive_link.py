"""릴 영상을 구글 드라이브(개인 계정, drive.file 권한)에 올리고 공유 링크를 돌려준다 — 표준 라이브러리만(2026-11-25).

메일에 넣기엔 큰 릴을 줄이지 않고 원본 그대로 조교에게 전달하려고 쓴다(사용자 지시).
토큰: drive_auth.py 로 만든 암호화 저장소 TOKEN_TOKEN_DRIVE_INSTA.
받는 사람 메일을 보기 권한으로 추가하고, 그게 안 되면(구글 계정이 아닌 주소 등) '링크가 있는 사람 보기'로 연다.
    python drive_link.py <파일> [받는사람 ...]
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from common import BASE_DIR, log

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "common"))
from shared import token_store  # noqa: E402

TOKEN = "token_drive_insta.json"
FOLDER_NAME = "재난안전학과 인스타 릴"


def _access_token():
    t = json.loads(token_store.read_text(TOKEN))
    body = urllib.parse.urlencode({"client_id": t["client_id"], "client_secret": t["client_secret"],
                                   "refresh_token": t["refresh_token"], "grant_type": "refresh_token"}).encode()
    with urllib.request.urlopen("https://oauth2.googleapis.com/token", data=body, timeout=30) as r:
        return json.load(r)["access_token"]


def _api(tok, url, data=None, method=None, ctype="application/json", headers=None):
    h = {"Authorization": f"Bearer {tok}", **(headers or {})}
    if data is not None:
        h["Content-Type"] = ctype
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data is not None else "GET"), headers=h)
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.headers, (r.read() or b"{}")


def _folder(tok):
    q = urllib.parse.quote(f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false")
    _, b = _api(tok, f"https://www.googleapis.com/drive/v3/files?q={q}&fields=files(id)")
    files = json.loads(b).get("files") or []
    if files:
        return files[0]["id"]
    _, b = _api(tok, "https://www.googleapis.com/drive/v3/files?fields=id",
                json.dumps({"name": FOLDER_NAME, "mimeType": "application/vnd.google-apps.folder"}).encode())
    return json.loads(b)["id"]


def upload(path, name=None, share_to=()):
    """파일을 올리고 → (보기 링크, 공유 방식)."""
    tok = _access_token()
    meta = {"name": name or os.path.basename(path), "parents": [_folder(tok)]}
    size = os.path.getsize(path)
    hdr, _ = _api(tok, "https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable",
                  json.dumps(meta).encode(), ctype="application/json; charset=UTF-8",
                  headers={"X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)})
    with open(path, "rb") as f:
        _, b = _api(tok, hdr["Location"], f.read(), method="PUT", ctype="video/mp4")
    info = _share(tok, json.loads(b)["id"], share_to)
    return info


def _share(tok, fid, share_to=()):
    _, b = _api(tok, f"https://www.googleapis.com/drive/v3/files/{fid}?fields=id,name,size,webViewLink")
    info = json.loads(b)
    how = []
    for em in share_to or ():
        try:
            _api(tok, f"https://www.googleapis.com/drive/v3/files/{info['id']}/permissions?sendNotificationEmail=false",
                 json.dumps({"type": "user", "role": "reader", "emailAddress": em}).encode())
            how.append(em)
        except urllib.error.HTTPError as e:
            log(f"드라이브 공유({em}) 실패 {e.code} — 링크 공유로 엽니다")
    if not how:
        _api(tok, f"https://www.googleapis.com/drive/v3/files/{info['id']}/permissions",
             json.dumps({"type": "anyone", "role": "reader"}).encode())
        how = ["링크가 있는 사람"]
    log(f"드라이브에 올림: {info['name']} ({int(info.get('size') or 0) // 1024}KB) → {info['webViewLink']} (보기: {', '.join(how)})")
    return info["webViewLink"], how


def find(name):
    """같은 이름으로 이미 올린 파일 id(없으면 None)."""
    tok = _access_token()
    q = urllib.parse.quote(f"name='{name}' and trashed=false")
    _, b = _api(tok, f"https://www.googleapis.com/drive/v3/files?q={q}&fields=files(id)")
    f = json.loads(b).get("files") or []
    return f[0]["id"] if f else None


def share_existing(fid, share_to=()):
    return _share(_access_token(), fid, share_to)


if __name__ == "__main__":
    print(upload(sys.argv[1], share_to=sys.argv[2:]))
