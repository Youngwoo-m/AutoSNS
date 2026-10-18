#!/bin/bash
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job naverbuddy.weekly -- "$0" "$@"
# 주간 서로이웃 선신청(안전형) 래퍼 — launchd 가 매주 금 21:00 호출.
# 신청 후 지난 신청분의 수락 현황을 집계해 카카오톡으로 알린다(집계 실패해도 신청은 유지).
#
# 이 스크립트는 '실제 신청'을 보낸다. 손으로 확인하려다 실수로 신청이 나가는 사고를
# 막기 위해, 인자가 하나라도 붙으면 아무 것도 하지 않고 거부한다(--help 포함).
#   실행 방법 : ./run_buddy.sh            (인자 없이 — launchd 도 이렇게 호출)
#   미리 보기 : ./.venv/bin/python naver_buddy_request.py        (dry-run, 신청 안 함)
#   집계만    : ./.venv/bin/python buddy_report.py --no-kakao
if [ "$#" -ne 0 ]; then
    cat >&2 <<'MSG'
run_buddy.sh: 인자를 받지 않습니다 — 실제 서로이웃 신청이 나가는 스크립트라 거부합니다.
  실제 실행 : ./run_buddy.sh
  미리 보기 : ./.venv/bin/python naver_buddy_request.py        (dry-run)
  집계만    : ./.venv/bin/python buddy_report.py --no-kakao
MSG
    exit 2
fi
cd "$(dirname "$0")" || exit 1
mkdir -p logs
# 신청 전에 누적 기록부터 백업(파일 유실 시 같은 사람에게 재신청되는 것을 막는다)
../backup_state.sh >> "logs/buddy.out.log" 2>&1
./.venv/bin/python naver_buddy_request.py --go >> "logs/buddy.out.log" 2>&1
./.venv/bin/python buddy_report.py          >> "logs/buddy.out.log" 2>&1
