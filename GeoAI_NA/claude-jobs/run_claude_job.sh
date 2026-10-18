#!/bin/bash
# AX 오케스트레이터: 잠금·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job "claude.$1" -- "$0" "$@"
# Codex 자동화에서 옮긴 개인 계정 글 작업을 claude -p 로 돌린다 — launchd com.smuds.claude.<작업> 이 호출.
#   ./run_claude_job.sh nordic            실제 실행(발행됨)
#   AX_DRY=1 ./run_claude_job.sh nordic   시험 실행(발행기는 발행 직전에 멈추고, 대기열·카톡·상태는 건드리지 않음)
#   AX_DRY=1 AX_HOUR=12 ./run_claude_job.sh safekorea   회차(jobs.json runs)를 12시로 가정해 시험
# 지시문 = 공통규칙.md + 실행 정보 + jobs/<작업>.md. 티스토리 크롬은 발행기(tistory_post.py)가 잠금을 잡고 연다.
JOB="$1"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT=/Volumes/USB256/devAPP/AutoSNS
export PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
[ -n "$JOB" ] && [ -f "$HERE/jobs/$JOB.md" ] || { echo "작업 지시문이 없습니다: $JOB" >&2; exit 2; }
mkdir -p "$HERE/logs" "$HERE/state"
LOG="$HERE/logs/$JOB.log"
MODEL=$(/usr/bin/python3 -c "import json,sys;print(next(j.get('model','opus') for j in json.load(open('$HERE/jobs.json'))['jobs'] if j['key']==sys.argv[1]))" "$JOB")
RUN_NOTE=$(/usr/bin/python3 -c "import json,sys,datetime;j=next(j for j in json.load(open('$HERE/jobs.json'))['jobs'] if j['key']==sys.argv[1]);print(j.get('runs',{}).get(sys.argv[2],''))" "$JOB" "${AX_HOUR:-$(date +%-H)}")

PROMPT=$(mktemp -t claudejob)
{
    cat "$HERE/공통규칙.md"
    echo
    echo "# 이번 실행"
    echo "- 작업: $JOB (launchd com.smuds.claude.$JOB, 작업 기록 GeoAI_NA/claude-jobs/state/$JOB.jsonl)"
    echo "- 시각: $(date '+%Y-%m-%d %H:%M %Z (%a)')"
    [ -n "$AX_HOUR" ] && echo "- (시험용: 회차는 ${AX_HOUR}시로 가정한다)"
    [ -n "$RUN_NOTE" ] && echo "- 회차: $RUN_NOTE"
    if [ "$AX_DRY" = "1" ]; then echo "- **시험 실행(AX_DRY=1)** — 공통 규칙의 '시험 실행'대로 한다."; else echo "- 실제 실행"; fi
    echo
    echo "# 작업 지시문"
    echo
    cat "$HERE/jobs/$JOB.md"
} > "$PROMPT"

echo "===== [$(date '+%F %T')] $JOB 시작 (모델 $MODEL${AX_DRY:+, 시험 실행}) =====" >> "$LOG"
cd "$ROOT" || exit 1
# 3시간이 지나도 안 끝나면 끊는다(멈춘 채로 다음 회차·잠금을 막지 않게)
claude -p --model "$MODEL" --permission-mode bypassPermissions --no-chrome \
    --add-dir /Volumes/USB256/기술사 --add-dir /Volumes/USB256/devAPP/safekorea --add-dir "$HOME/.codex/skills" \
    < "$PROMPT" >> "$LOG" 2>&1 &
PID=$!
( sleep 10800; kill "$PID" 2>/dev/null && echo "[$(date '+%F %T')] 3시간 초과로 중단" >> "$LOG" ) &
WATCH=$!
wait "$PID"; RC=$?
kill "$WATCH" 2>/dev/null; wait "$WATCH" 2>/dev/null
rm -f "$PROMPT"
echo "===== [$(date '+%F %T')] $JOB 끝 (코드 $RC) =====" >> "$LOG"
# 실제 실행이 실패하면 카카오톡 '나에게'로 알린다(시험 실행은 알리지 않음). 알림 실패는 작업 결과를 바꾸지 않는다.
if [ "$RC" != "0" ] && [ "$AX_DRY" != "1" ]; then
    LAST=$(grep -v '^=====' "$LOG" | tail -3 | tr '\n' ' ' | cut -c1-120)
    "$ROOT/naver-blog-auto/.venv/bin/python" "$ROOT/naver-blog-auto/kakao_notify.py" \
        "[AX] 클로드 작업 실패: $JOB (코드 $RC) $LAST" >> "$LOG" 2>&1 \
        || echo "[$(date '+%F %T')] 카카오 실패 알림을 보내지 못함" >> "$LOG"
fi
exit $RC
