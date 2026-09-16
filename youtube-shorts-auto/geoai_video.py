"""블로그 글 → AI 아나운서 뉴스브리핑 영상 → 개인 GeoAI 채널(@geoai-na) 업로드.

naver-blog-auto 의 GeoAI 발행 파이프라인이 이 파일을 subprocess 로 부른다
(프로젝트마다 venv 가 달라, insta-cardnews 를 부르는 방식과 같다).
입력은 표준입력 JSON, 출력은 마지막 줄의 결과 JSON 이다.

입력 예:
  {"headline": "위성 AI로 산사태 예측", "title": "...유튜브 제목...",
   "scenes": [{"heading": "...", "narration": "..."}, ...],
   "hashtags": ["GeoAI", ...], "sources": [{"title": "...", "link": "..."}],
   "description": "설명 첫 문단", "dry_run": true, "privacy": "public"}

채널·문구는 config.json 의 editions.geoai 가 정한다(제목 접두사·설명 꼬리말·고지문).
학과 채널 토큰(token.json)이 아니라 token_youtube_geoai.json 을 쓴다.
"""
import json
import os
import sys
from datetime import datetime

# 설정 병합보다 먼저 에디션을 정해야 한다(load_config 가 호출 시점에 환경변수를 읽는다).
os.environ["SMUDS_EDITION"] = "geoai"

from common import BASE_DIR, load_config, log          # noqa: E402
from heygen_anchor import make_news_anchor             # noqa: E402
from youtube_upload import upload                      # noqa: E402

TOKEN_PATH = os.path.join(BASE_DIR, "token_youtube_geoai.json")


def run(payload):
    cfg = load_config()
    if not os.path.exists(TOKEN_PATH) and not payload.get("dry_run", True):
        raise RuntimeError("token_youtube_geoai.json 이 없습니다 — "
                           "geoai_youtube_auth.py 로 채널 인증을 먼저 하세요.")
    scenes = payload.get("scenes") or []
    if not scenes:
        raise RuntimeError("scenes 가 비어 영상 대본을 만들 수 없습니다.")
    data = {
        "title": payload.get("title") or payload.get("headline", "GeoAI 뉴스"),
        "description": payload.get("description", ""),
        "scenes": scenes,
        "hashtags": payload.get("hashtags", []),
        "sources": payload.get("sources", []),
        "stamp": f"geoai_{datetime.now():%Y%m%d_%H%M%S}",
    }
    make_news_anchor(data, title=payload.get("headline"))   # data['video'] 채움
    privacy = payload.get("privacy") or cfg.get("youtube", {}).get("privacy", "public")
    r = upload(data, dry_run=payload.get("dry_run", True), privacy=privacy,
               token_path=TOKEN_PATH)
    out = {"status": r.get("status"), "video_id": r.get("video_id", ""),
           "url": r.get("url", ""), "video": data.get("video"),
           "seconds": data.get("video_seconds")}
    if r.get("video_id"):
        try:                                   # 대본 자막(검색·AI 요약이 읽는 통로)
            from make_captions import attach
            attach(data, video_id=r["video_id"], token_path=TOKEN_PATH)
        except Exception as e:
            log(f"자막 업로드 건너뜀: {type(e).__name__}: {str(e)[:100]}")
    return out


if __name__ == "__main__":
    payload = json.loads(sys.stdin.read() or "{}")
    if "--go" in sys.argv:
        payload["dry_run"] = False
    result = run(payload)
    print(json.dumps(result, ensure_ascii=False))
