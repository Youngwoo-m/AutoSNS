#!/bin/bash
# GeoAI 글을 티스토리에 요약+원문 링크로 올린다 — launchd 가 매일 08:50 · 18:50 호출.
# GeoAI 발행(07:40 · 18:00)이 끝난 뒤에 돌도록 시각을 잡았다.
#
# 인자를 받지 않는다 — 실행 즉시 실제 발행이다.
#   미리 보기 : ./.venv/bin/python tistory_crosspost.py --plan
#              ./.venv/bin/python tistory_crosspost.py --dry
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다 — 실제 발행 스크립트라 거부합니다." >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
mkdir -p logs
# 같은 티스토리 크롬 프로필을 다른 작업(채용정보 tistory_jobs, Codex 기술사 연재 자동화 등)이
# 쓰고 있으면 크롬이 프로필을 못 열어 실패한다 → 비기를 최대 40분 기다린다(2026-10-18).
for i in $(seq 1 40); do
    pgrep -f "chrome-profile-tistory" >/dev/null || break
    [ "$i" -eq 1 ] && echo "[$(date '+%F %T')] 티스토리 크롬 프로필 사용 중 — 기다림" >> logs/tistory.log
    if [ "$i" -eq 40 ]; then
        echo "[$(date '+%F %T')] 40분 기다려도 프로필이 비지 않아 이번 회차를 건너뜀" >> logs/tistory.log
        exit 1
    fi
    sleep 60
done
exec ./.venv/bin/python tistory_crosspost.py --go >> "logs/tistory.log" 2>&1
