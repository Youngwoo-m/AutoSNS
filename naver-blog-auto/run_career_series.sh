#!/bin/bash
# 진로 시리즈 개별 글을 하루 2편씩 Blogger 에 올린다 — launchd 가 매일 10:30 호출.
#
# 한 번에 몰아 올리면 Blogger 가 글쓰기를 막는다(2026-09-16, 4편째부터 403).
# 하루 2편·편 사이 3분 간격으로 나눠 올리고, 이미 올라간 편은 건너뛴다.
# 8편이 다 올라가면 아무 일도 하지 않으므로 그때 이 잡을 내려도 된다.
#
# 인자를 받지 않는다 — 다른 발행 래퍼와 같은 이유(확인하려다 실제 발행되는 사고 방지).
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다." >&2
    echo "  미리 보기 : ./.venv/bin/python career_series.py --dry" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
mkdir -p logs
exec ./.venv/bin/python career_series.py >> "logs/career_series.log" 2>&1
