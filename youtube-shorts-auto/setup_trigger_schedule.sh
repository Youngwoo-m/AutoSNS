#!/bin/bash
# 사건 즉시 발행 트리거를 하루 5회(08/11/14/17/20시) 점검하도록 launchd 에 등록.
# 점검은 가볍다(뉴스만 확인). 큰 사건 + 쿨다운/상한 통과 시에만 유튜브에 발행한다.
# 사용법:  bash setup_trigger_schedule.sh   (해제: 아래 안내 참고)
set -e

LABEL="com.smuds.ytshorts.trigger"
DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -x "$DIR/run_trigger.sh" ]; then
  echo "run_trigger.sh 실행 권한이 없습니다: $DIR/run_trigger.sh" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$DIR/logs"

if launchctl list | grep -q "$LABEL"; then
  launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
  echo "기존 트리거 작업 제거됨: $LABEL"
fi

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>$LABEL</string>
  <key>ProgramArguments</key> <array><string>$DIR/run_trigger.sh</string></array>
  <key>WorkingDirectory</key> <string>$DIR</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>17</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>20</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>StandardOutPath</key>   <string>$DIR/logs/trigger.launchd.out.log</string>
  <key>StandardErrorPath</key> <string>$DIR/logs/trigger.launchd.err.log</string>
  <key>RunAtLoad</key>         <false/>
</dict>
</plist>
PLISTEOF

launchctl bootstrap "gui/$UID" "$PLIST"

echo ""
echo "등록 완료: '$LABEL' (매일 08/11/14/17시·20시 점검)"
echo "★ 실제 발행은 config.json 의 trigger.enabled 를 true 로 바꿔야 시작됩니다."
echo "지금 즉시 점검(테스트):  launchctl kickstart -p gui/$UID/$LABEL"
echo "발행 없이 판단만 보기:   ./.venv/bin/python check_trigger.py --dry"
echo "해제:                   launchctl bootout gui/$UID/$LABEL && rm \"$PLIST\""
