#!/bin/bash
# 주간 서로이웃 선신청(안전형) 래퍼 — launchd 가 매주 금 21:00 호출.
# 신청 후 지난 신청분의 수락 현황을 집계해 카카오톡으로 알린다(집계 실패해도 신청은 유지).
cd "$(dirname "$0")" || exit 1
mkdir -p logs
./.venv/bin/python naver_buddy_request.py --go >> "logs/buddy.out.log" 2>&1
./.venv/bin/python buddy_report.py          >> "logs/buddy.out.log" 2>&1
