#!/bin/bash
# 주간 유튜브 Shorts 자동 발행 래퍼 (launchd 가 호출). run.bat 의 macOS 판.
# 실제 유튜브 Shorts 발행가 나가는 스크립트다. 손으로 확인하려다(예: --help) 발행이
# 나가는 사고를 막기 위해, 인자가 하나라도 붙으면 거부한다.
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다 — 실제 발행 스크립트라 거부합니다." >&2
    echo "  실제 실행 : $(basename "$0")   /   미리 보기 : ./.venv/bin/python run_weekly.py --check" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
# 발행 전 디스크 여유 점검(9/19 디스크 가득 참으로 전 매체 결방 뒤 추가). 모자라면 긴급
# 정리·카톡 알림만 하고 발행은 그대로 진행한다.
/usr/bin/python3 ../shared/diskguard.py 유튜브뉴스 || true
mkdir -p logs
exec ./.venv/bin/python run_weekly.py >> "logs/run.out.log" 2>&1
