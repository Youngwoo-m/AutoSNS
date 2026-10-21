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

# 실행 전 점검(jobs.json 의 precheck): 종료 코드 3 = 할 일 없음 → claude 를 부르지 않고 끝낸다. 그 밖의 실패는 그냥 돌린다.
PRECHECK=$(/usr/bin/python3 -c "import json,sys;j=next(j for j in json.load(open('$HERE/jobs.json'))['jobs'] if j['key']==sys.argv[1]);print(' '.join(j.get('precheck',[])))" "$JOB")
if [ -n "$PRECHECK" ]; then
    PRE_OUT=$(cd "$HERE" && $PRECHECK 2>&1); PRE_RC=$?
    if [ "$PRE_RC" = "3" ]; then
        echo "===== [$(date '+%F %T')] $JOB 시작 (점검: 할 일 없음) =====" >> "$LOG"
        echo "변화 없음: 처리할 요청이 없어 AI 를 부르지 않았습니다. ($PRE_OUT)" >> "$LOG"
        echo "{\"at\":\"$(date '+%Y-%m-%dT%H:%M%z')\",\"status\":\"skipped\",\"title\":null,\"urls\":{},\"review\":\"n/a\",\"calc\":\"n/a\",\"note\":\"사전 점검: 접수 없음, AI 호출 생략\"}" >> "$HERE/state/$JOB.jsonl"
        echo "===== [$(date '+%F %T')] $JOB 끝 (코드 0, AI 호출 없음) =====" >> "$LOG"
        exit 0
    fi
fi

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
# 서브에이전트(숏츠 제작 등)가 길어져도 마지막 응답 뒤 10분 만에 끊기지 않게 기다리는 한도를 2시간으로 늘린다
# (2026-10-21 survey-shorts 17:00: 제작 에이전트가 백그라운드로 돌다 10분 뒤 끊겨 영상이 안 만들어졌다)
export CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS=7200000
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
# 지시문대로 껐어야 하지만, 실패·중단으로 Voicebox 가 켜진 채 남았으면 끈다(사람이 연 것은 두기)
/bin/bash "$ROOT/shared/voicebox.sh" down "$JOB" >/dev/null 2>&1
echo "===== [$(date '+%F %T')] $JOB 끝 (코드 $RC) =====" >> "$LOG"
# 실제 실행이 실패하면 카카오톡 '나에게'로 알린다(시험 실행은 알리지 않음). 알림 실패는 작업 결과를 바꾸지 않는다.
if [ "$RC" != "0" ] && [ "$AX_DRY" != "1" ]; then
    LAST=$(grep -v '^=====' "$LOG" | tail -3 | tr '\n' ' ' | cut -c1-120)
    "$ROOT/channels/naver-blog-auto/.venv/bin/python" "$ROOT/channels/naver-blog-auto/kakao_notify.py" \
        "[AX] 클로드 작업 실패: $JOB (코드 $RC) $LAST" >> "$LOG" 2>&1 \
        || echo "[$(date '+%F %T')] 카카오 실패 알림을 보내지 못함" >> "$LOG"
fi
exit $RC
