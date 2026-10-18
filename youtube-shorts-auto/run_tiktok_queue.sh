#!/bin/bash
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job tiktok.queue -- "$0" "$@"
# 틱톡 대기열 — 유튜브 공개 30분 뒤 학과 틱톡에 1편씩 올린다(launchd com.smuds.tiktok.queue, 15분마다).
# 실제로 게시된다. 확인만 하려면: ./.venv/bin/python tiktok_queue.py --plan
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다 — 실제 게시 스크립트라 거부합니다." >&2
    echo "  미리 보기 : ./.venv/bin/python tiktok_queue.py --plan" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
# 올릴 것이 없으면 크롬을 띄우지 않고 바로 끝난다(15분마다 돌아도 부담이 없다).
./.venv/bin/python -c "import tiktok_queue as T,sys; e,_=T.pick(T._load()); sys.exit(0 if e else 3)" || exit 0
/usr/bin/python3 ../shared/diskguard.py 틱톡대기열 || true
mkdir -p logs
exec ./.venv/bin/python tiktok_queue.py >> "logs/tiktok_queue.out.log" 2>&1
