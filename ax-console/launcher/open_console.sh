#!/bin/bash
# AX 발행 콘솔 열기 — 바탕화면 아이콘(AX 발행 콘솔.app)이 부른다.
# 1) 콘솔 서버가 꺼져 있으면 켠다(launchd com.smuds.axconsole)  2) 주소창 없는 앱 창으로 연다
URL="http://127.0.0.1:8700"
LABEL="com.smuds.axconsole"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
up() { curl -s -o /dev/null --max-time 2 "$URL/"; }
if ! up; then
  if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
    launchctl kickstart -k "gui/$(id -u)/$LABEL"
  else
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
  fi
  for i in $(seq 1 20); do up && break; sleep 1; done
fi
if ! up; then
  osascript -e 'display alert "AX 발행 콘솔을 켜지 못했습니다" message "ax-console/data/logs/server.err.log 를 확인하세요." as warning'
  exit 1
fi
if [ -d "/Applications/Google Chrome.app" ]; then
  open -na "Google Chrome" --args --app="$URL" --window-size=1400,900
else
  open "$URL"
fi
