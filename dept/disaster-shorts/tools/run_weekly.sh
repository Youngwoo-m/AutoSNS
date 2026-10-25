#!/bin/bash
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job disastershorts.weekly -- "$0" "$@"
# 재난 유형별 숏츠 주간 자동 제작(launchd: 일·월 20:00). 인자를 받지 않는다(실제 업로드가 나가는 스크립트).
if [ "$#" -ne 0 ]; then echo "인자를 받지 않습니다. 미리 보기: .venv/bin/python weekly.py --check" >&2; exit 2; fi
cd "$(dirname "$0")" || exit 1
mkdir -p ../logs
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
/Volumes/USB256/devAPP/AutoSNS/channels/youtube-shorts-auto/.venv/bin/python weekly.py >> ../logs/weekly.log 2>&1
RC=$?
# weekly.py 가 켠 Voicebox 를 끈다(사람이 연 것·다른 작업이 쓰는 중이면 두기)
/bin/bash /Volumes/USB256/devAPP/AutoSNS/shared/voicebox.sh down disastershorts.weekly
exit $RC
