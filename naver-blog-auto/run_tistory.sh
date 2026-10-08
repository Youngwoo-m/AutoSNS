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
exec ./.venv/bin/python tistory_crosspost.py --go >> "logs/tistory.log" 2>&1
