"""D3 브라우저 서비스 — 프로필별 크롬을 바탕화면에 창을 띄우지 않고 열고, 화면·입력을 콘솔로 중계한다.

youtube-shorts-auto/.venv 파이썬(websocket-client)으로 돈다. 콘솔 서버가 필요할 때 띄운다.
127.0.0.1:8711 에서만 받고, 콘솔 내부 키(X-AX-Internal)가 있어야 한다.

  POST /start   {profile, url, mode}   mode: headless(창 없음, 기본) | hidden(보이는 크롬을 화면 밖에)
  POST /stop    {profile}
  GET  /list
  GET  /shot?profile=…                 JPEG 화면
  POST /input   {profile, type: click|type|key|scroll|navigate|back, …}
  POST /save_cookies {profile, domains, path}   (티스토리처럼 세션 쿠키를 파일로 받아 둘 때)

- 프로필 잠금(shared/axlock)을 크롬이 떠 있는 동안 잡는다. 다른 작업과 겹치지 않는다.
- 15분 동안 아무 조작이 없으면 저절로 닫는다.
"""
import base64
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONSOLE = Path(__file__).resolve().parents[1]
ROOT = CONSOLE.parent
sys.path.insert(0, str(ROOT))
from shared import axlock  # noqa: E402

import websocket  # noqa: E402  websocket-client

CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
PORT = int(os.environ.get('AX_BROWSER_PORT', 8711))
KEY = (Path(os.environ.get('AX_AUTH_DIR') or CONSOLE / 'data' / 'auth') / 'internal.key').read_text().strip()
IDLE = 900
VW, VH = 1280, 860   # 화면 크기(이름 H 는 아래 HTTP 처리 클래스가 쓴다)
SESS = {}
LOCK = threading.Lock()

ALLOWED_EXTRA = {'--disable-blink-features=AutomationControlled'}
MARK = '--ax-browser-worker'   # 이 워커가 띄운 크롬 표시(남은 크롬 정리용)
KEYS = {'Enter': (13, '\r'), 'Backspace': (8, ''), 'Tab': (9, '\t'), 'Escape': (27, ''), 'ArrowLeft': (37, ''),
        'ArrowUp': (38, ''), 'ArrowRight': (39, ''), 'ArrowDown': (40, ''), 'Delete': (46, '')}


def _ancestors(pid):
    """pid 와 그 부모들(잠금을 쥔 래퍼가 그 위에 있는지 확인용)."""
    out, seen = [], 0
    while pid and pid > 1 and seen < 30:
        out.append(pid)
        r = subprocess.run(['ps', '-o', 'ppid=', '-p', str(pid)], capture_output=True, text=True).stdout.strip()
        pid, seen = int(r or 0), seen + 1
    return out


def _free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


REAL_KEYCHAIN = {'tiktok', 'scratch'}   # 셀레니움 밖에서 크롬을 직접 띄워 쓰는 프로필(쿠키가 진짜 키체인 키로 암호화돼 있음)


