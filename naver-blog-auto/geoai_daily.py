"""GeoAI 블로그(geoaina.blogspot.com) 하루 1편 자동 발행 — launchd 가 매일 호출한다.

무엇을 올리나:
  · 주 1회(config.geoai.brief_weekday, 기본 화요일) → 그 주의 GeoAI·생성형AI 뉴스 브리핑
  · 나머지 요일 → 개념 시리즈 1편(geoai_series.TOPICS 순서대로)
브리핑은 뉴스가 없거나 생성이 실패하면 시리즈로 대신한다(블로그가 하루를 비우지 않게).

하루 1편 원칙: 블로그에 오늘 날짜 글이 이미 있으면 아무것도 하지 않는다.
(한 번에 몰아 올리면 Blogger 가 남용으로 보고 403 을 낸다 — career_series.py 에서 겪음)

사용:
    python geoai_daily.py --plan   # 오늘 무엇을 올릴지만 확인(API 호출 없음)
    python geoai_daily.py --dry    # 글을 만들어 보기만(발행 안 함)
    python geoai_daily.py --go     # 실제 발행 (run_geoai.sh 가 호출)
"""
import json
import os
import sys
from datetime import datetime

from common import load_config, log, _deep_merge

WEEKDAY_KR = "월화수목금토일"


def _brief_day(cfg):
    """브리핑 요일(0=월). config.geoai.brief_weekday, 기본 1(화)."""
    return int((cfg.get("geoai") or {}).get("brief_weekday", 1))


def publish_brief(dry_run=False, cfg=None):
    """GeoAI 판 뉴스 브리핑을 만들어 GeoAI 블로그에 올린다.

    네이버·학과 블로그에 쓰는 생성기를 그대로 쓰되, 에디션만 geoai 로 바꾼다
    (config.editions.geoai — 뉴스 질의·태그·제목이 GeoAI/생성형AI 쪽으로 교체된다)."""
    os.environ["SMUDS_EDITION"] = "geoai"
    from generate_content import generate            # 환경변수 반영 위해 지연 import
    from post_blogger import build_html
    from geoai_blogger import publish, gcfg

    cfg = load_config()                              # geoai 에디션이 병합된 설정
    data = generate()
    # 글 끝 채널 안내는 GeoAI 블로그용 링크로 바꿔 끼운다(build_html 은 blogger.links 를 본다).
    links = gcfg(cfg).get("links") or (cfg.get("blogger", {}) or {}).get("links") or []
    html = build_html(data, _deep_merge(cfg, {"blogger": {"links": links}}))
    r = publish(data["title"], html, data.get("tags", []), dry_run=dry_run, cfg=cfg)
    r["title"] = data["title"]
    r["kind"] = "brief"
    return r


def plan(cfg=None):
    cfg = cfg or load_config()
    wd = datetime.now().weekday()
    kind = "brief" if wd == _brief_day(cfg) else "series"
    return kind, wd


def main():
    dry = "--dry" in sys.argv
    only_plan = "--plan" in sys.argv
    cfg = load_config()
    kind, wd = plan(cfg)

    if only_plan:
        from geoai_series import next_topic, TOPICS
        idx, topic = next_topic()
        print(f"오늘({WEEKDAY_KR[wd]}요일) 예정: "
              + ("GeoAI 주간 브리핑" if kind == "brief"
                 else f"시리즈 {idx}/{len(TOPICS)}편 — {topic[1] if topic else '남은 주제 없음'}"))
        return

    # 오늘 이미 올라간 글이 있으면 멈춘다(밀린 실행·수동 재실행으로 두 편 나가는 것 방지).
    if not dry:
        try:
            from geoai_blogger import service, blog_id, posted_today
            t = posted_today(service(), blog_id(cfg))
            if t:
                log(f"GeoAI: 오늘 이미 발행됨 — {t[:50]} (건너뜀)")
                return
        except Exception as e:
            log(f"GeoAI: 오늘 발행 여부 확인 실패({type(e).__name__}: {str(e)[:80]}) — 중단합니다")
            raise SystemExit(1)

    log(f"===== GeoAI 블로그 {WEEKDAY_KR[wd]}요일 발행 시작({kind}) =====")
    r = None
    if kind == "brief":
        try:
            r = publish_brief(dry_run=dry, cfg=cfg)
        except Exception as e:
            log(f"브리핑 실패({type(e).__name__}: {str(e)[:120]}) → 시리즈 1편으로 대체")
            r = None
    if r is None or r.get("error"):
        os.environ.pop("SMUDS_EDITION", None)        # 시리즈는 기본 설정으로 쓴다
        from geoai_series import run as run_series
        r = run_series(dry_run=dry, cfg=load_config())
    log(f"===== GeoAI 종료: {r.get('status') or r.get('error')} =====")

    if not dry and r.get("status") == "published":
        try:                                          # 카톡 알림(실패 무시)
            from kakao_notify import notify
            notify(f"[GeoAI 블로그 발행] {r.get('kind')}\n{r.get('title','')}",
                   r.get("url") or (cfg.get("geoai") or {}).get("url", ""))
        except Exception as e:
            log(f"카톡 알림 건너뜀: {type(e).__name__}")
    if dry:
        print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
