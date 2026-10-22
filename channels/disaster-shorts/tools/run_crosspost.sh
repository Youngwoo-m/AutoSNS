#!/bin/bash
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job disastershorts.crosspost -- "$0" "$@"
# 재난 유형별 숏츠 교차 게시(launchd: 화·금 19:30, 21:00 재시도). 인자를 받지 않는다(실제 게시가 나간다).
if [ "$#" -ne 0 ]; then echo "인자를 받지 않습니다. 점검: .venv/bin/python crosspost.py <편> --dry" >&2; exit 2; fi
cd "$(dirname "$0")" || exit 1
mkdir -p ../logs
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
exec /Volumes/USB256/devAPP/AutoSNS/channels/youtube-shorts-auto/.venv/bin/python crosspost.py >> ../logs/crosspost.log 2>&1
