#!/bin/bash
# 고용24 재난안전 분야 채용정보를 네이버 블로그 '채용정보'에 올린다 — launchd 가 일요일 20:00 호출.
#
# 매일 19:00 브리핑 발행과 같은 크롬 프로필(chrome-profile)을 쓴다. 한 프로필을 두 크롬이
# 동시에 열면 뒤에 연 쪽이 죽으므로, 앞 작업이 아직 돌고 있으면 끝날 때까지(최대 40분) 기다린다.
#
# 인자를 받지 않는다 — 다른 발행 래퍼와 같은 이유(확인하려다 실제 발행되는 사고 방지).
if [ "$#" -ne 0 ]; then
    echo "$(basename "$0"): 인자를 받지 않습니다 — 실제 발행 스크립트라 거부합니다." >&2
    echo "  미리 보기 : ./.venv/bin/python jobs_work24.py --list   (발행 직전까지: --dry)" >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
mkdir -p logs
for i in $(seq 1 40); do
    pgrep -f "naver-blog-auto/chrome-profile" >/dev/null || break
    [ "$i" -eq 1 ] && echo "[$(date '+%F %T')] 네이버 크롬 프로필 사용 중 — 기다림" >> logs/jobs.log
    sleep 60
done
./.venv/bin/python jobs_work24.py --go >> "logs/jobs.log" 2>&1 || exit $?
# 같은 초안으로 인스타그램 카드뉴스도 올린다(소방 제외, 블로그 링크 안내). 방금 만든 초안이
# 없으면(이번 주 블로그를 건너뛴 경우) jobs_insta.py 가 알아서 건너뛴다.
cd ../insta-cardnews || exit 1
exec ./.venv/bin/python jobs_insta.py --latest --go >> "../naver-blog-auto/logs/jobs.log" 2>&1
