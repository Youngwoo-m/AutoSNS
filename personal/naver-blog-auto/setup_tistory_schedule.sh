#!/bin/bash
# 티스토리 교차 발행 launchd 등록 — 매일 08:50 · 18:50.
# 사용법:  bash setup_tistory_schedule.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.smuds.tistory"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$DIR/logs"
launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>$LABEL</string>
  <key>ProgramArguments</key> <array><string>$DIR/run_tistory.sh</string></array>
  <key>WorkingDirectory</key> <string>$DIR</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>50</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>50</integer></dict>
  </array>
  <key>StandardOutPath</key>   <string>$DIR/logs/tistory.launchd.out.log</string>
  <key>StandardErrorPath</key> <string>$DIR/logs/tistory.launchd.err.log</string>
  <key>RunAtLoad</key>         <false/>
</dict>
</plist>
PLISTEOF
launchctl bootstrap "gui/$UID" "$PLIST"
echo "등록 완료: $LABEL  08:50 · 18:50"
echo "삭제: launchctl bootout gui/\$UID/$LABEL"
