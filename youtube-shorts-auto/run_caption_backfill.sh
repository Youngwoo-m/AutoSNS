#!/bin/bash
# 기존 영상 자막 소급 적용 — launchd 가 매일 17:10 호출(할당량 리셋 직후).
#
# 유튜브 API 하루 한도는 10,000유닛인데 자막 업로드는 1편당 400유닛, 자막 확인은
# 50유닛이라 한 번에 많이 돌릴 수 없다(33편을 한 번에 돌리다 할당량이 터졌다).
# 그래서 하루 10편으로 제한한다. 멱등이라 이미 자막이 있는 영상은 건너뛰고,
# 남은 대상이 없으면 아무 일도 하지 않는다(다 끝나면 이 잡을 내려도 된다).
#
# 인자를 받지 않는다 — 다른 발행 래퍼와 같은 이유(확인하려다 실행되는 사고 방지).
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다." >&2
    echo "  미리 보기 : ./.venv/bin/python backfill_captions.py          (dry-run)" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
mkdir -p logs
exec ./.venv/bin/python backfill_captions.py --go --limit 10 >> "logs/caption_backfill.log" 2>&1
