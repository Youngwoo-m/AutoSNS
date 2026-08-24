#!/bin/bash
# 주간 유튜브 Shorts 자동 발행 래퍼 (launchd 가 호출). run.bat 의 macOS 판.
cd "$(dirname "$0")" || exit 1
mkdir -p logs
exec ./.venv/bin/python run_weekly.py >> "logs/run.out.log" 2>&1
