#!/bin/bash
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job ytshorts.trigger -- "$0" "$@"
# 사건 즉시 발행 트리거 점검 (launchd 가 하루 몇 번 호출).
# check_trigger.py 가 스스로 '큰 사건인지 + 쿨다운/상한'을 판단해, 조건일 때만 발행한다.
cd "$(dirname "$0")" || exit 1
# 발행 전 디스크 여유 점검(9/19 디스크 가득 참으로 전 매체 결방 뒤 추가). 모자라면 긴급
# 정리·카톡 알림만 하고 발행은 그대로 진행한다.
/usr/bin/python3 ../shared/diskguard.py 유튜브트리거 || true
mkdir -p logs
exec ./.venv/bin/python check_trigger.py >> "logs/trigger.out.log" 2>&1
