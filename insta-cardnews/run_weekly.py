"""주간 실행 엔트리포인트: 카드 문구 생성 → Gamma 카드 PNG → 인스타 캐러셀 게시.
작업 스케줄러가 이걸 호출한다.

스케줄 실행만 '실제 게시'한다(dry_run=False 고정). 수동으로 post_instagram.py 를
직접 돌리면 항상 dry_run 이라 실수로 게시되지 않는다. (네이버 프로젝트의 실수 발행
사고를 교훈 삼은 안전장치)
"""
import os
from datetime import datetime

from common import load_config, log

# 토요일(weekday()==5)엔 AI 뉴스판(수요일은 기본 재난안전판).
if datetime.now().weekday() == 5:
    os.environ["SMUDS_EDITION"] = "ai"
from generate_cards import generate
from post_instagram import post_carousel, post_reel


def _make_cards(data):
    """config.card_renderer 에 따라 카드 이미지를 만든다. 기본 'local'(KoPubWorld)."""
    renderer = load_config().get("card_renderer", "local")
    if renderer == "gamma":
        from gamma_make import make_cards
        log("카드 렌더러: Gamma")
    else:
        from render_cards_local import make_cards
        log("카드 렌더러: 로컬(KoPubWorld)")
    return make_cards(data)


def main():
    log("===== 주간 인스타 카드뉴스 시작 =====")
    try:
        cfg = load_config()
        data = generate()           # 1) 뉴스 → 카드 문구
        _make_cards(data)           # 2) 카드 PNG 생성(data['images'] 채워짐)

        # 3) 게시: reel.enabled 면 배경음악 릴, 아니면 이미지 캐러셀
        if cfg.get("reel", {}).get("enabled"):
            from make_reel import make_reel
            make_reel(data)                              # 카드+음악 → 세로 영상
            result = post_reel(data, dry_run=False)      # 릴 게시
        else:
            result = post_carousel(data, dry_run=False)  # 캐러셀 게시
        log(f"===== 종료: {result.get('status')} (카드 {result.get('images')}장) =====")
    except Exception as e:
        log(f"===== 실패: {e} =====")
        raise


if __name__ == "__main__":
    main()
