#!/bin/bash
# 주간 인스타 카드뉴스 자동 게시 래퍼 (launchd 가 호출). run.bat 의 macOS 판.
# 실제 인스타 카드뉴스 게시가 나가는 스크립트다. 손으로 확인하려다(예: --help) 발행이
# 나가는 사고를 막기 위해, 인자가 하나라도 붙으면 거부한다.
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다 — 실제 발행 스크립트라 거부합니다." >&2
    echo "  실제 실행 : $(basename "$0")   /   미리 보기 : ./.venv/bin/python run_weekly.py --dry-run" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
mkdir -p logs
exec ./.venv/bin/python run_weekly.py >> "logs/run.out.log" 2>&1
