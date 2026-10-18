#!/bin/bash
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job naverblog.weekly -- "$0" "$@"
# 주간 자동 포스팅 실행 래퍼 (launchd 가 호출). run.bat 의 macOS 판.
# 실제 네이버 블로그 포스팅가 나가는 스크립트다. 손으로 확인하려다(예: --help) 발행이
# 나가는 사고를 막기 위해, 인자가 하나라도 붙으면 거부한다.
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다 — 실제 발행 스크립트라 거부합니다." >&2
    echo "  실제 실행 : $(basename "$0")   /   미리 보기 : ./.venv/bin/python run_weekly.py --dry-run" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
# 발행 전 디스크 여유 점검(9/19 디스크 가득 참으로 전 매체 결방 뒤 추가). 모자라면 긴급
# 정리·카톡 알림만 하고 발행은 그대로 진행한다.
/usr/bin/python3 ../shared/diskguard.py 네이버블로그 || true
mkdir -p logs
exec ./.venv/bin/python run_weekly.py >> "logs/run.out.log" 2>&1
