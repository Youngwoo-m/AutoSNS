#!/bin/bash
# 재난 숏츠 음성 미리 만들기(launchd: 새벽 03:30 — Voicebox 가 시스템 부하를 많이 줘서 한가한 때 만든다, 2026-10-28)
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job disastershorts.prevoice -- "$0" "$@"
cd "$(dirname "$0")" || exit 1
mkdir -p ../logs
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
PY=/Volumes/USB256/devAPP/AutoSNS/channels/youtube-shorts-auto/.venv/bin/python
/bin/bash /Volumes/USB256/devAPP/AutoSNS/shared/voicebox.sh up disastershorts.prevoice
$PY prevoice.py >> ../logs/prevoice.log 2>&1
RC=$?
/bin/bash /Volumes/USB256/devAPP/AutoSNS/shared/voicebox.sh down disastershorts.prevoice
exit $RC
