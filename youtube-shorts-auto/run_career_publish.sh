#!/bin/bash
# 진로 시리즈 주간 자동 발행 래퍼 (launchd 가 매주 화요일 호출).
cd "$(dirname "$0")" || exit 1
mkdir -p logs
exec ./.venv/bin/python publish_career.py >> "logs/career_publish.out.log" 2>&1
