#!/bin/bash
# GeoAI 블로그(geoaina.blogspot.com)에 하루 1편 올린다 — launchd 가 매일 07:40 호출.
#
# 인자를 받지 않는다 — 실행 즉시 실제 발행이라, 확인하려다 발행되는 사고를 막는다.
#   미리 보기 : ./.venv/bin/python geoai_daily.py --plan   (무엇을 올릴지만)
#              ./.venv/bin/python geoai_daily.py --dry    (글까지 만들어 보고 발행은 안 함)
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다 — 실제 발행 스크립트라 거부합니다." >&2
    echo "  미리 보기 : ./.venv/bin/python geoai_daily.py --plan" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
# 발행 전 디스크 여유 점검(9/19 디스크 가득 참으로 전 매체 결방 뒤 추가). 모자라면 긴급
# 정리·카톡 알림만 하고 발행은 그대로 진행한다.
/usr/bin/python3 ../shared/diskguard.py GeoAI아침 || true
mkdir -p logs
exec ./.venv/bin/python geoai_daily.py --go >> "logs/geoai.log" 2>&1
