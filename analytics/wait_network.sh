#!/bin/zsh
# 네트워크가 올라올 때까지 기다린다. launchd 가 부팅·절전 해제 직후 잡을 띄우면
# 아직 DNS 가 안 붙어 수집이 통째로 실패한다(2026-09-21 주간 리포트가 그랬다).
# 기본 10분까지 30초 간격으로 확인하고, 끝내 안 되면 1 을 돌려준다.
DEADLINE=$(( $(date +%s) + ${SMUDS_NET_WAIT:-600} ))
while :; do
  if curl -sS -m 8 -o /dev/null https://smtp.gmail.com 2>/dev/null \
     || curl -sS -m 8 -o /dev/null https://www.google.com 2>/dev/null; then
    return 0 2>/dev/null || exit 0
  fi
  [[ $(date +%s) -ge $DEADLINE ]] && { echo "!! 네트워크 대기 시간 초과"; return 1 2>/dev/null || exit 1; }
  echo "   네트워크 대기 중…"
  sleep 30
done
