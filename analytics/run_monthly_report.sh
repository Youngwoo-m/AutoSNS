#!/bin/zsh
# 월간 리포트 수집·생성·발송. 매월 1일에 '방금 끝난 달'을 다룬다.
# 사용: ./run_monthly_report.sh [기준일 YYYY-MM-DD] [대상월 YYYY-MM]
set -u
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
TODAY="${1:-$(date +%Y-%m-%d)}"
SINCE="2026-03-01"
HWPX_SKILL="$HOME/.claude/skills/hwpx-skill/scripts/md2hwpx.py"

echo "== 수집 시작 ($TODAY) =="
"$ROOT/youtube-shorts-auto/.venv/bin/python" collect_youtube.py || echo "!! 유튜브 수집 실패 — 직전 결과로 진행"
python3 collect_web.py "$SINCE"                                 || echo "!! 블로그·홈페이지 수집 실패 — 직전 결과로 진행"
"$ROOT/insta-cardnews/.venv/bin/python" collect_instagram.py "$SINCE" || echo "!! 인스타 수집 실패 — 직전 결과로 진행"

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

if [[ -f mail_config.json ]]; then
  echo "== 메일 발송 =="
  SUBJECT="$(cat "out/monthly_${YM}.subject.txt" 2>/dev/null || echo '[재난안전학과] 월간 콘텐츠 활동 리포트')"
  python3 send_mail.py "$HTML" "$SUBJECT" "$HWPX" "$XLSX" || echo "!! 메일 발송 실패"
else
  echo "메일 설정(mail_config.json) 없음 — 리포트 파일만 생성했습니다."
fi
