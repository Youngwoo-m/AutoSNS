"""학과·개인 구글 토큰 상태를 확인한다. 콘솔 서버가 youtube-shorts-auto/.venv 파이썬으로 부른다.

토큰을 열어 만료됐으면 갱신(갱신한 토큰은 같은 이름으로 다시 저장)하고, 그 토큰으로
실제 API를 한 번 불러 어느 채널·블로그에 연결됐는지 확인한다. 결과는 JSON 한 줄로 출력한다.
토큰 값은 출력하지 않는다.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from shared import secret_env  # noqa: E402


def creds(name):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    raw = secret_env.read().get(name)
    if not raw:
        return None, '토큰 없음'
    info = json.loads(raw) if isinstance(raw, str) else raw
    c = Credentials.from_authorized_user_info(info)
    if not c.valid:
        if not c.refresh_token:
            return None, '만료 (다시 로그인 필요)'
        c.refresh(Request())
        secret_env.update({name: c.to_json() if isinstance(raw, str) else json.loads(c.to_json())})
    return c, None


def identify(service, c):
    from googleapiclient.discovery import build
    if service == 'youtube':
        r = build('youtube', 'v3', credentials=c, cache_discovery=False).channels().list(part='snippet', mine=True).execute()
        return [i['snippet']['title'] for i in r.get('items', [])] or ['연결된 채널 없음']
    if service == 'blogger':
        r = build('blogger', 'v3', credentials=c, cache_discovery=False).blogs().listByUser(userId='self').execute()
        return [b['url'].replace('https://', '').rstrip('/') for b in r.get('items', [])] or ['블로그 없음']
    if service == 'searchconsole':
        r = build('searchconsole', 'v1', credentials=c, cache_discovery=False).sites().list().execute()
        return [s['siteUrl'] for s in r.get('siteEntry', [])] or ['등록된 사이트 없음']
    return []


def check(service, name):
    try:
        c, err = creds(name)
        if err:
            return {'ok': False, 'state': err}
        return {'ok': True, 'state': '정상', 'expires': c.expiry.isoformat() if c.expiry else '',
                'scopes': [s.rsplit('/', 1)[-1] for s in (c.scopes or [])], 'targets': identify(service, c)}
    except Exception as e:  # 갱신 거부(invalid_grant)·권한 부족 등을 사람이 읽을 말로
        msg = str(e)
        if 'invalid_grant' in msg:
            msg = '토큰이 취소되었거나 만료됨 (다시 로그인 필요)'
        return {'ok': False, 'state': msg[:200]}


if __name__ == '__main__':
    pairs = json.loads(sys.argv[1])  # [[계정, 서비스, 저장소 이름], ...]
    print(json.dumps({f'{a}/{s}': check(s, n) for a, s, n in pairs}, ensure_ascii=False))
