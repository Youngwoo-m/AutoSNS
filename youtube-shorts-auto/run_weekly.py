"""주간 실행 엔트리포인트: 대본 생성 → 프레임 → TTS → 영상 → 유튜브 Shorts + 틱톡 실제 발행.
작업 스케줄러가 이걸 호출한다.

스케줄 실행만 '실제 발행'한다(dry_run=False 고정). 수동으로 youtube_upload.py /
tiktok_upload.py 를 직접 돌리면 기본 dry_run 이라 실수로 발행되지 않는다.
(naver/insta 프로젝트의 실수 발행 사고를 교훈 삼은 안전장치)
"""
import json
import os
import subprocess
import sys
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


def _event_signal(cfg):
    """수·토 슬롯이 '이번 주 큰 사건이 있었나'를 트리거와 같은 기준으로 판단한다.

    (event_or_None, 사유). 쿨다운·주간상한은 보지 않는다 — 여기서 알고 싶은 건
    '발행할 만한 사건이 존재하는가'뿐이고, 도배 방지는 트리거 쪽 몫이다.
    """
    from check_trigger import decide
    return decide(cfg)


def _publish_fallback(cfg, check_only=False):
    """큰 사건이 없는 주엔 뉴스를 억지로 만들지 않고 예약 시리즈(O·X 퀴즈) 1편을 올린다.

    행사·점검 기사로 채운 뉴스 숏폼이 조회수 중앙값 174로 가장 부진했던 실측 결과에 따른 것.
    publish_career.py 가 예약표에서 '미발행 최우선 편'을 골라 유튜브+인스타에 올린다.
    """
    kind = cfg.get("weekly", {}).get("fallback_kind", "quiz")
    # --now: 예정일과 무관하게 미발행 최우선 편. --check 는 같은 선택을 발행 없이 보여준다.
    args = ["--now", "--dry"] if check_only else ["--now"]
    log(f"대체 콘텐츠({kind}) {'미리보기' if check_only else '발행'}: publish_career.py {' '.join(args)}")
    env = {k: v for k, v in os.environ.items() if k != "SMUDS_EDITION"}
    p = subprocess.run([sys.executable, "publish_career.py", *args],
                       cwd=BASE_DIR, capture_output=True, text=True,
                       timeout=1800, env=env)
    for ln in (p.stdout or "").strip().splitlines()[-4:]:
        log(f"  {ln}")
    if p.returncode != 0:
        log(f"대체 콘텐츠 발행 실패(rc={p.returncode}): {(p.stderr or '')[-300:]}")
    return p.returncode == 0


def _threads_summary(data):
    """스레드 본문 요약 한 문장 — 글로 쓴 설명문 첫 문장.

    전에는 1장면 나레이션을 그대로 썼는데, 나레이션은 음성용이라 숫자가 한글로 풀려
    있다('공장과 창고 천팔백오십구 동', 9/30 스레드). 설명문에는 '1,859동'으로 적혀 있다.
    설명문이 없을 때만 나레이션을 쓴다."""
    import re
    desc = (data.get("description") or "").strip()
    # 첫 문장이 '제천 재난안전 소식입니다.' 같은 인사말이면 내용이 없다 — 25자 넘는
    # 첫 문장을 쓴다(앞 세 문장 안에서).
    sents = [x.strip() for x in re.split(r"(?<=[.!?。])\s+", desc.split("\n")[0]) if x.strip()]
    for x in sents[:3]:
        if len(x) > 25:
            return x
    return (data.get("scenes") or [{}])[0].get("narration", "")


def main(argv=()):
    check_only = "--check" in argv
    log("===== 주간 유튜브 Shorts + 인스타 + 틱톡 시작 ====="
        + (" [CHECK — 발행하지 않음]" if check_only else ""))

    # 0) 큰 사건이 없으면 뉴스를 만들지 않고 예약 시리즈로 대체한다 — 단 지정 요일만.
    #    수(중앙값 699)보다 토(250)가 약하고, 토요일은 아나운서 크레딧까지 쓰므로
    #    조용한 주의 토요일만 대체하고 수요일은 늘 뉴스로 둔다.
    cfg0 = load_config()
    wcfg0 = cfg0.get("weekly", {})
    fb_days = wcfg0.get("fallback_weekdays", [5])      # 5=토요일
    if wcfg0.get("fallback_when_quiet", True) and datetime.now().weekday() in fb_days:
        try:
            event, why = _event_signal(cfg0)
        except Exception as e:
            event, why = True, f"사건 판단 실패 → 뉴스로 진행({type(e).__name__})"
        if not event:
            log(f"뉴스 대신 예약 시리즈로 — {why}")
            _publish_fallback(cfg0, check_only=check_only)
            log("===== 종료(대체 발행) =====")
            return
        log(f"뉴스로 진행 — {why}")
    if check_only:
        wd = "월화수목금토일"[datetime.now().weekday()]
        why = ("뉴스 경로로 진행할 상황" if datetime.now().weekday() in fb_days
               else f"{wd}요일은 대체 대상이 아님(대체 요일 {fb_days}) — 늘 뉴스")
        log(f"===== 종료(CHECK: {why}) =====")
        return

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
        # 6-0'') 대본 자막 업로드(검색 색인·AI 요약이 내용을 읽는 통로)
        try:
            from make_captions import attach as attach_caption
            attach_caption(data, video_id=result.get("video_id"))
        except Exception as e:
            log(f"자막 업로드 건너뜀: {type(e).__name__}")
        # 6-0') 뉴스 재생목록 편입(연속 시청·구독 전환)
        try:
            from youtube_upload import add_to_playlist
            add_to_playlist(result.get("video_id"), kind="news", cfg=cfg)
        except Exception as e:
            log(f"재생목록 편입 건너뜀: {type(e).__name__}")
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

    # 쓰레드 텍스트 크로스포스트(설정 시). 헤드라인+요약+유튜브 링크+해시태그.
    try:
        ig_dir = os.path.join(os.path.dirname(BASE_DIR), "insta-cardnews")
        ig_py = os.path.join(ig_dir, ".venv", "bin", "python")
        url = result.get("url", "") if isinstance(result, dict) else ""
        if os.path.exists(os.path.join(ig_dir, "threads_cli.py")) and os.path.exists(ig_py):
            headline = data.get("title", "재난안전 소식")
            summary = _threads_summary(data)
            tags = [t for t in (data.get("hashtags") or []) if t.lower() != "shorts"][:5]
            text = "\n\n".join(x for x in [
                headline, summary, ("▶ " + url if url else ""),
                " ".join("#" + t for t in tags)] if x)[:500]
            env = {k: v for k, v in os.environ.items() if k != "SMUDS_EDITION"}
            p = subprocess.run([ig_py, "threads_cli.py"], cwd=ig_dir,
                               input=json.dumps({"text": text}), text=True,
                               capture_output=True, timeout=300, env=env)
            out = (p.stdout or p.stderr or "").strip().splitlines()
            log(f"쓰레드: {out[-1] if out else '(무응답)'}")
    except Exception as e:
        log(f"쓰레드 크로스포스트 건너뜀(유튜브는 정상): {type(e).__name__}: {e}")

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
    main(sys.argv[1:])
