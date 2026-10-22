"""실패 대응 ② 원인 분석 에이전트 — 읽기 도구만 쓴다. 조치·삭제·로그인·발행은 하지 않는다.

    python incident.py <사건ID>   → 결과 JSON 한 줄 {cause, confidence, evidence, fix_steps, human_needed, known_issue}
콘솔 서버가 youtube-shorts-auto/.venv 파이썬으로 부른다.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_core import CONSOLE, ROOT, Agent, Budget, Tool, load_settings, submit_tool  # noqa: E402
import watcher  # noqa: E402

ALLOWED = [ROOT, Path('/Volumes/USB256/devAPP/AutoSNS/channels/disaster-shorts')]
SECRET_KEY = re.compile(r'key|secret|token|password|passwd|pw$|cookie|session', re.I)
SKIP_DIRS = ('.venv', 'chrome-profile', 'node_modules', '__pycache__', '/posts/', '_profile_backup', '/.git/')


def _inside(p):
    p = Path(p).resolve()
    return any(str(p).startswith(str(a.resolve())) for a in ALLOWED) and not any(s in str(p) for s in SKIP_DIRS[:2])


def read_log(path, lines=40, grep=''):
    """로그 끝부분. 기본 40줄·최대 120줄, 한 줄은 300자에서 자른다(HTML 응답이 통째로 찍힌 줄이 토큰을 다 먹었다).
    grep 이 없으면 파일 끝 256KB 만 읽는다."""
    p = Path(path) if os.path.isabs(path) else ROOT / path
    if not _inside(p) or p.suffix not in ('.log', '.txt') or not p.exists():
        raise ValueError('저장소 안의 .log 파일만 읽을 수 있습니다')
    if grep:
        rows = [r for r in p.read_text(errors='ignore').splitlines() if grep in r]
    else:
        with open(p, 'rb') as f:
            f.seek(max(0, p.stat().st_size - 262144))
            rows = f.read().decode('utf-8', 'ignore').splitlines()
    return '\n'.join(r if len(r) <= 300 else r[:300] + ' …(잘림)' for r in rows[-min(int(lines), 120):])


def job_status(job):
    info = watcher.catalog().get(job)
    if not info:
        return f'없는 작업: {job}. 목록: {", ".join(watcher.catalog())}'
    pl = watcher.plist(job)
    loaded = f'com.smuds.{job}' in subprocess.run(['launchctl', 'list'], capture_output=True, text=True).stdout
    logs = watcher.job_logs(pl, job)
    return {'job': job, 'name': info.get('name'), 'what': info.get('what'), 'note': info.get('note', ''),
            'launchd_loaded': loaded, 'schedule': pl.get('StartCalendarInterval') or pl.get('StartInterval'),
            'script': pl.get('ProgramArguments', [''])[-1], 'locks': info.get('locks', []),
            'logs': [{'path': f, 'modified': __import__('datetime').datetime.fromtimestamp(os.path.getmtime(f)).isoformat(timespec='minutes')} for f in logs]}


def process_list(pattern):
    if len(pattern) < 3:
        raise ValueError('찾을 글자를 3자 이상 주세요')
    out = subprocess.run(['ps', '-axo', 'pid,ppid,lstart,command'], capture_output=True, text=True).stdout.splitlines()
    rows = [r[:300] for r in out[1:] if pattern in r and 'ps -axo' not in r]
    return rows[:30] or '해당 프로세스 없음'


def _console(path):
    key = (CONSOLE / 'data' / 'auth' / 'internal.key').read_text().strip()
    req = urllib.request.Request(f'http://127.0.0.1:8700{path}', headers={'X-AX-Internal': key})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def account_status():
    g = _console('/api/google')
    out = []
    for a in g['accounts']:
        out.append({'account': a['id'], 'google': [{k: s.get(k) for k in ('label', 'state', 'targets')} for s in a['services']],
                    'others': [{k: o.get(k) for k in ('label', 'id', 'state', 'note')} for o in a.get('others', [])],
                    'github': a.get('github')})
    return out


def orchestrator_status():
    return _console('/api/orchestrator')


def view_screenshot(path):
    p = Path(path)
    if not _inside(p) or p.suffix != '.png' or not p.exists():
        raise ValueError('저장소 안의 .png 만 볼 수 있습니다')
    return {'image': str(p)}


def search_code(pattern, folder=''):
    base = (ROOT / folder) if folder else ROOT
    if not _inside(base):
        raise ValueError('저장소 안에서만 찾습니다')
    r = subprocess.run(['grep', '-rn', '--include=*.py', '--include=*.sh', '-F', pattern, str(base)],
                       capture_output=True, text=True, timeout=60).stdout.splitlines()
    r = [x[len(str(ROOT)) + 1:][:240] for x in r if not any(s in x for s in SKIP_DIRS)]
    return r[:60] or '찾지 못함'


def read_code(path, start=1, lines=80):
    p = ROOT / path
    if not _inside(p) or p.suffix not in ('.py', '.sh') or not p.exists():
        raise ValueError('저장소 안의 .py·.sh 만 읽을 수 있습니다')
    rows = p.read_text(errors='ignore').splitlines()
    s = max(1, int(start))
    return '\n'.join(f'{i}: {t}' for i, t in enumerate(rows[s - 1:s - 1 + min(int(lines), 200)], s))


def read_config(module):
    p = ROOT / module / 'config.json'
    if not p.exists():
        raise ValueError('그 모듈에는 config.json 이 없습니다')

    def mask(d):
        if isinstance(d, dict):
            return {k: ('***' if SECRET_KEY.search(k) and isinstance(v, (str, list)) and v else mask(v)) for k, v in d.items()}
        if isinstance(d, list):
            return [mask(x) for x in d]
        return d
    return json.dumps(mask(json.loads(p.read_text())), ensure_ascii=False)[:8000]


def past_incidents(query=''):
    ki = json.loads((CONSOLE / 'config' / 'known_issues.json').read_text()).get('issues', [])
    past = [{'job': x['job'], 'signature': x['signature'], 'status': x['status'],
             'cause': (x.get('analysis') or {}).get('cause'), 'resolution': [h['what'] for h in x['history'] if '해결' in h['what']]}
            for x in watcher.incidents() if x['status'] == 'resolved' or (x.get('analysis') or {}).get('cause')]
    q = query.strip()
    hit = lambda o: not q or q in json.dumps(o, ensure_ascii=False)
    return {'known_issues': [k for k in ki if hit(k)] or ki, 'past': [p for p in past if hit(p)][:15]}


def git_log(path):
    r = subprocess.run(['git', '-C', str(ROOT), 'log', '-8', '--date=short', '--format=%h %ad %s', '--', path],
                       capture_output=True, text=True)
    return r.stdout.strip() or '기록 없음'


def main():
    iid = sys.argv[1]
    inc = watcher._load(watcher.incident_path(iid), None)
    if not inc:
        print(json.dumps({'error': '사건 없음'}, ensure_ascii=False))
        return
    S = lambda **p: {'type': 'object', 'properties': p, 'required': [k for k in p if k not in ('lines', 'grep', 'folder', 'start', 'query')]}
    st, it = {'type': 'string'}, {'type': 'integer'}
    tools = [
        Tool('job_status', '작업의 launchd 상태·일정·스크립트·로그 파일·사용자 메모', S(job=st), job_status, max_calls=4),
        Tool('read_log', '로그 파일 끝부분(기본 40줄, grep 으로 거르기 가능)', S(path=st, lines=it, grep=st), read_log, max_calls=4),
        Tool('process_list', '실행 중 프로세스(명령줄에 pattern 이 든 것)', S(pattern=st), process_list, max_calls=4),
        Tool('account_status', '구글 토큰·네이버·카카오·티스토리·GitHub·Netlify 로그인 상태', S(), account_status, max_calls=2),
        Tool('orchestrator_status', '잠금을 잡은 작업·기다리는 작업·비상 정지', S(), orchestrator_status, max_calls=2),
        Tool('view_screenshot', '실패 스크린샷 보기', S(path=st), view_screenshot, max_calls=1),
        Tool('search_code', '코드에서 글자 찾기(.py/.sh)', S(pattern=st, folder=st), search_code, max_calls=3),
        Tool('read_code', '코드 일부 읽기', S(path=st, start=it, lines=it), read_code, max_calls=3),
        Tool('read_config', '모듈 config.json (비밀값은 가림)', S(module=st), read_config, max_calls=3),
        Tool('past_incidents', '해결법 모음과 지난 사건', S(query=st), past_incidents, max_calls=2),
        Tool('git_log', '파일·폴더의 최근 커밋', S(path=st), git_log, max_calls=3),
        submit_tool('분석 결과 제출', {'type': 'object', 'properties': {
            'cause': {'type': 'string', 'description': '원인 한두 문장'},
            'confidence': {'type': 'string', 'enum': ['확실', '가능성 높음', '모름']},
            'evidence': {'type': 'array', 'items': {'type': 'string'}, 'description': '판단 근거(로그 줄, 상태값 등)'},
            'fix_steps': {'type': 'array', 'items': {'type': 'string'}, 'description': '해결 방법, 순서대로'},
            'human_needed': {'type': 'boolean', 'description': '사람이 해야 할 일이 있는가(로그인·코드 수정 등)'},
            'known_issue': {'type': 'string', 'description': '해결법 모음의 key (해당할 때)'}},
            'required': ['cause', 'confidence', 'evidence', 'fix_steps', 'human_needed']}),
    ]
    system = """너는 SNS 자동 발행 시스템의 실패 원인 분석가다. 읽기 도구만 있다. 아무것도 고치거나 끄거나 로그인하지 않는다.
