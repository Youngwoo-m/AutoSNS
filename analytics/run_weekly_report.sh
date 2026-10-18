#!/bin/zsh
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job report.weekly -- "$0" "$@"
# 주간 리포트 수집·생성. 소스마다 필요한 라이브러리가 달라 인터프리터를 나눠 부른다.
# 사용: ./run_weekly_report.sh [기준일 YYYY-MM-DD]
#      SMUDS_REPORT_DRYRUN=1 을 주면 수집·생성만 하고 메일은 보내지 않는다(점검용).
set -u
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
# 크롬 프로필을 여는 수집은 그 프로필 잠금을 쥐고 돈다 — 발행 작업과 겹치지 않고, 콘솔 브라우저도 빌려 쓸 수 있다(2026-10-19)
LOCKRUN() { local res="$1"; shift; /usr/bin/python3 "$ROOT/shared/axlock.py" run --job "report:${res#profile:}" --res "$res" --no-stop -- "$@"; }
TODAY="${1:-$(date +%Y-%m-%d)}"
SINCE="2026-03-01"

echo "== 네트워크 확인 =="
if ! ./wait_network.sh; then
  echo "!! 네트워크가 없어 수집을 건너뛴다. 이번 회차는 발송하지 않는다."
  exit 1
fi

echo "== 수집 시작 ($TODAY) =="
"$ROOT/youtube-shorts-auto/.venv/bin/python" collect_youtube.py || echo "!! 유튜브 수집 실패 — 직전 결과로 진행"
python3 collect_web.py "$SINCE"                                 || echo "!! 블로그·홈페이지 수집 실패 — 직전 결과로 진행"
python3 collect_blogger.py "$SINCE"                             || echo "!! 블로거 수집 실패 — 직전 결과로 진행"
python3 collect_x.py "$SINCE"                                   || echo "!! 엑스 수집 실패 — 직전 결과로 진행"
LOCKRUN profile:naver "$ROOT/naver-blog-auto/.venv/bin/python" collect_naver_stats.py || echo "!! 네이버 블로그 조회수 수집 실패 — 조회수 없이 진행"
LOCKRUN profile:insta "$ROOT/insta-cardnews/.venv/bin/python" collect_threads.py "$SINCE" || echo "!! 스레드 수집 실패 — 직전 결과로 진행"
LOCKRUN profile:insta "$ROOT/insta-cardnews/.venv/bin/python" collect_instagram.py "$SINCE" || echo "!! 인스타 수집 실패 — 직전 결과로 진행"

"$ROOT/naver-blog-auto/.venv/bin/python" collect_searchconsole.py || echo "!! 서치콘솔 수집 실패 — 건너뜀"

echo "== 리포트 생성 =="
REPORT="$(python3 build_report.py "$TODAY" | tail -1)"
echo "$REPORT"

# mail_config.json 이 있으면 그 계정으로 바로 발송한다. 없으면 파일만 남긴다.
if [[ "${SMUDS_REPORT_DRYRUN:-0}" == "1" ]]; then
  echo "== 드라이런: 메일 발송 건너뜀 =="
elif [[ -f mail_config.json && -f "$REPORT" ]]; then
  echo "== 메일 발송 =="
  SUBJECT="$(cat "${REPORT%.html}.subject.txt" 2>/dev/null || echo '[재난안전학과] SNS 주간 리포트')"
  python3 send_mail.py "$REPORT" "$SUBJECT" || echo "!! 메일 발송 실패"
else
  echo "메일 설정(mail_config.json) 없음 — 리포트 파일만 생성했습니다."
fi
