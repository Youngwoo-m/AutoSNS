"""stdin JSON 을 받아 인스타그램 릴로 '실제' 게시하는 CLI 엔트리포인트.

youtube-shorts-auto/publish_career.py 가 subprocess 로 호출한다.
(insta-cardnews 자체 venv·config·크롬 프로필을 쓰도록 프로젝트 분리 유지)

입력(stdin) 예:
  {"reel": "/abs/path/video.mp4",
   "caption": "피드 본문(훅·요약)",
   "hashtags": ["재난안전","세명대학교", ...]}   # 첫 댓글로 게시됨

출력(stdout): {"status": "published" | "dry_run" | "error" | ...}
"""
import json
import sys

from post_instagram import post_reel


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as e:
        print(json.dumps({"status": "error", "error": f"bad stdin json: {e}"}))
        return
    if not data.get("reel"):
        print(json.dumps({"status": "error", "error": "no reel path"}))
        return
    try:
        # payload 에 "dry":true 면 '공유하기' 직전까지만(세션·플로우 점검용).
        res = post_reel(data, dry_run=bool(data.get("dry", False)))
        print(json.dumps(res, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"status": "error", "error": f"{type(e).__name__}: {e}"},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
