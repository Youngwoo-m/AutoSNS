#!/bin/bash
# 주간 자동 포스팅 실행 래퍼 (launchd 가 호출). run.bat 의 macOS 판.
cd "$(dirname "$0")" || exit 1
mkdir -p logs
exec ./.venv/bin/python run_weekly.py >> "logs/run.out.log" 2>&1
