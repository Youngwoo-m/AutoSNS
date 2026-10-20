"""채널 계정 로그아웃·다시 로그인, 비밀값 저장 — 콘솔 서버가 부른다.

로그아웃은 되돌리기 어려운 일이라 콘솔 화면에서 한 번 더 확인받은 뒤에만 부른다.
  google_disconnect(acc, svc)  저장소에서 그 서비스 토큰만 지운다(구글 쪽 허용은 남음)
  google_logout(acc)           구글 쪽 허용을 취소(revoke)하고 그 계정 토큰 3개를 모두 지운다
  browser_logout(site)         크롬 프로필에서 그 사이트 쿠키를 지운다(프로필 잠금을 잡고)
  gh_logout(user)              gh CLI 에서 그 계정을 뺀다
  kakao_logout()               카카오 알림 토큰을 지운다
  save_secret(name, value)     암호화 저장소에 값을 넣는다(값은 어디에도 출력하지 않는다)
"""
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

CONSOLE = Path(__file__).resolve().parents[1]
ROOT = CONSOLE.parent
sys.path.insert(0, str(ROOT))
from shared import axlock  # noqa: E402

GPY = str(ROOT / 'channels' / 'youtube-shorts-auto' / '.venv' / 'bin' / 'python')
NAME = re.compile(r'^[A-Z][A-Z0-9_]{2,60}$')

# 사이트 → (프로필 이름, 지울 쿠키 도메인, 함께 지울 파일, 다시 로그인 스크립트(폴더, 파일))
BROWSER = {
    'naver': ('naver', ['naver.com'], [], ('channels/naver-blog-auto', 'login_setup.py')),
    'tistory': ('tistory', ['tistory.com', 'kakao.com'], ['GeoAI_NA/naver-blog-auto/tistory_cookies.json'],
                ('channels/naver-blog-auto', 'tistory_login.py')),
}


def _py(code, payload):
    """youtube-shorts-auto 파이썬(cryptography·google 라이브러리 있음)으로 짧은 코드를 돌린다.
    비밀값은 표준입력으로만 넘긴다(명령줄·로그에 남지 않게)."""
    p = subprocess.run([GPY, '-c', code], cwd=str(ROOT), input=json.dumps(payload), capture_output=True,
                       text=True, timeout=90)
    if p.returncode != 0:
        raise ValueError(((p.stderr or '').strip().splitlines() or ['실패'])[-1][:200])
    return json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {}


def save_secret(name, value):
    if not NAME.match(name or ''):
        raise ValueError('이름은 영문 대문자·숫자·밑줄로 (예: GAMMA_API_KEY)')
    if not value or len(value) > 20000:
        raise ValueError('값을 넣으세요')
    _py("import json,sys;from shared import secret_env as s;d=json.load(sys.stdin);"
        "s.update({d['n']: d['v']});print(json.dumps({'ok':True}))", {'n': name, 'v': value})
    axlock.log(f'비밀값 저장: {name} (값은 기록하지 않음)')


def delete_secrets(names):
    _py("import json,sys;from shared import secret_env as s;d=json.load(sys.stdin);"
        "s.update(remove=d['n']);print(json.dumps({'ok':True}))", {'n': list(names)})


def google_disconnect(account, service, secret_name):
    delete_secrets([secret_name])
    axlock.log(f'구글 연결 해제: {account}/{service} ({secret_name} 삭제)')


def google_logout(account, secret_names):
    """구글 쪽 허용을 취소한 뒤 토큰들을 지운다. 같은 OAuth 앱이라 하나만 취소해도 모두 무효가 된다."""
    r = _py("""import json,sys,urllib.request,urllib.parse
from shared import secret_env as s
d=json.load(sys.stdin);v=s.read();done=[]
for n in d['n']:
    raw=v.get(n)
    if not raw: continue
    t=json.loads(raw) if isinstance(raw,str) else raw
    tok=t.get('refresh_token') or t.get('token')
    if not tok: continue
    try:
        urllib.request.urlopen(urllib.request.Request('https://oauth2.googleapis.com/revoke',
            data=urllib.parse.urlencode({'token':tok}).encode(),
            headers={'Content-Type':'application/x-www-form-urlencoded'}),timeout=20)
        done.append(n)
    except Exception as e:
        done.append(n+'(취소 응답: '+str(getattr(e,'code',e))+')')
s.update(remove=d['n']);print(json.dumps({'revoked':done}))""", {'n': list(secret_names)})
    axlock.log(f"구글 계정 로그아웃: {account} ({', '.join(secret_names)} 취소·삭제)")
    return r


def _cookie_dbs(profile):
    base = Path(axlock.PROFILES[profile])
    return [p for p in (base / 'Default' / 'Cookies', base / 'Default' / 'Network' / 'Cookies') if p.exists()]


def browser_logout(site):
    prof, domains, files, _ = BROWSER[site]
    removed = 0
    with axlock.hold([f'profile:{prof}'], job=f'console:logout-{site}', wait=10):
        for db in _cookie_dbs(prof):
            con = sqlite3.connect(db)
            for d in domains:
                removed += con.execute("delete from cookies where host_key = ? or host_key like ?", (d, f'%.{d}')).rowcount
            con.commit()
            con.close()
        for f in files:
            p = ROOT / f
            if p.exists():
                p.unlink()
    axlock.log(f'{site} 로그아웃: 쿠키 {removed}개 삭제')
    return {'cookies_removed': removed}


def browser_login(site):
    """사람이 직접 로그인하는 창을 띄운다(기존 로그인 스크립트, 로그인을 알아서 감지하고 닫힘)."""
    prof, _, _, (folder, script) = BROWSER[site]
    py = ROOT / folder / '.venv' / 'bin' / 'python'
    with axlock.hold([f'profile:{prof}'], job=f'console:login-{site}', wait=10):
        p = subprocess.run([str(py), script], cwd=str(ROOT / folder), capture_output=True, text=True, timeout=600)
    out = ((p.stdout or '') + (p.stderr or '')).strip().splitlines()
    axlock.log(f"{site} 다시 로그인: 코드 {p.returncode}")
    return {'ok': p.returncode == 0, 'msg': (out[-1] if out else '')[:200]}


def gh_logout(user):
    exe = next((e for e in ('/opt/homebrew/bin/gh', '/usr/local/bin/gh') if Path(e).exists()), 'gh')
    p = subprocess.run([exe, 'auth', 'logout', '--hostname', 'github.com', '--user', user], capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        raise ValueError((p.stderr or p.stdout).strip()[:200])
    axlock.log(f'GitHub 로그아웃: {user}')


def kakao_logout():
    delete_secrets(['KAKAO_TOKEN'])
    axlock.log('카카오 알림 토큰 삭제')
