@echo off
REM 주간 유튜브 Shorts 자동 발행 실행 배치 (작업 스케줄러가 호출)
cd /d "%~dp0"
".venv\Scripts\python.exe" run_weekly.py >> "logs\run.out.log" 2>&1
