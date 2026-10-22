#!/bin/bash
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job disastershorts.cleanup -- "$0" "$@"
# 발행 7일 지난 편의 Voicebox 음성 정리(launchd: 매일 05:20)
cd "$(dirname "$0")" || exit 1
mkdir -p ../logs
[ -d /Volumes/USB256 ] || exit 0
# 앱 안 기록을 지우려면 서버가 떠 있어야 해서 잠깐 켰다가 끈다
exec /bin/bash /Volumes/USB256/devAPP/AutoSNS/shared/voicebox.sh run -- /usr/bin/python3 cleanup.py >> ../logs/cleanup.log 2>&1
