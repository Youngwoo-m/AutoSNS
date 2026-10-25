#!/bin/bash
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job captionrecheck.weekly -- "$0" "$@"
# 주간 인스타 캡션 점검(안전형) — launchd 가 매주 일요일 21:00 호출.
# 인스타가 편집을 되돌리는 일이 있어(140건 중 3건 확인), 실물 캡션을 다시 보고
# 활성화 문구가 빠진 게시물만 채운다. 이미 정상이면 편집창만 열고 취소한다.
#
# 인자를 받지 않는다 — 손으로 확인하려다 실제 편집이 나가는 사고를 막기 위해서다.
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다 — 실제 게시물을 편집하는 스크립트입니다." >&2
    echo "  미리 보기 : ./.venv/bin/python ig_caption_boost.py --recheck   (dry-run)" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
mkdir -p logs
../../tools/backup_state.sh >> "logs/caption_recheck.log" 2>&1
exec ./.venv/bin/python ig_caption_boost.py --go 150 --recheck >> "logs/caption_recheck.log" 2>&1
