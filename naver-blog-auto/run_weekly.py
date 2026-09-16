"""주간 실행 엔트리포인트: 글 생성 -> 발행. 작업 스케줄러가 이걸 호출한다.

요일별 에디션(카테고리) — 매일 1편씩. 요일마다 주제가 달라야 같은 뉴스가
반복되지 않는다(하루 걸러 같은 기사를 다루면 글도 검색도 손해다).
  월 → 정책·제도판      화 → 산업·신기술판    수 → 재난안전판(지역 뉴스)
  목 → 재해영향평가판    금 → 기업재난관리판    토 → GeoAI판
  일 → 생활안전판

스케줄 실행은 '실제 발행'한다(dry_run=False 고정). config 의 dry_run 은 수동 테스트용
안전장치로 남겨두어, 실수로 publish_naver.py 를 직접 돌려도 발행되지 않게 한다.
"""
import os
from datetime import datetime

from common import log


# 월=0 … 일=6. None = 기본(재난안전판).
WEEKDAY_EDITIONS = {
    0: ["policy"],      # 월 정책·제도
    1: ["industry"],    # 화 산업·신기술
    2: [None],          # 수 재난안전(제천·충북 지역 뉴스)
    3: ["impact"],      # 목 재해영향평가
    4: ["biz"],         # 금 기업재난관리
    5: ["ai"],          # 토 GeoAI
    6: ["living"],      # 일 생활안전
}


def _editions_for_today():
    """오늘 발행할 에디션 목록(요일 고정 배치)."""
    return WEEKDAY_EDITIONS.get(datetime.now().weekday(), [None])


def _run_one(edition):
    # 에디션 전환은 SMUDS_EDITION 환경변수로(‑> load_config 가 매 호출 시 읽음)
    if edition:
        os.environ["SMUDS_EDITION"] = edition
    else:
        os.environ.pop("SMUDS_EDITION", None)
    # 매번 새로 import 하면 모듈 캐시로 같은 함수라, 함수 안에서 load_config 를 다시 부르는
    # generate/publish 는 바뀐 환경변수를 반영한다.
    from generate_content import generate
    from publish_naver import publish
    label = edition or "재난안전"
    log(f"----- [{label}] 생성·발행 시작 -----")
    data = generate()
    result = publish(data, dry_run=False)   # 스케줄은 항상 실제 발행
    # 같은 글을 Blogger(구글 검색 색인용)에도 올린다 — 실패해도 네이버 발행에는 영향 없음
    blogger_url = ""
    try:
        from post_blogger import publish as blogger_publish
        br = blogger_publish(data, dry_run=False)
        blogger_url = br.get("url", "")
        log(f"Blogger: {br.get('status')} {blogger_url}")
    except Exception as e:
        log(f"Blogger 발행 건너뜀(네이버는 정상): {type(e).__name__}: {e}")
    log(f"----- [{label}] 종료: {result.get('status')} -----")
    try:                        # 카카오톡 발행 알림(실패 무시)
        from kakao_notify import notify
        notify(f"[SMUDS 발행완료] 네이버 블로그 [{label}]\n{data.get('title','')}\n"
               f"상태: {result.get('status')}"
               + (f"\n+ Blogger: {blogger_url}" if blogger_url else ""),
               "https://blog.naver.com")
    except Exception as e:
        log(f"카톡 알림 건너뜀: {type(e).__name__}")


def main():
    log("===== 주간 자동 포스팅 시작 =====")
    editions = _editions_for_today()
    ok = True
    for ed in editions:
        try:
            _run_one(ed)
        except Exception as e:
            ok = False
            # 한 판이 실패해도 나머지 판은 계속 진행(목요일 2글 중 하나 실패 대비)
            log(f"===== 실패({ed or '재난안전'}): {e} =====")
    log(f"===== 전체 종료(성공={ok}) =====")
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
