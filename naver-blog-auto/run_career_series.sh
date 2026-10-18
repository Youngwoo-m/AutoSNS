#!/bin/bash
# AX 오케스트레이터: 잠금(같은 크롬 프로필·한도를 쓰는 작업은 차례로)·비상 정지를 거쳐 다시 실행한다 — shared/axlock.py
[ -z "$AX_LOCKED" ] && exec /usr/bin/python3 /Volumes/USB256/devAPP/AutoSNS/shared/axlock.py run --job blogcareer.daily -- "$0" "$@"
# 학과 블로그 시리즈 글을 한 실행에 1편 올린다 — launchd 가 매일 08:30 호출.
#
# 한 번에 몰아 올리면 Blogger 가 글쓰기를 막는다(2026-09-16, 4편째부터 403).
# 그래서 두 겹으로 묶는다. config.json 의 blogger.career_per_run(=1) 이 이 실행의
# 몫이고, blogger.daily_limit(=2) 은 저녁 브리핑과 함께 쓰는 하루 총량이다.
# 남은 한 편은 브리핑 몫으로 비워 둔다. 이미 올라간 편은 건너뛴다.
#
# 시리즈는 이어진다 — 진로 8편이 끝나면 자격증 18편으로 넘어간다(2026-09-21).
# 그러니 진로가 끝났다고 이 잡을 내리면 안 된다. 내려도 되는 때는 career_series.py
# 의 시리즈 목록을 다 소진해 "남은 편이 없습니다" 만 찍을 때다.
#
# 인자를 받지 않는다 — 다른 발행 래퍼와 같은 이유(확인하려다 실제 발행되는 사고 방지).
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다." >&2
    echo "  미리 보기 : ./.venv/bin/python career_series.py --dry" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
# 발행 전 디스크 여유 점검(9/19 디스크 가득 참으로 전 매체 결방 뒤 추가). 모자라면 긴급
# 정리·카톡 알림만 하고 발행은 그대로 진행한다.
/usr/bin/python3 ../shared/diskguard.py 블로거진로 || true
mkdir -p logs
exec ./.venv/bin/python career_series.py >> "logs/career_series.log" 2>&1
