"""jobs.json 대로 launchd 작업(com.smuds.claude.<key>)을 만들고 AX 콘솔 자동 작업 목록에 등록한다.

    python3 GeoAI_NA/claude-jobs/install.py            # plist 만들기 + automations.json 갱신(켜지는 않음)
    python3 GeoAI_NA/claude-jobs/install.py --load     # 만든 뒤 launchd 에 올림(정해진 시각에 실제 발행 시작)

켜기/끄기는 AX 콘솔 '자동 작업' 탭에서도 할 수 있다.
"""
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
AGENTS = Path.home() / 'Library' / 'LaunchAgents'
CATALOG = ROOT / 'ax-console' / 'config' / 'automations.json'


def main():
    jobs = json.loads((HERE / 'jobs.json').read_text())['jobs']
    cat = json.loads(CATALOG.read_text())
    keep = [j for j in cat['jobs'] if not j['job'].startswith('claude.')]
    # 콘솔에서 끈 이유(note)는 다시 만들어도 남긴다
    notes = {j['job']: {k: j[k] for k in ('note', 'last_note') if k in j} for j in cat['jobs'] if j['job'].startswith('claude.')}
    (HERE / 'logs').mkdir(exist_ok=True)
    for j in jobs:
        label = f"com.smuds.claude.{j['key']}"
        pl = {'Label': label,
              'ProgramArguments': ['/bin/bash', str(HERE / 'run_claude_job.sh'), j['key']],
              'WorkingDirectory': str(ROOT),
              'StartCalendarInterval': [{'Hour': h, 'Minute': j.get('minute', 0)} for h in j['hours']],
              'StandardOutPath': str(HERE / 'logs' / f"{j['key']}.launchd.out.log"),
              'StandardErrorPath': str(HERE / 'logs' / f"{j['key']}.launchd.err.log"),
              'RunAtLoad': False}
        f = AGENTS / f'{label}.plist'
        f.write_bytes(plistlib.dumps(pl))
        keep.append({'job': f"claude.{j['key']}", 'account': 'personal', 'name': j['name'],
                     'what': f"클로드(claude -p, {j['model']})가 지시문 jobs/{j['key']}.md 대로 작성·발행 (Codex '{j['codex']}' 에서 옮김)",
                     'entry': f"GeoAI_NA/claude-jobs/jobs/{j['key']}.md", 'channels': j['channels'],
                     **notes.get(f"claude.{j['key']}", {})})
        print('작성', f.name)
        if '--load' in sys.argv:
            uid = os.getuid()
            subprocess.run(['launchctl', 'enable', f'gui/{uid}/{label}'])
            subprocess.run(['launchctl', 'bootout', f'gui/{uid}/{label}'], capture_output=True)
            r = subprocess.run(['launchctl', 'bootstrap', f'gui/{uid}', str(f)], capture_output=True, text=True)
            print('  올림' if r.returncode == 0 else f'  올리기 실패: {r.stderr.strip()}')
    cat['jobs'] = keep
    tmp = CATALOG.with_suffix('.tmp')
    tmp.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(CATALOG)
    print('automations.json 갱신')


if __name__ == '__main__':
    main()
