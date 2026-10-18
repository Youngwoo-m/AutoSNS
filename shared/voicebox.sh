#!/bin/bash
# Voicebox(내 목소리 TTS, http://127.0.0.1:17493)를 필요할 때만 켜고, 다 쓰면 꺼서 메모리를 돌려준다.
#   shared/voicebox.sh up        켜고 API가 응답할 때까지 기다림(최대 3분). 이미 켜져 있으면 바로 끝
#   shared/voicebox.sh down      이 스크립트가 켠 것이고 다른 사용자가 없으면 끔
#   shared/voicebox.sh run -- 명령 …   켜고 → 명령 실행 → 끔(명령 종료 코드를 그대로 돌려줌)
#   shared/voicebox.sh up survey-daily / down survey-daily   여러 번의 셸에 걸쳐 쓸 때는 이름으로
#   shared/voicebox.sh status
# 사람이 직접 연 Voicebox 는 끄지 않는다. 여러 작업이 함께 쓰면 마지막 작업이 끝날 때 끈다.
# 켜기는 ~/bin/voicebox_launch.sh(임시 폴더를 USB256 으로) 를 그대로 쓴다.
PORT=17493
STATE=/Volumes/USB256/VoiceboxTmp/.ax
USERS="$STATE/users"
OURS="$STATE/started_by_ax"
LOG="$HOME/bin/logs/voicebox_launch.log"
ts() { date '+%Y-%m-%d %H:%M:%S'; }
alive() { curl -s -o /dev/null -m 3 "http://127.0.0.1:$PORT/profiles"; }
running() { pgrep -x voicebox >/dev/null || pgrep -f voicebox-server >/dev/null; }
mkdir -p "$USERS" 2>/dev/null

prune() {   # 끝난 작업이 남긴 사용 표시를 지운다(숫자=pid 는 죽었으면, 이름은 4시간 지나면)
    for f in "$USERS"/*; do
        [ -e "$f" ] || continue
        n=$(basename "$f")
        if [[ "$n" =~ ^[0-9]+$ ]]; then kill -0 "$n" 2>/dev/null || rm -f "$f"
        elif [ -n "$(find "$f" -mmin +240 2>/dev/null)" ]; then rm -f "$f"; fi
    done
}

up() {
    local who="${1:-$PPID}"
    prune
    touch "$USERS/$who"
    if alive; then return 0; fi
    if ! running; then
        touch "$OURS"
        echo "[$(ts)] 필요해서 켬 (pid $who)" >> "$LOG"
        /bin/bash "$HOME/bin/voicebox_launch.sh"
    fi
    for _ in $(seq 1 90); do alive && return 0; sleep 2; done
    echo "Voicebox 가 3분 안에 응답하지 않습니다" >&2
    return 1
}

down() {
    local who="${1:-$PPID}"
    rm -f "$USERS/$who"
    prune
    if [ -n "$(ls -A "$USERS" 2>/dev/null)" ]; then return 0; fi      # 아직 쓰는 작업이 있음
    [ -e "$OURS" ] || return 0                                        # 사람이 연 것 — 두기
    osascript -e 'quit app "Voicebox"' 2>/dev/null
    for _ in $(seq 1 30); do pgrep -x voicebox >/dev/null || break; sleep 1; done
    pkill -TERM -f voicebox-server 2>/dev/null
    for _ in $(seq 1 20); do pgrep -f voicebox-server >/dev/null || break; sleep 1; done
    pkill -KILL -f voicebox-server 2>/dev/null
    rm -f "$OURS"
    echo "[$(ts)] 다 써서 끔" >> "$LOG"
}

case "$1" in
    up) up "$2" ;;
    down) down "$2" ;;
    run)
        shift; [ "$1" = "--" ] && shift
        up $$ || exit 1
        "$@"; RC=$?
        down $$
        exit $RC ;;
    status)
        prune
        if alive; then echo "켜짐(응답함)"; elif running; then echo "켜지는 중"; else echo "꺼짐"; fi
        [ -e "$OURS" ] && echo "자동으로 켠 것" || { running && echo "사람이 연 것(자동으로 끄지 않음)"; }
        echo "쓰는 작업: $(ls "$USERS" 2>/dev/null | tr '\n' ' ')" ;;
    *) sed -n 2,8p "$0"; exit 2 ;;
esac
