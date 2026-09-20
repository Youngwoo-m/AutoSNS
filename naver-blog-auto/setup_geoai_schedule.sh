#!/bin/bash
# GeoAI 블로그 하루 2편 launchd 등록 — 아침 07:40(영상 포함) · 저녁 18:00(글만).
# 사용법:  bash setup_geoai_schedule.sh
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/Library/LaunchAgents" "$DIR/logs"

# 이름 | 실행파일 | 시 | 분 | 설명
JOBS=(
  "com.smuds.geoai.daily|run_geoai.sh|7|40|아침(영상 포함)"
  "com.smuds.geoai.evening|run_geoai_evening.sh|18|0|저녁(글만)"
)

for job in "${JOBS[@]}"; do
  IFS='|' read -r LABEL SCRIPT HOUR MIN DESC <<< "$job"
  PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

  if [ ! -x "$DIR/$SCRIPT" ]; then
    echo "$SCRIPT 를 찾을 수 없거나 실행 권한이 없습니다: $DIR/$SCRIPT" >&2
    exit 1
  fi

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
  <key>ProgramArguments</key> <array><string>$DIR/$SCRIPT</string></array>
  <key>WorkingDirectory</key> <string>$DIR</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MIN</integer></dict>
  </array>
  <key>StandardOutPath</key>   <string>$DIR/logs/geoai.launchd.out.log</string>
  <key>StandardErrorPath</key> <string>$DIR/logs/geoai.launchd.err.log</string>
  <key>RunAtLoad</key>         <false/>
</dict>
</plist>
PLISTEOF

  launchctl bootstrap "gui/$UID" "$PLIST"
  printf '등록 완료: %-26s %02d:%02d  %s\n' "$LABEL" "$HOUR" "$MIN" "$DESC"
done

echo ""
echo "하루 상한은 config.json 의 geoai.posts_per_day 로 정합니다(현재 2편)."
echo "등록 확인:  launchctl list | grep smuds.geoai"
echo "삭제:       launchctl bootout gui/\$UID/com.smuds.geoai.daily"
echo "            launchctl bootout gui/\$UID/com.smuds.geoai.evening"
echo ""
echo "주의: 실행 시각에 맥이 켜져 있어야 합니다(잠자기면 깨어난 뒤 실행)."
