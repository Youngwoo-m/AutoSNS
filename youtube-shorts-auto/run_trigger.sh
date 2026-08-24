#!/bin/bash
# 사건 즉시 발행 트리거 점검 (launchd 가 하루 몇 번 호출).
# check_trigger.py 가 스스로 '큰 사건인지 + 쿨다운/상한'을 판단해, 조건일 때만 발행한다.
cd "$(dirname "$0")" || exit 1
mkdir -p logs
exec ./.venv/bin/python check_trigger.py >> "logs/trigger.out.log" 2>&1
