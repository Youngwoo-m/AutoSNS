#!/bin/bash
# 주간 서로이웃 선신청(안전형) 래퍼 — launchd 가 매주 금 21:00 호출.
cd "$(dirname "$0")" || exit 1
mkdir -p logs
exec ./.venv/bin/python naver_buddy_request.py --go >> "logs/buddy.out.log" 2>&1
