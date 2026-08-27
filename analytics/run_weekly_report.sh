#!/bin/zsh
# 주간 리포트 수집·생성. 소스마다 필요한 라이브러리가 달라 인터프리터를 나눠 부른다.
# 사용: ./run_weekly_report.sh [기준일 YYYY-MM-DD]
set -u
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
TODAY="${1:-$(date +%Y-%m-%d)}"
SINCE="2026-03-01"

echo "== 수집 시작 ($TODAY) =="
"$ROOT/youtube-shorts-auto/.venv/bin/python" collect_youtube.py || echo "!! 유튜브 수집 실패 — 직전 결과로 진행"
python3 collect_web.py "$SINCE"                                 || echo "!! 블로그·홈페이지 수집 실패 — 직전 결과로 진행"
"$ROOT/insta-cardnews/.venv/bin/python" collect_instagram.py "$SINCE" || echo "!! 인스타 수집 실패 — 직전 결과로 진행"

echo "== 리포트 생성 =="
python3 build_report.py "$TODAY"
