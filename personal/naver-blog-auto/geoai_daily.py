"""GeoAI 블로그(geoaina.blogspot.com) 하루 1편 자동 발행 — launchd 가 매일 호출한다.

무엇을 올리나:
  · 주 1회(config.geoai.brief_weekday, 기본 화요일) → 그 주의 GeoAI·생성형AI 뉴스 브리핑
  · 나머지 요일 → 개념 시리즈 1편(geoai_series.TOPICS 순서대로)
브리핑은 뉴스가 없거나 생성이 실패하면 시리즈로 대신한다(블로그가 하루를 비우지 않게).

글에 함께 붙는 것:
  · 이미지(기본: 가로 배너 1장, 설정에 따라 Gamma 카드뉴스) → 공개 GitHub 저장소에
    올리고 CDN 으로 건다(Blogger API 에는 이미지 업로드가 없어 외부 호스팅이 필요하다)
  · 그날 글을 유튜브 '게시물'(커뮤니티)에도 올린다 — 제목·요약·글 링크·쇼츠 링크·배너
  · 매일 쇼츠 영상 1편을 개인 유튜브 채널(@geoai-safety)에 올리고 글에 임베드한다.
    보통은 카드 영상(무료 TTS)이고, config.geoai.video_weekdays 인 날만 HeyGen
    아바타 아나운서 영상이다(크레딧이 들어 주 1회)
둘 다 실패해도 글 발행은 그대로 진행한다(있으면 더 좋은 것이지 조건이 아니다).

하루 1편 원칙: 블로그에 오늘 날짜 글이 이미 있으면 아무것도 하지 않는다.

사용:
    python geoai_daily.py --plan   # 오늘 무엇을 올릴지만 확인(API 호출 없음)
    python geoai_daily.py --dry    # 글·카드·대본까지 만들어 보고 발행/업로드는 안 함
    python geoai_daily.py --go     # 실제 발행 (run_geoai.sh 가 호출)

손으로 돌릴 때 쓰는 덧붙임 플래그:
    --force        오늘 이미 글이 있어도 한 편 더 올린다(하루 1편 가드 무시)
    --video        오늘이 영상 요일이 아니어도 영상을 만든다
    --no-video     영상 요일이어도 영상을 만들지 않는다
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime

from common import BASE_DIR, load_config, log, _deep_merge

WEEKDAY_KR = "월화수목금토일"
YT_DIR = os.path.join(os.path.dirname(BASE_DIR), "youtube-shorts-auto")


def _gcfg(cfg):
    return cfg.get("geoai") or {}


def _brief_day(cfg):
    return int(_gcfg(cfg).get("brief_weekday", 1))


def _video_style(cfg, argv=()):
    """오늘 만들 영상 종류. None 이면 안 만든다.

    · anchor — HeyGen 아바타(크레딧이 든다). geoai.video_weekdays 인 날만.
    · cards  — 카드 프레임 + 무료 TTS. 매일 올려도 추가 비용이 없다.
    --no-video 로 끄고, --video 로 카드 영상을 강제할 수 있다."""
    if "--no-video" in argv:
        return None
    g = _gcfg(cfg)
    if datetime.now().weekday() in (g.get("video_weekdays") or []):
        return "anchor"
    if g.get("daily_video", True) or "--video" in argv:
        return "cards"
    return None


def make_images(data, cfg, dry_run=False):
    """글에 넣을 이미지를 만들어 CDN 주소 목록을 돌려준다. 실패하면 빈 목록(글은 그대로).

    geoai.media_style:
      · banner(기본) — 가로 3:1 배너 1장. 글 흐름을 덜 끊고 Gamma 크레딧도 안 쓴다.
      · cards        — Gamma 카드뉴스 여러 장(geoai.cards.count).
      · none         — 이미지 없음."""
    style = (_gcfg(cfg).get("media_style") or "banner").lower()
    if style == "none":
        return []
    paths = []
    try:
        if style == "cards":
            if not (_gcfg(cfg).get("cards") or {}).get("enabled", True):
                return []
            from geoai_cards import make_cards
            paths = make_cards(data, cfg)
        else:
            from geoai_banner import make_banner
            paths = [make_banner(data, cfg)]
    except Exception as e:
        log(f"이미지 생성 건너뜀(글은 정상): {type(e).__name__}: {str(e)[:120]}")
        return []
    if dry_run:
        log(f"[DRY] 이미지 {len(paths)}장 생성됨(업로드 안 함): {paths[0] if paths else ''}")
        return []
    data["_local_images"] = paths        # 유튜브 게시물에 붙일 원본 파일 경로
    try:
        from geoai_assets import upload
        prefix = f"{datetime.now():%Y/%m/%Y%m%d_%H%M%S}"
        return upload(paths, prefix, cfg)
    except Exception as e:
        log(f"이미지 업로드 건너뜀(글은 정상): {type(e).__name__}: {str(e)[:120]}")
        return []




# launchd 가 정한 시각에는 아직 인터넷이 안 붙어 있을 때가 있다(2026-09-21 07:40 에
# oauth2.googleapis.com 에 닿지 못해 그날 아침 글이 통째로 빠졌다). 한 번 실패했다고
# 그 시간대를 버리지 않도록 잠시 기다렸다 다시 본다.
CHECK_TRIES = 5
CHECK_WAIT = 60          # 초. 5번이면 최대 4분쯤 기다린다


def _posts_today_retry(cfg):
    """오늘 올라간 글 제목 목록. 끝내 확인하지 못하면 None(그때만 중단한다)."""
    for i in range(1, CHECK_TRIES + 1):
        try:
            from geoai_blogger import service, blog_id, posts_today
            return posts_today(service(), blog_id(cfg))
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:80]}"
            if i < CHECK_TRIES:
                log(f"GeoAI: 발행 여부 확인 실패({last}) — {CHECK_WAIT}초 뒤 "
                    f"다시 시도합니다({i}/{CHECK_TRIES}).")
                time.sleep(CHECK_WAIT)
    log(f"GeoAI: 발행 여부를 {CHECK_TRIES}번 모두 확인하지 못했습니다({last}) — 중단합니다.")
    return None


def make_step_image(data, cfg, dry_run=False):
    """따라하기 단계를 그린 도식 PNG 를 올리고 CDN 주소를 준다. 없거나 실패하면 ""."""
    if not data.get("howto"):
        return ""
    try:
        from geoai_steps import make_steps
        path = make_steps(data, cfg)
    except Exception as e:
        log(f"따라하기 도식 건너뜀(글은 정상): {type(e).__name__}: {str(e)[:120]}")
        return ""
    if not path:
        return ""
    if dry_run:
        log(f"[DRY] 따라하기 도식 생성됨(업로드 안 함): {path}")
        return ""
    try:
        from geoai_assets import upload
        urls = upload([path], f"{datetime.now():%Y/%m/steps_%Y%m%d_%H%M%S}", cfg)
        return urls[0] if urls else ""
    except Exception as e:
        log(f"따라하기 도식 업로드 건너뜀(글은 정상): {type(e).__name__}: {str(e)[:120]}")
        return ""


def make_video(data, cfg, dry_run=False, heygen_video_id=None, style="cards"):
    """AI 아나운서 영상을 만들어 유튜브에 올리고 video_id 를 돌려준다.

    영상 제작은 youtube-shorts-auto 프로젝트(별도 venv)에서 돈다 — HeyGen·ffmpeg·
    유튜브 업로드가 모두 거기 있다. 실패는 삼킨다(영상 없이 글만 나간다)."""
    py = os.path.join(YT_DIR, ".venv", "bin", "python")
    if not os.path.exists(py):
        log("영상 건너뜀: youtube-shorts-auto/.venv 가 없습니다")
        return {}
    try:
        from geoai_script import make_payload
        payload = make_payload(data, cfg)
    except Exception as e:
        log(f"영상 대본 실패(글은 정상): {type(e).__name__}: {str(e)[:120]}")
        return {}
    payload["style"] = style
    if dry_run:
        # HeyGen 은 dry-run 이어도 영상을 만들면 크레딧이 나간다 — 대본만 보여주고 멈춘다.
        chars = sum(len(s["narration"]) for s in payload["scenes"])
        log(f"[DRY] {style} 영상 대본 {len(payload['scenes'])}장면/{chars}자 — "
            f"헤드라인: {payload['headline']} (영상 생성 안 함)")
        return {"status": "dry_run", "style": style, "script": payload}
    payload["dry_run"] = False
    payload["privacy"] = _gcfg(cfg).get("video_privacy", "public")
    if heygen_video_id:
        payload["heygen_video_id"] = heygen_video_id
    try:
        # HeyGen 생성이 수 분 걸린다 — 넉넉히 기다린다.
        p = subprocess.run([py, "geoai_video.py"], cwd=YT_DIR, input=json.dumps(payload),
                           text=True, capture_output=True, timeout=2400)
        lines = [l for l in (p.stdout or "").strip().splitlines() if l.strip()]
        out = json.loads(lines[-1]) if lines and lines[-1].startswith("{") else {}
        if not out:
            # 자식 로그를 넉넉히 남긴다 — 시간 초과 때 HeyGen video_id 가 여기 들어 있고,
            # 그 id 로 이어받으면 이미 나간 크레딧을 버리지 않는다.
            log(f"영상 결과를 읽지 못했습니다:\n{(p.stdout or '')[-600:]}\n"
                f"{(p.stderr or '')[-400:]}")
        else:
            log(f"영상: {out.get('status')} {out.get('url','')} ({out.get('seconds','?')}s)")
        return out
    except Exception as e:
        log(f"영상 제작 실패(글은 정상): {type(e).__name__}: {str(e)[:150]}")
        return {}


def _post_image(data, cfg):
    """게시물에 붙일 이미지. 글머리 배너를 2:1 비율로 다시 그린다.

    유튜브 게시물은 가로세로 2:5~5:2 만 받는다 — 3:1 배너는 그대로 올리면 거부된다."""
    try:
        from geoai_banner import make_banner
        return make_banner(data, cfg, size=(1200, 600))
    except Exception as e:
        log(f"게시물 이미지 생성 건너뜀({type(e).__name__}) — 글만 올립니다")
        return None


def post_community(data, post_url, cfg, dry_run=False, video_url=""):
    """그날 글을 유튜브 '게시물'(커뮤니티)에도 올린다.

    공개 API 가 없어 로그인 프로필을 쓴 브라우저 자동화다(youtube-shorts-auto 쪽).
    실패해도 삼킨다 — 블로그·영상은 이미 나간 뒤다."""
    py = os.path.join(YT_DIR, ".venv", "bin", "python")
    if not os.path.exists(py):
        return {}
    payload = {"title": data.get("title", ""), "summary": data.get("summary"),
               "url": post_url, "video_url": video_url,
               "image": _post_image(data, cfg)}
    try:
        cmd = [py, "geoai_community.py"] + ([] if dry_run else ["--go"])
        p = subprocess.run(cmd, cwd=YT_DIR, input=json.dumps(payload),
                           text=True, capture_output=True, timeout=600)
        lines = [l for l in (p.stdout or "").strip().splitlines() if l.startswith("{")]
        out = json.loads(lines[-1]) if lines else {}
        log(f"유튜브 게시물: {out.get('status') or out.get('error') or '응답 없음'}")
        return out
    except Exception as e:
        log(f"유튜브 게시물 건너뜀: {type(e).__name__}: {str(e)[:120]}")
        return {}


def post_threads(data, post_url, cfg, dry_run=False, video_url=""):
    """그날 글을 스레드에도 올린다(제목·요약·블로그 링크·해시태그).

    스레드 발행은 insta-cardnews 로그인 세션으로만 되므로 그쪽 venv 의 threads_cli.py
    를 부른다. 실패해도 삼킨다 — 블로그·영상은 이미 나간 뒤다."""
    def _one_line(v):
        """summary 는 글 종류에 따라 문자열이거나 문단 리스트다(시리즈 글은 리스트)."""
        if isinstance(v, (list, tuple)):
            v = next((str(x) for x in v if str(x).strip()), "")
        return str(v or "").strip().split("\n")[0]

    ig_dir = os.path.join(os.path.dirname(BASE_DIR), "insta-cardnews")
    py = os.path.join(ig_dir, ".venv", "bin", "python")
    cli = os.path.join(ig_dir, "threads_cli.py")
    if not (os.path.exists(py) and os.path.exists(cli)):
        log("쓰레드 건너뜀: insta-cardnews 쪽을 찾지 못함")
        return {}
    try:
        summary = _one_line(data.get("summary"))
        tags = [t for t in (data.get("labels") or data.get("tags") or []) if t][:5]
        link = post_url or video_url
        text = "\n\n".join(x for x in [
            data.get("title", "GeoAI 재난안전"), summary,
            ("▶ " + link) if link else "",
            " ".join("#" + str(t).replace(" ", "") for t in tags)] if x)[:500]
    except Exception as e:
        log(f"쓰레드 본문 조립 실패({type(e).__name__}: {str(e)[:100]}) — 건너뜀")
        return {}
    if dry_run:
        log(f"쓰레드(dry): {text[:60]}…")
        return {"status": "dry_run"}
    try:
        p = subprocess.run([py, "threads_cli.py"], cwd=ig_dir,
                           input=json.dumps({"text": text}), text=True,
                           capture_output=True, timeout=300)
        lines = [l for l in (p.stdout or "").strip().splitlines() if l.startswith("{")]
        out = json.loads(lines[-1]) if lines else {}
        log(f"쓰레드: {out.get('status') or out.get('error') or '응답 없음'}")
        return out
    except Exception as e:
        log(f"쓰레드 건너뜀: {type(e).__name__}: {str(e)[:120]}")
        return {}


def make_brief(dry=False):
    """GeoAI 판 뉴스 브리핑 글을 만든다 → (설정, data, 본문 HTML). 채널 안내는 붙이지 않는다.

    설정은 여기서 다시 읽는다 — SMUDS_EDITION 을 세운 뒤라야 geoai 에디션이 병합된다."""
    os.environ["SMUDS_EDITION"] = "geoai"
    from generate_content import generate            # 환경변수 반영 위해 지연 import
    from post_blogger import build_html
    cfg = load_config()                              # geoai 에디션이 병합된 설정
    data = generate()
    from blog_photo import photo_html
    data["photo_html"] = photo_html(data.get("title", ""), data.get("summary", ""), cfg, dry_run=dry)
    # 본문 HTML 은 학과 블로그와 같은 생성기를 쓰되, 끝의 CTA·링크 블록은 뺀다
    # (geoai_blogger.compose 가 GeoAI 채널 안내를 마지막에 한 번만 붙인다).
    body = build_html(data, _deep_merge(cfg, {"blogger": {"links": []},
                                              "blog": {"cta": {"text": "", "links": []}}}))
    return cfg, data, body


def plan(cfg=None):
    cfg = cfg or load_config()
    wd = datetime.now().weekday()
    return ("brief" if wd == _brief_day(cfg) else "series"), wd


def main():
    dry = "--dry" in sys.argv
    cfg = load_config()
    kind, wd = plan(cfg)

    if "--plan" in sys.argv:
        from geoai_series import next_topic, TOPICS
        idx, topic = next_topic()
        what = ("GeoAI 주간 브리핑" if kind == "brief"
                else f"시리즈 {idx}/{len(TOPICS)}편 — {topic[1] if topic else '남은 주제 없음'}")
        print(f"오늘({WEEKDAY_KR[wd]}요일) 예정: {what}")
        print(f"  이미지: {(cfg.get('geoai', {}).get('media_style') or 'banner')}"
              f" / 영상: {_video_style(cfg, sys.argv) or '없음'}")
        return

    if not dry and "--force" not in sys.argv:   # 하루 상한을 넘으면 멈춘다
        cap = max(int(_gcfg(cfg).get("posts_per_day", 1)), 1)
        done = _posts_today_retry(cfg)
        if done is None:                      # 끝내 확인하지 못했다
            raise SystemExit(1)
        # 따로 올리는 연재(예: 'NaGeoAI 실제 QGIS 실습')는 자동 편성 몫이 아니다 — 이것까지
        # 세니 아침에 실습 글이 올라간 날은 저녁 자동 글이 상한에 걸려 빠졌다(9/30, 10/1).
        # 토목시공기술사 연재(클로드 작업 claude.civil-daily·civil-friend 가 같은 블로그에 올림)도 별도 몫이다 —
        # 빼지 않으면 그 글이 상한을 먹어 GeoAI 저녁 글이 빠졌다(2026-10-18 18:00).
        skip = tuple(dict.fromkeys(list(_gcfg(cfg).get("cap_exclude_prefixes", ["NaGeoAI 실제 QGIS 실습"]))
                                   + ["NaGeoAI 실제 QGIS 실습", "[토목시공기술사]"]))
        other = [t for t in done if skip and t.startswith(skip)]
        if other:
            log(f"GeoAI: 상한 계산에서 제외한 별도 연재 {len(other)}편 — {other[0][:40]}")
            done = [t for t in done if not (skip and t.startswith(skip))]
        if len(done) >= cap:
            log(f"GeoAI: 오늘 이미 {len(done)}편 발행됨(상한 {cap}) — {done[0][:50]} (건너뜀)")
            return
        if done:
            log(f"GeoAI: 오늘 {len(done)}/{cap}편 발행됨 — 이어서 진행합니다.")

    log(f"===== GeoAI 블로그 {WEEKDAY_KR[wd]}요일 발행 시작({kind}) =====")
    from geoai_blogger import compose, publish
    from geoai_series import build_html as series_html, prepare, mark_posted

    data = body = None
    topic = None
    if kind == "brief":
        try:
            cfg, data, body = make_brief(dry=dry)
        except Exception as e:
            log(f"브리핑 실패({type(e).__name__}: {str(e)[:120]}) → 시리즈 1편으로 대체")
            data = None
    if data is None:                                  # 시리즈(또는 브리핑 실패 대체)
        os.environ.pop("SMUDS_EDITION", None)
        cfg = load_config()
        kind = "series"
        _, topic, data = prepare(cfg, check_blog=not dry)
        if data is None:
            log("올릴 글이 없습니다(시리즈 소진).")
            return
        step_url = make_step_image(data, cfg, dry_run=dry)
        # 사람이 찍어 둔 실제 화면 캡처가 shots/<slug>/ 에 있으면 그것을 쓴다(도식보다 앞선다).
        shots = {"cover": "", "steps": {}}
        if not dry and topic:
            from geoai_shots import upload_for
            shots = upload_for(topic[0], cfg, steps=data.get("howto"))
        from blog_photo import photo_html
        data["photo_html"] = photo_html(data.get("title", ""), " ".join(data.get("summary") or []),
                                        cfg, dry_run=dry)
        body = series_html(data, cfg, with_links=False,
                           step_image=step_url, shots=shots)

    images = make_images(data, cfg, dry_run=dry)
    style = _video_style(cfg, sys.argv)
    video = make_video(data, cfg, dry_run=dry, style=style) if style else {}
    html = compose(body, images, video.get("video_id", ""), cfg, data.get("title", ""))
    labels = data.get("tags", []) + (list(topic[3]) if topic else [])
    # 카테고리는 글마다 하나씩 반드시 붙는다(라벨 가젯이 카테고리 메뉴 구실을 한다).
    from geoai_series import category_of
    category = category_of(topic[0]) if topic else ""
    pinned = [category] if category else []
    # 이 카테고리의 첫 글인가 — Blogger 의 '선택한 라벨' 목록은 고정이라, 새 카테고리가
    # 생기면 사람이 라벨 가젯에 직접 체크해 줘야 메뉴에 뜬다. 그래서 알려 준다.
    first_of_category = False
    if category and not dry:
        try:
            from geoai_blogger import service, blog_id, has_label
            first_of_category = not has_label(service(), blog_id(cfg), category)
        except Exception as e:
            log(f"카테고리 첫 글 여부 확인 실패(무시): {type(e).__name__}")
    r = publish(data["title"], html, labels, dry_run=dry, cfg=cfg, pinned=pinned)
    r["kind"], r["title"] = kind, data["title"]
    if r.get("status") == "published" and topic:
        mark_posted(topic, data, r.get("url", ""))
    log(f"===== GeoAI 종료: {r.get('status') or r.get('error')} "
        f"(이미지 {len(images)}장, 영상 {video.get('style', '없음') if video.get('video_id') else 'X'}) =====")

    if r.get("status") == "published" or dry:      # 유튜브 게시물(커뮤니티)
        post_community(data, r.get("url", ""), cfg, dry_run=dry,
                       video_url=video.get("url", ""))
        # 스레드는 저녁 회차에서만 올린다. 아침·저녁 둘 다 올리면 월 60건대가 돼
        # 계정이 GeoAI 글로 도배된다(2026-09-28 결정). 저녁 회차 = --no-video.
        if "--no-video" in sys.argv or "--threads" in sys.argv:
            post_threads(data, r.get("url", ""), cfg, dry_run=dry,
                         video_url=video.get("url", ""))
        else:
            log("쓰레드 건너뜀: 아침 회차(저녁 회차에서만 올린다)")

    if not dry and r.get("status") == "published" and first_of_category:
        log(f"★ '{category}' 카테고리의 첫 글입니다 — Blogger 레이아웃 > 카테고리(라벨 "
            f"가젯) > 수정 에서 '{category}'를 체크해야 메뉴에 나타납니다.")

    if not dry and r.get("status") == "published":
        try:                                          # 카톡 알림(실패 무시)
            from kakao_notify import notify
            msg = (f"[GeoAI 블로그 발행] {kind}\n{data.get('title','')}"
                   + (f"\n영상: {video.get('url','')}" if video.get("url") else ""))
            if first_of_category:
                msg += (f"\n\n★ '{category}' 카테고리 첫 글입니다.\n"
                        f"Blogger 레이아웃 > 카테고리 가젯 > 수정 에서 "
                        f"'{category}'를 체크해 주세요(안 하면 메뉴에 안 뜹니다).")
            notify(msg, r.get("url") or _gcfg(cfg).get("url", ""))
        except Exception as e:
            log(f"카톡 알림 건너뜀: {type(e).__name__}")
    if dry:
        print(json.dumps({"post": r, "images": images, "video": video},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
