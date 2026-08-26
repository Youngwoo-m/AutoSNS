"""카카오톡 '나에게 보내기'(메모 API) 알림.

kakao_token.json 에 client_id/client_secret/refresh_token/access_token 을 둔다.
access_token(약 6시간)이 만료되면 refresh_token(약 60일)으로 자동 갱신 후 재시도한다.
카카오가 refresh_token 을 새로 내려주면(만료 임박 시) 그 값으로 교체 저장한다.

의존성 없이 표준 라이브러리만 사용 → 세 프로젝트(youtube/insta/naver) 어디든 복사해 쓸 수 있다.
발행 파이프라인을 막지 않도록 notify() 는 실패해도 예외를 삼키고 결과 dict 를 돌려준다.

CLI:  python kakao_notify.py "보낼 메시지" [링크URL]
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

def _token_path():
    """토큰 파일 위치. 세 프로젝트가 youtube-shorts-auto 의 단일 토큰을 공유한다
    (갱신 소스 일원화). 로컬에 있으면 그걸, 없으면 형제 youtube-shorts-auto 것을 쓴다.
    KAKAO_TOKEN_PATH 환경변수로 강제 지정도 가능."""
    env = os.environ.get("KAKAO_TOKEN_PATH")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(here, "kakao_token.json"),
              os.path.join(here, "..", "youtube-shorts-auto", "kakao_token.json")):
        if os.path.exists(p):
            return os.path.abspath(p)
    return os.path.join(here, "kakao_token.json")


TOKEN_PATH = _token_path()
AUTH_URL = "https://kauth.kakao.com/oauth/token"
MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def _load():
    with open(TOKEN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(tok):
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(tok, f, ensure_ascii=False, indent=2)
    os.chmod(TOKEN_PATH, 0o600)


def _refresh(tok):
    """refresh_token 으로 access_token 재발급(+ 회전 시 refresh_token 교체)."""
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": tok["client_id"],
        "client_secret": tok.get("client_secret", ""),
        "refresh_token": tok["refresh_token"],
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(AUTH_URL, data=data), timeout=15) as r:
        d = json.load(r)
    tok["access_token"] = d["access_token"]
    if d.get("refresh_token"):        # 만료 임박 시에만 새 refresh_token 을 준다
        tok["refresh_token"] = d["refresh_token"]
    _save(tok)
    return tok


def _send_once(access_token, text, link_url):
    url = link_url or "https://www.youtube.com/@smu_ds_official"
    obj = {"object_type": "text", "text": text[:1000],
           "link": {"web_url": url, "mobile_web_url": url}}
    data = urllib.parse.urlencode(
        {"template_object": json.dumps(obj, ensure_ascii=False)}).encode()
    req = urllib.request.Request(
        MEMO_URL, data=data, headers={"Authorization": "Bearer " + access_token})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def notify(text, link_url=None):
    """카카오톡 나에게 보내기. 성공 시 {'result_code':0}. 실패해도 예외 없이 dict 반환."""
    try:
        tok = _load()
    except FileNotFoundError:
        return {"skipped": "kakao_token.json 없음(알림 비활성)"}
    try:
        return _send_once(tok["access_token"], text, link_url)
    except urllib.error.HTTPError as e:
        if e.code == 401:             # access_token 만료 → 갱신 후 1회 재시도
            try:
                tok = _refresh(tok)
                return _send_once(tok["access_token"], text, link_url)
            except Exception as e2:
                return {"error": f"refresh 후 재시도 실패: {type(e2).__name__}: {e2}"}
        return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:200]}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    msg = a[0] if a else "[SMUDS] 카카오 알림 테스트 ✅"
    link = a[1] if len(a) > 1 else None
    print(json.dumps(notify(msg, link), ensure_ascii=False))
