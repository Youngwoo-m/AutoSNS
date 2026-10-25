@echo off
REM 주간 인스타 카드뉴스 자동 게시. 작업 스케줄러가 이 배치를 호출한다.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" run_weekly.py
) else (
  python run_weekly.py
)
