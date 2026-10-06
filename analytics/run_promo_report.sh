#!/bin/zsh
# 학교 제출용 '온라인 홍보활동 보고서'를 그달 말일에 작성한다.
#
# launchd 에는 '말일' 이 없어 매일 23:00 에 깨어나 내일이 1일일 때만 일한다.
# 수집부터 다시 돌린다 — 주간 수집은 월요일이라 말일엔 며칠 묵어 있다.
#
# 사용: ./run_promo_report.sh [대상월 YYYY-MM]   FORCE=1 이면 말일이 아니어도 만든다.
set -u
cd "$(dirname "$0")"
ROOT="$(cd .. && pwd)"
SINCE="2026-03-01"

if [[ $# -ge 1 ]]; then
  YM="$1"
else
  YM="$(date +%Y-%m)"
  if [[ "${FORCE:-0}" != "1" && "$(date -v+1d +%d)" != "01" ]]; then
    exit 0                      # 말일이 아니면 조용히 끝낸다(매일 깨어나므로)
  fi
fi

echo "== 네트워크 확인 =="
if ! ./wait_network.sh; then
  echo "!! 네트워크가 없어 홍보활동 보고서를 만들지 못했다($YM)"
  exit 1
fi

echo "== 수집 ($YM 말일 기준) =="
"$ROOT/youtube-shorts-auto/.venv/bin/python" collect_youtube.py || echo "!! 유튜브 수집 실패 — 직전 결과로 진행"
python3 collect_web.py "$SINCE"                                 || echo "!! 블로그·홈페이지 수집 실패 — 직전 결과로 진행"
"$ROOT/naver-blog-auto/.venv/bin/python" collect_naver_stats.py || echo "!! 네이버 블로그 조회수 수집 실패 — 조회수 없이 진행"
python3 collect_blogger.py "$SINCE"                             || echo "!! 블로거 수집 실패 — 직전 결과로 진행"
python3 collect_x.py "$SINCE"                                   || echo "!! 엑스 수집 실패 — 직전 결과로 진행"
"$ROOT/insta-cardnews/.venv/bin/python" collect_threads.py "$SINCE"   || echo "!! 스레드 수집 실패 — 직전 결과로 진행"
"$ROOT/insta-cardnews/.venv/bin/python" collect_instagram.py "$SINCE" || echo "!! 인스타 수집 실패 — 직전 결과로 진행"

echo "== 홍보활동 보고서 작성 =="
OUT="out/[재난안전학과] 온라인 홍보활동 보고서 ${YM}.xlsx"
./.venv/bin/python build_promo_report.py "$YM" "$OUT" || { echo "!! 작성 실패"; exit 1; }
echo "$OUT"
