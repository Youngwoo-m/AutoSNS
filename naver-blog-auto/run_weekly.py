"""주간 실행 엔트리포인트: 글 생성 -> 발행. 작업 스케줄러가 이걸 호출한다.

요일별 에디션(카테고리):
  수 → 재난안전판(재난안전뉴스)
  목 → 재해영향평가판(재해영향평가) + 기업재난관리판(기업재난관리)  ※ 두 글
  토 → GeoAI판(GeoAI재난관리)

스케줄 실행은 '실제 발행'한다(dry_run=False 고정). config 의 dry_run 은 수동 테스트용
안전장치로 남겨두어, 실수로 publish_naver.py 를 직접 돌려도 발행되지 않게 한다.
"""
import os
from datetime import datetime

from common import log


def _editions_for_today():
    """오늘 발행할 에디션 목록. None = 기본(재난안전판)."""
    wd = datetime.now().weekday()   # 월=0 … 목=3, 토=5
    if wd == 5:
        return ["ai"]
    if wd == 3:
        return ["impact", "biz"]    # 목요일: 두 글(각자 카테고리)
    return [None]


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
    log(f"----- [{label}] 종료: {result.get('status')} -----")
    try:                        # 카카오톡 발행 알림(실패 무시)
        from kakao_notify import notify
        notify(f"[SMUDS 발행완료] 네이버 블로그 [{label}]\n{data.get('title','')}\n"
               f"상태: {result.get('status')}", "https://blog.naver.com")
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
