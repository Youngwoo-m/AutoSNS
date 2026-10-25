#!/bin/zsh
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job indexcheck.daily -- "$0" "$@"
# 매일 색인 점검. 구글 검색창을 치지 않고 서치콘솔 URL 검사 API 로 확인한다.
# 사용: ./run_indexing_check.sh [--all]
set -u
cd -P "$(dirname "$0")"
ROOT="$(cd ../.. && pwd)"

echo "== 네트워크 확인 =="
if ! ./wait_network.sh; then
  echo "!! 네트워크가 없어 색인 점검을 건너뛴다"
  exit 1
fi

echo "== 색인 점검 =="
"$ROOT/channels/naver-blog-auto/.venv/bin/python" check_indexing.py "$@"
