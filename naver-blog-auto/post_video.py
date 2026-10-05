"""유튜브 발행 후 그 영상을 네이버 블로그 '동영상뉴스' 카테고리에 함께 올린다.

youtube-shorts-auto 가 업로드를 마친 뒤 이 스크립트를 서브프로세스로 호출하며,
표준입력(stdin)으로 JSON 페이로드를 넘긴다:
  {"title": ..., "body": ..., "youtube_url": ..., "sources": [...],
   "category": "동영상뉴스", "dry_run": false}

네이버 로그인/프로필은 이 프로젝트(naver-blog-auto)에 있으므로, 네이버 발행은
반드시 이 프로젝트 안에서 실행되어야 한다.
"""
import json
import sys

from common import log
from publish_naver import publish


def main():
    raw = sys.stdin.read()
    try:
        p = json.loads(raw)
    except Exception as e:
        log(f"post_video: 페이로드 파싱 실패: {e}")
        return 1

    url = (p.get("youtube_url") or "").strip()
    if not url:
        log("post_video: youtube_url 이 없어 중단합니다.")
        return 1

    data = {
        "title": p.get("title", "재난안전 동영상 뉴스"),
        "body": p.get("body", "이번 영상으로 정리한 재난안전 소식입니다."),
        "video_url": url,
        "sources": p.get("sources", []),
        "category": p.get("category", "동영상뉴스"),
        "tags": p.get("tags", []),   # 네이버 태그(최대 10개) — 없으면 예전처럼 태그 없이
        "no_banner": True,   # 배너 대신 동영상이 대표
    }
    dry = bool(p.get("dry_run", False))
    log(f"===== 동영상 뉴스 발행: {data['title'][:40]} (dry={dry}) =====")
    r = publish(data, dry_run=dry)
    log(f"동영상 뉴스: {r.get('status')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
