#!/bin/bash
# 매일 07:40 에 run_geoai.sh 를 실행하는 launchd 등록 스크립트(GeoAI 블로그 하루 1편).
# 사용법:  bash setup_geoai_schedule.sh
set -e

LABEL="com.smuds.geoai.daily"
DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

if [ ! -x "$DIR/run_geoai.sh" ]; then
  echo "run_geoai.sh 를 찾을 수 없거나 실행 권한이 없습니다: $DIR/run_geoai.sh" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$DIR/logs"

if launchctl list | grep -q "$LABEL"; then
  launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
  echo "기존 작업 제거됨: $LABEL"
fi

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>            <string>$LABEL</string>
  <key>ProgramArguments</key> <array><string>$DIR/run_geoai.sh</string></array>
  <key>WorkingDirectory</key> <string>$DIR</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>40</integer></dict>
  </array>
  <key>StandardOutPath</key>   <string>$DIR/logs/geoai.launchd.out.log</string>
  <key>StandardErrorPath</key> <string>$DIR/logs/geoai.launchd.err.log</string>
  <key>RunAtLoad</key>         <false/>
</dict>
</plist>
PLISTEOF

launchctl bootstrap "gui/$UID" "$PLIST"

echo ""
echo "등록 완료: '$LABEL' (매일 07:40) — GeoAI 블로그 하루 1편"
echo "지금 바로 테스트:  launchctl kickstart -p gui/$UID/$LABEL   ※ 실제 발행됩니다"
echo "등록 확인:        launchctl list | grep $LABEL"
echo "삭제:             launchctl bootout gui/$UID/$LABEL && rm \"$PLIST\""
echo ""
echo "주의: 실행 시각에 맥이 켜져 있어야 합니다(잠자기면 깨어난 뒤 실행)."
