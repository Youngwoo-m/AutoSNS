@echo off
REM 주간 자동 포스팅 실행 래퍼 (작업 스케줄러가 호출)
cd /d "%~dp0"
".venv\Scripts\python.exe" run_weekly.py
