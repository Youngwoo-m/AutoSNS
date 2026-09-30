#!/bin/bash
# GeoAI 블로그 저녁 1편 — launchd 가 매일 18:00 호출한다(아침 07:40 은 run_geoai.sh).
#
# 아침과 다른 점은 영상을 만들지 않는 것뿐이다(--no-video). 카드 쇼츠를 하루 두 편
# 올리면 새 채널이 스팸처럼 보이고 렌더링·업로드 시간도 그만큼 길어진다.
#
# 인자를 받지 않는다 — 실행 즉시 실제 발행이라, 확인하려다 발행되는 사고를 막는다.
#   미리 보기 : ./.venv/bin/python geoai_daily.py --plan
#              ./.venv/bin/python geoai_daily.py --dry --no-video
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다 — 실제 발행 스크립트라 거부합니다." >&2
    echo "  미리 보기 : ./.venv/bin/python geoai_daily.py --plan" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
# 발행 전 디스크 여유 점검(9/19 디스크 가득 참으로 전 매체 결방 뒤 추가). 모자라면 긴급
# 정리·카톡 알림만 하고 발행은 그대로 진행한다.
/usr/bin/python3 ../shared/diskguard.py GeoAI저녁 || true
mkdir -p logs
exec ./.venv/bin/python geoai_daily.py --go --no-video >> "logs/geoai.log" 2>&1
