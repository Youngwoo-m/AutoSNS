"""표준 라이브러리만 쓰는 HTTP 가져오기 — 자료사진·영상 모듈이 같은 코드를 따로 쓰던 것을 합쳤다.

    from shared.web import get_bytes, get_json, download
    data = get_json(url, headers={"Authorization": key})
    download(url, "/tmp/clip.mp4", timeout=60)          # 임시 파일(.part)에 받은 뒤 성공해야 옮긴다
UA 는 기본 "smuds/1.0". 오류(HTTPError·시간 초과 등)는 그대로 올려 보낸다.
"""
import json
import os
import urllib.request

UA = {"User-Agent": "smuds/1.0"}


def get_bytes(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def get_json(url, headers=None, timeout=20):
    return json.loads(get_bytes(url, headers, timeout).decode("utf-8"))


def download(url, path, headers=None, timeout=60):
    """url 을 path 에 받는다. path + '.part' 에 먼저 쓰고 끝나면 옮겨, 실패로 반쪽 파일이 남지 않는다."""
    data = get_bytes(url, headers, timeout)
    tmp = path + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return path