class Session:
    def __init__(self, profile, mode, owner_pid=None, extra=()):
        if profile not in axlock.PROFILES:
            raise ValueError(f'없는 프로필: {profile}')
        self.profile, self.mode, self.owner = profile, mode, owner_pid
        # 발행 작업이 빌려 쓰는 경우(owner_pid): 그 작업이 run_*.sh 래퍼로 이미 프로필 잠금을 쥐고 있다.
        # 그 잠금을 쥔 프로세스가 맞는지 확인하고, 다시 잡지 않는다.
        if owner_pid:
            h = axlock.holder_of(f'profile:{profile}')
            if not h or int(h['pid']) not in _ancestors(int(owner_pid)):
                raise ValueError('빌려 쓰려면 그 작업이 프로필 잠금을 쥐고 있어야 합니다(shared/axlock.py run 으로 실행)')
            self.fds = []
        else:
            self.fds = axlock.acquire([f'profile:{profile}'], job=f'browser:{profile}', wait=5)
        self.port = _free_port()
        args = [CHROME, f'--user-data-dir={axlock.PROFILES[profile]}', f'--remote-debugging-port={self.port}', MARK,
                '--remote-allow-origins=*', '--no-first-run', '--no-default-browser-check', '--disable-features=Translate,MacAppCodeSignClone',
                f'--window-size={VW},{VH}', '--lang=ko-KR'] + [a for a in extra if a in ALLOWED_EXTRA]
        # 쿠키 암호화 키를 그 프로필을 여는 다른 도구와 맞춘다. 셀레니움(chromedriver)은 맥에서 늘 --use-mock-keychain 을 붙인다.
        # 키가 다르면 크롬이 못 푸는 쿠키를 지워 로그인이 풀린다(2026-10-19 네이버: 콘솔에서 로그인 → 보고서 셀레니움이 열며 삭제 → 통계 401).
        # 틱톡(tiktok_web 이 크롬을 직접 띄움)·빈 브라우저만 진짜 키체인, 나머지는 셀레니움과 같은 mock 키.
        if profile not in REAL_KEYCHAIN:
            args.append('--use-mock-keychain')
        args += ['--headless=new'] if mode == 'headless' else ['--window-position=-3000,-3000']
        self.proc = subprocess.Popen(args + ['about:blank'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws, self.mid, self.last = None, 0, time.time()
        self.lock = threading.Lock()
        try:
            self._attach()
        except Exception:
            self.close()
            raise

    def _attach(self):
        t0 = time.time()
        while True:
            try:
                tabs = json.load(urllib.request.urlopen(f'http://127.0.0.1:{self.port}/json', timeout=2))
                page = next(t for t in tabs if t.get('type') == 'page')
                break
            except Exception:
                if time.time() - t0 > 20 or self.proc.poll() is not None:
                    raise RuntimeError('크롬을 띄우지 못했습니다(프로필이 다른 크롬에서 열려 있을 수 있음)')
                time.sleep(0.4)
        self.ws = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=30, suppress_origin=True)
        self.cmd('Page.enable')
        ua = self.cmd('Browser.getVersion').get('userAgent', '')
        if 'Headless' in ua:   # 창 없는 크롬은 'HeadlessChrome' 으로 자신을 알려 사이트가 막거나 추가 인증을 요구할 수 있다
            self.cmd('Network.setUserAgentOverride', userAgent=ua.replace('HeadlessChrome', 'Chrome'), acceptLanguage='ko-KR,ko')
        self.cmd('Emulation.setDeviceMetricsOverride', width=VW, height=VH, deviceScaleFactor=1, mobile=False)

    def cmd(self, method, **params):
        with self.lock:
            self.mid += 1
            mid = self.mid
            self.ws.send(json.dumps({'id': mid, 'method': method, 'params': params}))
            while True:
                m = json.loads(self.ws.recv())
                if m.get('id') == mid:
                    if 'error' in m:
                        raise RuntimeError(f"{method}: {m['error'].get('message')}")
                    return m.get('result', {})

    def info(self):
        r = self.cmd('Runtime.evaluate', expression='JSON.stringify({u:location.href,t:document.title})', returnByValue=True)
        v = json.loads(r.get('result', {}).get('value') or '{}')
        return {'profile': self.profile, 'mode': self.mode, 'url': v.get('u', ''), 'title': v.get('t', ''),
                'idle': int(time.time() - self.last), 'port': self.port, 'owner': self.owner}

    def shot(self):
        r = self.cmd('Page.captureScreenshot', format='jpeg', quality=65)
        return base64.b64decode(r['data'])

    def input(self, b):
        self.last = time.time()
        t = b.get('type')
        if t == 'click':
            x, y = float(b['x']), float(b['y'])
            self.cmd('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y)
            for ev in ('mousePressed', 'mouseReleased'):
                self.cmd('Input.dispatchMouseEvent', type=ev, x=x, y=y, button='left', clickCount=1)
        elif t == 'scroll':
            self.cmd('Input.dispatchMouseEvent', type='mouseWheel', x=float(b.get('x', VW / 2)), y=float(b.get('y', VH / 2)),
                     deltaX=0, deltaY=float(b.get('dy', 400)))
        elif t == 'type':
            self.cmd('Input.insertText', text=str(b.get('text', ''))[:2000])
        elif t == 'key':
            k = b.get('key')
            if k not in KEYS:
                raise ValueError('지원하지 않는 키')
            code, txt = KEYS[k]
            for ev in ('keyDown', 'keyUp'):
                p = {'type': ev, 'key': k, 'windowsVirtualKeyCode': code, 'nativeVirtualKeyCode': code}
                if ev == 'keyDown' and txt:
                    p['text'] = txt
                self.cmd('Input.dispatchKeyEvent', **p)
        elif t == 'navigate':
            u = str(b.get('url', '')).strip()
            if not u.startswith(('http://', 'https://')):
                u = 'https://' + u
            self.cmd('Page.navigate', url=u)
        elif t == 'back':
            self.cmd('Runtime.evaluate', expression='history.back()')
        else:
            raise ValueError('없는 입력 종류')

    def save_cookies(self, domains, path):
        allc = self.cmd('Network.getAllCookies').get('cookies', [])
        keys = ('name', 'value', 'domain', 'path', 'secure', 'httpOnly', 'sameSite', 'expires')
        keep = [{k: c[k] for k in keys if k in c} for c in allc if any(d in c.get('domain', '') for d in domains)]
        p = ROOT / path
        p.write_text(json.dumps(keep))
        os.chmod(p, 0o600)
        return len(keep)

    def cookie_names(self, domain):
        return [c['name'] for c in self.cmd('Network.getAllCookies').get('cookies', []) if domain in c.get('domain', '')]

    def session_cookie_names(self, domain):
        """창을 닫으면 사라지는 세션 쿠키 이름 — '로그인 상태 유지'를 안 켜고 로그인했는지 가린다."""
        return [c['name'] for c in self.cmd('Network.getAllCookies').get('cookies', [])
                if domain in c.get('domain', '') and c.get('session')]

    def close(self):
        try:
            if self.ws:
                self.cmd('Browser.close')   # 정상 종료라야 쿠키가 디스크에 쓰인다
        except Exception:
            pass
        try:
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.terminate()
        axlock._release(self.fds)


def reaper():
    while True:
        time.sleep(10)
        with LOCK:
            for p, s in list(SESS.items()):
                gone = s.owner and not axlock._alive(s.owner)       # 빌려 간 작업이 끝났거나 죽음
                if (not s.owner and time.time() - s.last > IDLE) or gone or s.proc.poll() is not None:
                    s.close()
                    SESS.pop(p, None)
                    axlock.log(f'내부 브라우저 {p}: 15분 동안 안 써서 닫음')


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, obj=None, body=None, ctype='application/json; charset=utf-8'):
        data = body if body is not None else json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def ok(self):
        return self.headers.get('X-AX-Internal') == KEY

    def sess(self, p):
        s = SESS.get(p)
        if not s:
            raise ValueError('열려 있지 않은 프로필입니다')
        return s

    def do_GET(self):
        if not self.ok():
            return self.send(403, {'error': '허용되지 않음'})
        try:
            if self.path == '/list':
                return self.send(200, [s.info() for s in SESS.values()])
            if self.path.startswith('/shot?profile='):
                s = self.sess(self.path.split('=', 1)[1])
                return self.send(200, body=s.shot(), ctype='image/jpeg')
            if self.path.startswith('/cookies?'):
                q = dict(x.split('=', 1) for x in self.path.split('?', 1)[1].split('&'))
                se = self.sess(q['profile'])
                return self.send(200, {'names': se.cookie_names(q['domain']), 'session': se.session_cookie_names(q['domain'])})
            self.send(404, {'error': '없음'})
        except Exception as e:
            self.send(400, {'error': str(e)[:300]})

    def do_POST(self):
        if not self.ok():
            return self.send(403, {'error': '허용되지 않음'})
        try:
            b = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
            p = str(b.get('profile', ''))
            if self.path == '/start':
                with LOCK:
                    if p not in SESS:
                        SESS[p] = Session(p, b.get('mode') or 'headless', owner_pid=b.get('owner_pid'), extra=b.get('extra') or ())
                        axlock.log(f"내부 브라우저 {p} 열림 ({SESS[p].mode})" + (f" — 작업 pid {b['owner_pid']} 가 빌려 씀" if b.get('owner_pid') else ''))
                    elif b.get('owner_pid') and SESS[p].owner != b.get('owner_pid'):
                        raise ValueError('그 프로필은 이미 콘솔 브라우저에서 열려 있습니다. 닫은 뒤 다시 하세요')
                if b.get('url'):
                    SESS[p].input({'type': 'navigate', 'url': b['url']})
                return self.send(200, SESS[p].info())
            if self.path == '/stop':
                with LOCK:
                    s = SESS.pop(p, None)
                if s:
                    s.close()
                    axlock.log(f'내부 브라우저 {p} 닫힘')
                return self.send(200, {'ok': True})
            if self.path == '/input':
                s = self.sess(p)
                s.input(b)
                return self.send(200, {'ok': True})
            if self.path == '/save_cookies':
                return self.send(200, {'saved': self.sess(p).save_cookies(b['domains'], b['path'])})
            self.send(404, {'error': '없음'})
        except axlock.Timeout:
            self.send(409, {'error': '그 프로필을 다른 작업이 쓰고 있습니다. 끝난 뒤 다시 여세요'})
        except Exception as e:
            self.send(400, {'error': str(e)[:300]})


def cleanup_orphans():
    """앞 워커가 비정상으로 끝나 남긴 크롬(이 워커 표시 + 등록된 프로필)을 닫는다."""
    out = subprocess.run(['ps', '-axo', 'pid,ppid,command'], capture_output=True, text=True).stdout.splitlines()[1:]
    for ln in out:
        pid, ppid, cmd = ln.strip().split(None, 2)
        if MARK in cmd and any(f'--user-data-dir={v}' in cmd for v in axlock.PROFILES.values()) and 'Helper' not in cmd:
            try:
                os.kill(int(pid), 15)
                axlock.log(f'내부 브라우저: 남아 있던 크롬 정리(pid {pid})')
            except OSError:
                pass


if __name__ == '__main__':
    import signal
    signal.signal(signal.SIGTERM, lambda *a: (_ for _ in ()).throw(SystemExit(0)))   # 끌 때 크롬을 닫고 나가게
    cleanup_orphans()
    threading.Thread(target=reaper, daemon=True).start()
    try:
        ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
    finally:
        for s in list(SESS.values()):
            s.close()