순서: past_incidents 로 비슷한 해결법을 먼저 보고 → job_status → 로그 → (필요하면) 계정·프로세스·잠금 상태 → 스크린샷 → 코드.
원인은 근거가 있을 때만 '확실', 정황만 있으면 '가능성 높음', 모르면 '모름'으로 낸다. 추측을 사실처럼 쓰지 않는다.
해결 방법은 사람이 그대로 따라 할 수 있게 구체적으로(명령·화면 위치) 쓴다. 이미 저절로 풀렸으면 그렇다고 쓴다."""
    b = load_settings().get('incident', {}).get('budget', {})
    ev = '\n'.join(f"- {e['at']} {e.get('file', '')} {e['text']}" + (f" (스크린샷 {e['screenshot']})" if e.get('screenshot') else '')
                   for e in inc['evidence'][-8:])
    prompt = (f"사건: {inc['name']} ({inc['job']}) · 종류 {inc['kind']} · {inc['severity']} · {inc['count']}회 · "
              f"{inc['first']} ~ {inc['last']}\n문구: {inc['signature']}\n근거:\n<data>\n{ev}\n</data>\n원인을 찾아 제출하라.")
    r = Agent('incident', system, tools, Budget(max_tokens=int(b.get('max_tokens', 60000)),
                                                max_tool_calls=int(b.get('max_tool_calls', 20)),
                                                max_turns=int(b.get('max_turns', 12)), max_output=2000)).run(prompt)
    if r.status != 'submitted':
        print(json.dumps({'error': f'{r.status}: {r.detail}', 'log': r.log}, ensure_ascii=False))
        return
    print(json.dumps({**r.result, 'log': r.log, 'usage': r.usage}, ensure_ascii=False))


if __name__ == '__main__':
    main()
