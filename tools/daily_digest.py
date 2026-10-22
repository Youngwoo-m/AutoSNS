"""어제(또는 지정한 날) 자동 작업 결과를 카카오톡 '나에게'로 한 번에 알린다 — launchd com.smuds.digest.daily 가 매일 아침 부른다.

    python3 tools/daily_digest.py              # 어제 요약을 보낸다
    python3 tools/daily_digest.py --print      # 보내지 않고 화면에만
    python3 tools/daily_digest.py --date 2026-10-21

orchestrator.log(shared/axlock.py 가 남김)에서 그날의 시작·끝·건너뜀을 세고, 콘솔의 열린 장애 수를 붙인다.
카카오 메모는 200자 안이라 실패한 작업 이름은 앞쪽 몇 개만 적는다.
"""
import datetime
import glob
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / 'ax-console' / 'data' / 'logs' / 'orchestrator.log'
LINE = re.compile(r'^\[(\d{4}-\d\d-\d\d)T[\d:]+\] (?P<job>[^:\s]+): (?P<msg>.*)$')
SKIP_JOBS = ('t1', 't2', 't3', 't-bw', '시험', 'test')


def catalog_jobs():
    try:
        return {j['job'] for j in json.loads((ROOT / 'ax-console' / 'config' / 'automations.json').read_text())['jobs']}
    except (OSError, ValueError):
        return set()


def day_stats(day):
    ran, failed, skipped = {}, {}, []
    known = catalog_jobs()
    for ln in LOG.read_text(errors='ignore').splitlines():
        m = LINE.match(ln)
        if not m or m.group(1) != day:
            continue
        job, msg = m.group('job'), m.group('msg')
        if (known and job not in known) or job.startswith(SKIP_JOBS) or ':' in job:
            continue
        mm = re.match(r'끝 \(코드 (\d+),', msg)
        if mm:
            ran[job] = ran.get(job, 0) + 1
            if mm.group(1) != '0':
                failed[job] = failed.get(job, 0) + 1
        elif msg.startswith('건너뜀') and '비상 정지' not in msg:
            skipped.append(job)
    return ran, failed, skipped


def open_incidents():
    n = 0
    for f in glob.glob(str(ROOT / 'ax-console' / 'data' / 'incidents' / '*' / '*.json')):
        if '/archive/' in f:
            continue
        try:
            if json.loads(Path(f).read_text()).get('status') == 'open':
                n += 1
        except (OSError, ValueError):
            pass
    return n


def build(day):
    ran, failed, skipped = day_stats(day)
    head = f"[AX] {day[5:]} 자동 작업: 실행 {sum(ran.values())}건"
    if failed:
        names = ', '.join(j.replace('claude.', '') for j in list(failed)[:4])
        head += f" · 실패 {sum(failed.values())}건({names}{' 외' if len(failed) > 4 else ''})"
    else:
        head += ' · 실패 없음'
    if skipped:
        head += f" · 건너뜀 {len(skipped)}건"
    inc = open_incidents()
    head += f" · 열린 장애 {inc}건" if inc else ' · 열린 장애 없음'
    return head[:190]


def main(argv):
    day = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    if '--date' in argv:
        day = argv[argv.index('--date') + 1]
    text = build(day)
    print(text)
    if '--print' in argv:
        return 0
    nb = ROOT / 'channels' / 'naver-blog-auto'
    r = subprocess.run([str(nb / '.venv' / 'bin' / 'python'), str(nb / 'kakao_notify.py'), text],
                       capture_output=True, text=True, timeout=60)
    print((r.stdout or r.stderr).strip()[-200:])
    return r.returncode


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
