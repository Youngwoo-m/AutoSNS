#!/bin/bash
# 진로 시리즈 주간 자동 발행 래퍼 (launchd 가 매주 화요일 호출).
# 실제 진로 시리즈 발행가 나가는 스크립트다. 손으로 확인하려다(예: --help) 발행이
# 나가는 사고를 막기 위해, 인자가 하나라도 붙으면 거부한다.
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다 — 실제 발행 스크립트라 거부합니다." >&2
    echo "  실제 실행 : $(basename "$0")   /   미리 보기 : ./.venv/bin/python publish_career.py --dry" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
mkdir -p logs
exec ./.venv/bin/python publish_career.py >> "logs/career_publish.out.log" 2>&1
