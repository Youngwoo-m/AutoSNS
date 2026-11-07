"""블로그 글 → 쇼츠 영상 → 개인 GeoAI 채널(@geoai-safety) 업로드.

영상은 두 가지다(payload 의 style):
  · cards(기본)  — 카드 프레임 + 무료 TTS 나레이션. 매일 올려도 추가 비용이 없다.
  · anchor       — HeyGen AI 아바타 아나운서. 크레딧이 들어 주 1회(화요일)만.

naver-blog-auto 의 GeoAI 발행 파이프라인이 이 파일을 subprocess 로 부른다
(프로젝트마다 venv 가 달라, insta-cardnews 를 부르는 방식과 같다).
입력은 표준입력 JSON, 출력은 마지막 줄의 결과 JSON 이다.

입력 예:
  {"headline": "위성 AI로 산사태 예측", "title": "...유튜브 제목...",
   "scenes": [{"heading": "...", "narration": "..."}, ...],
   "hashtags": ["GeoAI", ...], "sources": [{"title": "...", "link": "..."}],
   "description": "설명 첫 문단", "dry_run": true, "privacy": "public",
   "style": "cards | anchor",
   "heygen_video_id": "(선택) 앞서 요청해 둔 HeyGen 영상 id — 다시 만들지 않고 이어받는다"}

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
from make_video import make_video                      # noqa: E402
from render_frames import make_frames                  # noqa: E402
from tts import make_tts                               # noqa: E402
from youtube_upload import upload                      # noqa: E402

TOKEN_PATH = os.path.join(BASE_DIR, "token_youtube_geoai.json")


def run(payload):
    cfg = load_config()
    from shared import token_store            # 토큰은 암호화 저장소에 있다
    if not token_store.exists(TOKEN_PATH) and not payload.get("dry_run", True):
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
        "date_label": payload.get("label") or "",   # 띠 화면 날짜 자리(시리즈 표시)
    }
    style = (payload.get("style") or "cards").lower()
    if style == "anchor":
        # heygen_video_id 를 주면 앞서 요청해 둔 영상을 이어받는다(시간 초과로 놓친 건 복구).
        make_news_anchor(data, title=payload.get("headline"),
                         heygen_video_id=payload.get("heygen_video_id"))   # data['video'] 채움
    else:
        try:                                   # 뉴스 원본 이미지(있으면 카드 하단에 깔린다)
            from fetch_images import fetch_images
            fetch_images(data)
        except Exception as e:
            log(f"뉴스 이미지 수집 건너뜀: {type(e).__name__}")
        make_frames(data)                      # 세로 카드 프레임 PNG
        make_tts(data)                         # 장면별 한국어 TTS
        make_video(data)                       # 프레임+음성 → mp4
        log(f"카드 영상 완성: {data.get('video')} ({data.get('video_seconds','?')}s)")
    privacy = payload.get("privacy") or cfg.get("youtube", {}).get("privacy", "public")
    r = upload(data, dry_run=payload.get("dry_run", True), privacy=privacy,
               token_path=TOKEN_PATH)
    out = {"status": r.get("status"), "style": style, "video_id": r.get("video_id", ""),
           "url": r.get("url", ""), "video": data.get("video"),
           "seconds": data.get("video_seconds")}
    # 첫 댓글(질문 한 줄 + 채널 모음 링크). 학과 채널에만 있던 것을 GeoAI 채널에도 붙인다.
    # 댓글은 이 채널 토큰으로 달아야 한다 — 학과 계정으로 달리면 채널이 섞인다.
    ac = (cfg.get("youtube", {}) or {}).get("auto_comment", {}) or {}
    if r.get("video_id") and ac.get("enabled", False):
        try:
            from youtube_upload import post_top_comment
            post_top_comment(r["video_id"], data=data, cfg=cfg, token_path=TOKEN_PATH,
                             dry_run=bool(payload.get("dry_run", True)))
        except Exception as e:  # noqa: BLE001
            log(f"첫 댓글 건너뜀(영상은 정상): {type(e).__name__}: {str(e)[:100]}")
    if r.get("video_id") and data.get("captions_unreliable"):
        log("자막 업로드 건너뜀 — 녹음된 대본을 확인할 수 없는 영상입니다.")
    elif r.get("video_id"):
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
