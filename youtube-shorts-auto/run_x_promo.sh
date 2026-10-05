#!/bin/bash
# X 학과 소개 영상 하루 1편 게시(launchd com.smuds.xpromo.daily, 매일 12:30). 실제로 게시된다.
# 확인만 하려면: ./.venv/bin/python x_promo.py --plan
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다 — 실제 게시 스크립트라 거부합니다." >&2
    echo "  미리 보기 : ./.venv/bin/python x_promo.py --plan" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
/usr/bin/python3 ../shared/diskguard.py X학과소개 || true
mkdir -p logs
exec ./.venv/bin/python x_promo.py >> "logs/x_promo.out.log" 2>&1
