#!/bin/bash
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job xpromo.daily -- "$0" "$@"
# X 학과 소개 영상 하루 1편 게시(launchd com.smuds.xpromo.daily, 매일 12:30). 실제로 게시된다.
# 확인만 하려면: ./.venv/bin/python x_promo.py --plan
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다 — 실제 게시 스크립트라 거부합니다." >&2
    echo "  미리 보기 : ./.venv/bin/python x_promo.py --plan" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
/usr/bin/python3 ../../shared/diskguard.py X학과소개 || true
mkdir -p logs
exec ./.venv/bin/python x_promo.py >> "logs/x_promo.out.log" 2>&1
