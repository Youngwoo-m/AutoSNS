#!/bin/zsh
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job report.monthly -- "$0" "$@"
# 월간 리포트 수집·생성·발송. 매월 1일에 '방금 끝난 달'을 다룬다.
# 사용: ./run_monthly_report.sh [기준일 YYYY-MM-DD] [대상월 YYYY-MM]
#      SMUDS_REPORT_DRYRUN=1 을 주면 수집·생성만 하고 메일은 보내지 않는다(점검용).
set -u
cd -P "$(dirname "$0")"
ROOT="$(cd ../.. && pwd)"
# 크롬 프로필을 여는 수집은 그 프로필 잠금을 쥐고 돈다 — 발행 작업과 겹치지 않고, 콘솔 브라우저도 빌려 쓸 수 있다(2026-10-19)
LOCKRUN() { local res="$1"; shift; /usr/bin/python3 "$ROOT/shared/axlock.py" run --job "report:${res#profile:}" --res "$res" --no-stop -- "$@"; }
TODAY="${1:-$(date +%Y-%m-%d)}"
SINCE="2026-03-01"
HWPX_SKILL="$HOME/.claude/skills/hwpx-skill/scripts/md2hwpx.py"

echo "== 네트워크 확인 =="
if ! ./wait_network.sh; then
  echo "!! 네트워크가 없어 수집을 건너뛴다. 이번 회차는 발송하지 않는다."
  exit 1
fi

echo "== 수집 시작 ($TODAY) =="
"$ROOT/channels/youtube-shorts-auto/.venv/bin/python" collect_youtube.py || echo "!! 유튜브 수집 실패 — 직전 결과로 진행"
python3 collect_web.py "$SINCE"                                 || echo "!! 블로그·홈페이지 수집 실패 — 직전 결과로 진행"
LOCKRUN profile:naver "$ROOT/channels/naver-blog-auto/.venv/bin/python" collect_naver_stats.py || echo "!! 네이버 블로그 조회수 수집 실패 — 조회수 없이 진행"
python3 collect_blogger.py "$SINCE"                             || echo "!! 블로거 수집 실패 — 직전 결과로 진행"
python3 collect_x.py "$SINCE"                                   || echo "!! 엑스 수집 실패 — 직전 결과로 진행"
LOCKRUN profile:insta "$ROOT/channels/insta-cardnews/.venv/bin/python" collect_threads.py "$SINCE"   || echo "!! 스레드 수집 실패 — 직전 결과로 진행"
LOCKRUN profile:insta "$ROOT/channels/insta-cardnews/.venv/bin/python" collect_instagram.py "$SINCE" || echo "!! 인스타 수집 실패 — 직전 결과로 진행"

echo "== 월간 리포트 생성 =="
if [[ $# -ge 2 ]]; then YM="$2"; else YM=""; fi
HTML="$(./.venv/bin/python build_monthly.py "$TODAY" ${YM:+$YM} | tail -1)"
[[ -f "$HTML" ]] || { echo "!! 리포트 생성 실패"; exit 1; }
YM="$(basename "$HTML" .html | sed 's/^monthly_//')"
echo "$HTML"

# 한글 보고서. hwpx 스킬이 없으면 첨부에서 빠진다(메일은 그대로 나간다).
HWPX="out/재난안전학과_${YM}_콘텐츠활동_분석.hwpx"
if [[ -f "$HWPX_SKILL" ]]; then
  ./.venv/bin/python "$HWPX_SKILL" "out/monthly_${YM}.md" -o "$HWPX" -t report \
      --title "세명대학교 재난안전학과 ${YM} 콘텐츠 활동 분석" --creator "재난안전학과" >/dev/null \
    || echo "!! 한글 보고서 생성 실패 — 첨부에서 제외"
else
  echo "!! hwpx 스킬을 찾을 수 없음($HWPX_SKILL) — 한글 첨부 제외"
fi

XLSX="out/재난안전학과_${YM}_활동목록.xlsx"
cp "out/monthly_${YM}.xlsx" "$XLSX" 2>/dev/null

# 학교 제출용 양식(온라인 홍보활동 보고서)은 말일 잡이 미리 만들어 둔다.
# 그때 못 만들었으면(맥이 꺼져 있었다든지) 여기서 만들어 첨부는 빠지지 않게 한다.
PROMO="out/[재난안전학과] 온라인 홍보활동 보고서 ${YM}.xlsx"
if [[ -f "$PROMO" ]]; then
  echo "홍보활동 보고서: 말일에 작성된 파일을 첨부한다"
else
  echo "홍보활동 보고서: 말일 작성분이 없어 지금 만든다"
  ./.venv/bin/python build_promo_report.py "$YM" "$PROMO" >/dev/null \
    || { echo "!! 홍보활동 보고서 생성 실패 — 첨부에서 제외"; PROMO=""; }
fi

if [[ "${SMUDS_REPORT_DRYRUN:-0}" == "1" ]]; then
  echo "== 드라이런: 메일 발송 건너뜀 =="
elif [[ -f mail_config.json ]]; then
  echo "== 메일 발송 =="
  SUBJECT="$(cat "out/monthly_${YM}.subject.txt" 2>/dev/null || echo '[재난안전학과] 월간 콘텐츠 활동 리포트')"
  python3 send_mail.py "$HTML" "$SUBJECT" "$HWPX" "$XLSX" "$PROMO" || echo "!! 메일 발송 실패"
else
  echo "메일 설정(mail_config.json) 없음 — 리포트 파일만 생성했습니다."
fi
