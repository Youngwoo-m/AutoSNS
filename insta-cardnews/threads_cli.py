"""stdin JSON 으로 쓰레드 텍스트 게시(다른 프로젝트에서 subprocess 로 호출).

입력 예: {"text": "본문..."}  또는  {"data": {뉴스 data}}
파이프라인(실제 발행) 경로이므로 dry_run=False 로 게시하되, 최종 안전 게이트는
config.threads.enabled 다(enabled=false 면 post() 가 자동으로 dry-run 으로 강등).
"""
import json
import sys

from post_threads import post


def main():
    payload = json.loads(sys.stdin.read() or "{}")
    res = post(text=payload.get("text"), data=payload.get("data"),
               dry_run=payload.get("dry", False))
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
