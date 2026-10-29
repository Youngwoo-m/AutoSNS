#!/bin/bash
# 매일 정비 묶음 (2026-10-30): 캐시 정리 → 다이제스트 → 빈 캡션 고치기 → 색인 점검을 차례로 돈다.
# 각 스크립트가 자체 axlock 잠금을 걸므로 개별 동작은 그대로. 하나가 실패해도 다음은 계속한다.
ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ts() { date '+%Y-%m-%d %H:%M:%S'; }
run() { echo "[$(ts)] == $1"; shift; "$@"; echo "[$(ts)] -- 종료 코드 $?"; }
run cacheprune   /bin/bash "$ROOT/common/maintenance/prune_chrome_caches.sh"
run digest       /usr/bin/python3 "$ROOT/common/shared/axlock.py" run --job digest.daily -- /usr/bin/python3 "$ROOT/common/tools/daily_digest.py"
run captionautofix /bin/zsh "$ROOT/dept/insta-cardnews/run_caption_autofix.sh"
run indexcheck   /bin/zsh "$ROOT/common/analytics/run_indexing_check.sh"
