"""발행 스크립트가 크롬을 콘솔 브라우저 서비스에서 빌려 쓰게 한다(D3 2단계).

common.start_chrome(options) 이 부른다. 그 options 의 --user-data-dir 가 켜진 프로필이면
(ax-console/config/browser_service.json), 콘솔(127.0.0.1:8700)에 그 프로필 크롬을 창 없이 띄워 달라고
하고 selenium 을 그 크롬에 붙인다(debuggerAddress). 콘솔이 응답하지 않거나 꺼진 프로필이면 None 을
돌려주고, 호출한 쪽은 예전처럼 직접 크롬을 띄운다 — 발행이 멈추지 않게.

driver.quit() 하면 콘솔에 닫아 달라고 해 크롬이 정상 종료된다(쿠키 저장). 스크립트가 죽어도 워커가
작업 pid 가 사라진 것을 보고 닫는다.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = ROOT / 'ax-console' / 'config' / 'browser_service.json'
KEYFILE = ROOT / 'ax-console' / 'data' / 'auth' / 'internal.key'
CONSOLE = 'http://127.0.0.1:8700'


def _profile_of(options):
    from shared.axlock import PROFILES
    for a in options.arguments:
        if a.startswith('--user-data-dir='):
            path = os.path.realpath(a.split('=', 1)[1])
            for k, v in PROFILES.items():
                if os.path.realpath(v) == path:
                    return k
    return None


def _call(path, body):
    req = urllib.request.Request(CONSOLE + path, data=json.dumps(body).encode(),
                                 headers={'Content-Type': 'application/json', 'X-AX-Internal': KEYFILE.read_text().strip()})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:     # 콘솔이 알려 준 이유를 로그에 남긴다(그냥 'HTTP 400' 이면 원인을 못 찾는다)
        try:
            why = json.loads(e.read() or b'{}').get('error', '')
        except ValueError:
            why = ''
        raise RuntimeError(f'HTTP {e.code} {why}'.strip()) from None


def attach(options, log=print):
    """켜진 프로필이면 콘솔 크롬에 붙은 webdriver, 아니면 None."""
    try:
        conf = json.loads(CFG.read_text()).get('profiles', {})
    except (OSError, ValueError):
        return None
    prof = _profile_of(options)
    mode = conf.get(prof) if prof else None
    if not mode:
        return None
    if not os.environ.get('AX_LOCKED'):
        log(f'콘솔 브라우저: {prof} 는 잠금 래퍼(run_*.sh / axlock) 밖에서 실행돼 예전 방식으로 띄웁니다')
        return None
    try:
        extra = [a for a in options.arguments if a == '--disable-blink-features=AutomationControlled']
        info = _call('/api/browser/start', {'profile': prof, 'mode': mode, 'owner_pid': os.getpid(), 'extra': extra})
    except Exception as e:
        log(f'콘솔 브라우저를 쓰지 못해 예전 방식으로 띄웁니다: {type(e).__name__}: {str(e)[:150]}')
        return None
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    o = Options()
    o.debugger_address = f"127.0.0.1:{info['port']}"
    for k in ('unhandledPromptBehavior',):
        if k in options.capabilities:
            o.set_capability(k, options.capabilities[k])
    d = webdriver.Chrome(options=o)
    real_quit = d.quit

    def quit_and_close():
        try:
            real_quit()
        finally:
            try:
                _call('/api/browser/stop', {'profile': prof})
            except Exception:
                pass
    d.quit = quit_and_close
    log(f'콘솔 브라우저 사용: {prof} ({mode}) — 콘솔 \'브라우저\' 탭에서 진행을 볼 수 있습니다')
    return d
