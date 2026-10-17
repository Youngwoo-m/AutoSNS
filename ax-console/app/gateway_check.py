"""세명대 AI 게이트웨이 키를 하나씩 아주 짧게 불러 보고 결과를 JSON 한 줄로 낸다.

콘솔 서버가 youtube-shorts-auto/.venv 파이썬으로, youtube-shorts-auto 폴더에서 부른다.
키 값은 출력하지 않는다(기본 / 추가1, 추가2 … 로만 표시).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'youtube-shorts-auto'))

from common import load_config  # noqa: E402
from shared.llm import DEFAULT_BASE, gateway_keys  # noqa: E402


def main():
    from anthropic import Anthropic
    cfg = load_config()
    g = cfg.get('llm_gateway') or {}
    base = g.get('base_url') or DEFAULT_BASE
    out = []
    for i, k in enumerate(gateway_keys(cfg)):
        name = '기본' if i == 0 else f'추가{i}'
        try:
            r = Anthropic(api_key=k, base_url=base, max_retries=0, timeout=40).messages.create(
                model='claude-sonnet-5', max_tokens=5, messages=[{'role': 'user', 'content': '확인'}])
            out.append({'key': name, 'ok': True, 'state': f'응답 정상 ({r.model})'})
        except Exception as e:
            msg = str(e)
            if 'credit' in msg.lower() or '402' in msg or 'quota' in msg.lower():
                msg = '크레딧 소진'
            elif '401' in msg or 'auth' in msg.lower():
                msg = '키 오류 (인증 실패)'
            out.append({'key': name, 'ok': False, 'state': msg[:160]})
    print(json.dumps({'base_url': base, 'keys': out}, ensure_ascii=False))


if __name__ == '__main__':
    main()
