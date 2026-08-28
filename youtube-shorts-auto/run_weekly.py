"""주간 실행 엔트리포인트: 대본 생성 → 프레임 → TTS → 영상 → 유튜브 Shorts + 틱톡 실제 발행.
작업 스케줄러가 이걸 호출한다.

스케줄 실행만 '실제 발행'한다(dry_run=False 고정). 수동으로 youtube_upload.py /
tiktok_upload.py 를 직접 돌리면 기본 dry_run 이라 실수로 발행되지 않는다.
(naver/insta 프로젝트의 실수 발행 사고를 교훈 삼은 안전장치)
"""
import json
import os
import subprocess
from datetime import datetime

from common import BASE_DIR, load_config, log
from generate_script import generate

# 토요일(weekday()==5)엔 AI 뉴스판으로 발행(수요일은 기본 재난안전판).
if datetime.now().weekday() == 5:
    os.environ["SMUDS_EDITION"] = "ai"
from fetch_images import fetch_images
from render_frames import make_frames
from tts import make_tts
from make_video import make_video
from youtube_upload import upload
from tiktok_upload import upload as tiktok_publish


def _post_instagram_reel(data, ai_label=False):
    """뉴스 영상을 인스타 릴로 발행(insta-cardnews venv subprocess). AI 아나운서면 AI 레이블."""
    ig_dir = os.path.join(os.path.dirname(BASE_DIR), "insta-cardnews")
    ig_py = os.path.join(ig_dir, ".venv", "bin", "python")
    video = data.get("video")
    if not (os.path.exists(ig_py) and video and os.path.exists(video)):
        log("인스타 발행 생략(venv/영상 없음)"); return
    headline = (data.get("scenes") or [{}])[0].get("heading", "재난안전 뉴스")
    caption = f"{headline}\n\n세명대학교 재난안전학과가 전하는 재난안전 뉴스입니다."
    if ai_label:
        caption += "\n" + load_config().get("heygen", {}).get("disclosure_text_short",
            "※ 재난안전학과 학과장 아바타를 AI로 자동 생성한 영상입니다.")
    caption += "\n\n팔로우하고 제천·충북 재난안전 소식 받기 👉 @smu_ds_official"
    payload = {"reel": os.path.abspath(video), "caption": caption,
               "hashtags": data.get("hashtags", []), "ai_label": ai_label}
    env = {k: v for k, v in os.environ.items() if k != "SMUDS_EDITION"}
    p = subprocess.run([ig_py, "post_reel_cli.py"], cwd=ig_dir, input=json.dumps(payload),
                       text=True, capture_output=True, timeout=600, env=env)
    out = (p.stdout or "").strip().splitlines()
    log(f"인스타 릴 발행: {out[-1] if out else '(무응답, stderr:' + (p.stderr or '')[-120:] + ')'}")


def main():
    log("===== 주간 유튜브 Shorts + 인스타 + 틱톡 시작 =====")
    try:
        data = generate()                 # 1) 뉴스 → 대본(장면+나레이션)
        cfg = load_config()

        # 2~5) 영상 만들기 — 아나운서 발행일(기본 토요일)만 'AI 아나운서', 그 외(수)엔 카드.
        #      아나운서 실패(크레딧·오류) 시에도 카드로 자동 폴백(발행이 멈추지 않게).
        made_anchor = False
        hcfg = cfg.get("heygen", {})
        anchor_days = hcfg.get("anchor_days", [5])   # 5=토요일만 아나운서, 수요일=카드
        if hcfg.get("anchor_news", False) and datetime.now().weekday() in anchor_days:
            try:
                from heygen_anchor import make_news_anchor
                make_news_anchor(data)    # data['video'] 세팅(제목 포함)
                made_anchor = True
                log("AI 아나운서 영상으로 발행합니다.")
            except Exception as e:
                log(f"아나운서 영상 실패 → 카드 영상으로 대체: {type(e).__name__}: {e}")
        if not made_anchor:
            fetch_images(data)            # 2) 뉴스 원본 이미지 수집(best-effort)
            make_frames(data)             # 3) 세로 카드 프레임 PNG(하단 이미지 포함)
            make_tts(data)                # 4) 장면별 한국어 TTS mp3
            make_video(data)              # 5) 프레임+음성 → 세로 mp4

        privacy = cfg.get("youtube", {}).get("privacy", "public")
        result = upload(data, dry_run=False, privacy=privacy)  # 6) 유튜브 실제 발행
        log(f"유튜브: {result.get('status')} {result.get('url','')}")
        # 6-0) 자동 첫 댓글(구독 유도·참여 마중물). enabled 이고 업로드 성공 시에만.
        if cfg.get("youtube", {}).get("auto_comment", {}).get("enabled", True):
            try:
                from youtube_upload import post_top_comment
                post_top_comment(result.get("video_id"), data=data)
            except Exception as e:
                log(f"자동 댓글 건너뜀(유튜브는 정상): {type(e).__name__}: {e}")
        # 6-1) 같은 영상을 네이버 '동영상뉴스' 카테고리에도 발행(설정 시)
        try:
            from crosspost import crosspost_naver_video
            crosspost_naver_video(data, result.get("url", ""), dry_run=False)
        except Exception as e:
            log(f"동영상뉴스 크로스포스트 건너뜀(유튜브는 정상): {type(e).__name__}")
        # 6-2) 아나운서 뉴스만 인스타 릴로 발행(카드 뉴스는 아침 instacards 잡이 담당 → 중복 방지)
        if made_anchor:
            try:
                _post_instagram_reel(data, ai_label=True)
            except Exception as e:
                log(f"인스타 릴 발행 건너뜀(유튜브는 정상): {type(e).__name__}: {e}")
    except Exception as e:
        log(f"===== 실패(유튜브 단계까지): {e} =====")
        raise

    # 7) 틱톡 발행 — 유튜브가 이미 성공했으므로, 틱톡 실패가 전체를 되돌리지 않게 분리.
    tk = cfg.get("tiktok", {})
    if tk.get("enabled", False):
        try:
            tr = tiktok_publish(data, dry_run=False)
            log(f"틱톡: {tr.get('status')} (privacy={tr.get('privacy','')})")
        except Exception as e:
            log(f"틱톡 발행 실패(유튜브는 정상): {e}")

    # 카카오톡 '나에게 보내기' 발행 알림(실패해도 발행에는 영향 없음)
    try:
        from kakao_notify import notify
        kind = "AI 아나운서 뉴스" if made_anchor else "카드뉴스"
        url = result.get("url", "") if isinstance(result, dict) else ""
        msg = (f"[SMUDS 발행완료] 유튜브 {kind}\n{data.get('title','재난안전 뉴스')}\n{url}\n"
               f"+ 네이버 동영상뉴스" + ("\n+ 인스타 릴" if made_anchor else ""))
        r = notify(msg, url or None)
        log(f"카톡 알림: {r}")
    except Exception as e:
        log(f"카톡 알림 건너뜀: {type(e).__name__}: {e}")
    log("===== 종료 =====")


if __name__ == "__main__":
    main()
