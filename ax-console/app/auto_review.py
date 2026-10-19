"""자동 진행용 출처·사실 검토 — source-reviewer 에이전트(claude CLI, Max 구독)를 불러 판정을 받는다.

    python auto_review.py <콘텐츠 폴더>   → JSON 한 줄 {verdict, summary, issues, ...}  (verdict: pass|fix|block|error)
원고를 고치지 않고 읽기 도구만 쓴다(Read·Grep·Glob·WebFetch·WebSearch).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(folder):
    folder = Path(folder)
    prompt = (f"원고 파일: {folder / '원문.md'}\n작업 종류: ax-console 자동 진행 콘텐츠 (학과/개인 SNS 글)\n"
              f"채널별 변환본은 같은 폴더의 변환본_*.md 이다. 원문의 출처·사실을 중심으로 검토하고, 보고 형식의 JSON 하나만 답하라.")
    env = {k: v for k, v in os.environ.items() if k != 'ANTHROPIC_API_KEY'}   # 구독 로그인으로만
    env['PATH'] = '/usr/local/bin:/opt/homebrew/bin:' + env.get('PATH', '/usr/bin:/bin')
    cmd = ['claude', '-p', '--agent', 'source-reviewer', '--output-format', 'json', '--no-session-persistence',
           '--permission-mode', 'dontAsk', '--allowedTools', 'Read', 'Grep', 'Glob', 'WebFetch', 'WebSearch']
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=900)
        d = json.loads(p.stdout)
        if d.get('is_error'):
            return {'verdict': 'error', 'summary': str(d.get('result'))[:200]}
        m = re.search(r'\{.*\}', d.get('result') or '', re.S)
        r = json.loads(m.group(0))
        if r.get('verdict') not in ('pass', 'fix', 'block'):
            return {'verdict': 'error', 'summary': '판정 형식 오류'}
        return r
    except Exception as e:
        return {'verdict': 'error', 'summary': f'{type(e).__name__}: {str(e)[:200]}'}


if __name__ == '__main__':
    print(json.dumps(run(sys.argv[1]), ensure_ascii=False))
