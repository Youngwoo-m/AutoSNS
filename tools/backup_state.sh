#!/bin/bash
# 자동화 상태 파일 백업 — 지워지면 복구가 안 되는 '누적 기록'만 대상으로 한다.
#   buddy_request_state.json  : 서로이웃 선신청 이력(지워지면 같은 사람에게 재신청)
#   follow_back_state.json    : 인스타 맞팔 처리 이력
#   trigger_state.json        : 속보 트리거 중복 발행 방지 기록
# 날짜별 폴더에 복사하고 90일 지난 백업은 지운다. 백업 폴더는 git 에 올리지 않는다.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/backups/state/$(date +%Y-%m-%d)"
mkdir -p "$DEST"
for f in naver-blog-auto/buddy_request_state.json \
         insta-cardnews/follow_back_state.json \
         youtube-shorts-auto/trigger_state.json; do
    [ -f "$ROOT/$f" ] || continue
    cp -p "$ROOT/$f" "$DEST/$(echo "$f" | tr '/' '_')" && echo "백업: $f"
done
find "$ROOT/backups/state" -maxdepth 1 -type d -mtime +90 -not -path "$ROOT/backups/state" \
     -exec rm -rf {} + 2>/dev/null
echo "백업 위치: $DEST (보관 90일)"
