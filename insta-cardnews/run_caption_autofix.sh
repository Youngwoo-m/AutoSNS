#!/bin/zsh
# 빈 캡션으로 올라간 릴을 찾아 발행 때 기록해 둔 캡션으로 되돌린다.
# 주간 리포트(월 08:00)보다 먼저 돌아야 리포트가 이미 고친 것을 두고 경고하지 않는다.
# 사용: ./run_caption_autofix.sh [최근 N일=14]      DRY=1 이면 목록만 만들고 편집하지 않는다.
set -u
cd "$(dirname "$0")"
DAYS="${1:-14}"

echo "== 빈 캡션 탐색 =="
./.venv/bin/python build_caption_fixlist.py "$DAYS" captions_auto.json || { echo "!! 목록 생성 실패"; exit 1; }

COUNT=$(./.venv/bin/python -c "import json;print(len(json.load(open('captions_auto.json'))))" 2>/dev/null || echo 0)
if [[ "$COUNT" == "0" ]]; then
  echo "복원할 게시물 없음."
  exit 0
fi

if [[ "${DRY:-0}" == "1" ]]; then
  echo "DRY=1 — $COUNT 건 목록만 만들고 끝낸다."
  ./.venv/bin/python ig_caption_restore.py captions_auto.json
  exit 0
fi

echo "== 캡션 복원 ($COUNT 건) =="
./.venv/bin/python ig_caption_restore.py captions_auto.json --go
