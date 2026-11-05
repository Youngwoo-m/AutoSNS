# 3단계 착수 전 읽기 전용 조사

조사일2026-10-30. 등록부·교차 경로·원장/화면을 에이전트3개로 분담했다. 아래는 계획 근거이며 실제 인증·발행 성공 증거가 아니다. 코드·프로필·운영 설정은 변경하지 않았다.

## 현재 저장소와 권한 경계

`common/operations/database.py`의 v1 테이블은 contents/revisions/reviews/events/integration_settings/integration_events다. events는 content_id 필수의 콘텐츠 전용 이력이다. 별도 배포 이력과 명시적 스키마 이행이 필요하다. 읽기·factory에서 이행하면 안 된다.

ContentStore는 불변 버전/자산과 해시를 제공한다. 수동 reviews는 발행 승인 증거가 아니다. integration_settings의 연결 슬러그도 사용자 선호키이므로 실제 발행 연결 ID와 자동 결합하지 않는다. 변환본 구조를 바꾸지 않고 배포 계획이 특정 변환본을 참조한다.

등록부 대상 근거: 개인 YouTube `geoai_short_post.py:33`, 학과 Naver accounts.json의 studs23, 개인 Naver 전용 실행기의 safeworking은 식별 근거가 있다. Blogger 표시 주소·Tistory 주소와 플랫폼의 불변 ID는 구분한다. Instagram 예제 설정을 실제 계정으로 등록하지 않는다. Facebook/Threads/X의 불변 대상 ID는 아직 확정하지 않았다. 모든 인증 상태는 별도 미확인이다.

## 현재 운영 설정과 코드의 차이

실제 운영 원본 `/Volumes/USB256/devAPP/AutoSNS`의 관련 config를 허용 필드만 읽었다. TikTok은 tiktok_web.daily=true, tiktok.enabled=false다. automations.json의 daily=false 메모와 다르다. 워크트리에는 해당 config가 없다. 현재 설치 TikTok 큐 plist도 없다. enqueue 허용·직접 업로드·스케줄 파일 존재·load/disabled를 별도 근거로 보존한다. launchctl load/disabled는 이번 조사에서 확인하지 않았다.

핵심 코드7개와 automations.json은 실제 운영 원본/워크트리 바이트가 같았다. 현재 설치 plist에서 GeoAI07:40/18:00, 채용 일21:00, 진로 화20:00, 재난 교차 화·금19:30을 확인했다. 재난21:00 재시도 plist는 없었다. 주석·백업 시각으로 덮어쓰지 않는다.

## 보존할 주요 교차 경로

| 경로 | 근거와 조건 |
|---|---|
| 개인 숏츠→학과 TikTok | geoai_short_post.py:212. 업로드 응답·채널 확인 뒤 legacy queue.add, source=geoai_short. 예약 시각 전달, add가30분 지연 소유. AI 생성/음성 true. 이 경로 자체에는 public/쿠팡 제외 조건이 없음. 큐 실패가 YouTube 성공을 취소하지 않음. |
| 범용 YouTube→TikTok | youtube_upload.py:348. ID 있음+public+설명에 쿠팡 없음. 개인/학과 토큰 경로로 source=geoai/youtube_upload 구분. 전용 숏츠 조건과 합치지 않음. |
| GeoAI→학과 Threads | geoai_daily.py:393. Blogger published 또는 dry이고 --no-video 또는 --threads일 때. 저녁만이라는 주석보다 명시 override가 넓음. 첫 요약/원문 URL/태그5/전체500자와 legacy CLI 주인 보존. |
| 학과 채용→개인 Tistory | run_jobs.sh:22–32 및 tistory_jobs.py:94–135. Naver 채용 성공, Instagram 실패와 독립, 초안6시간 이내, jobs:basename 중복키, Naver 게시 공고ID≥1, 유효공고≥3. 사용자 중지 메모 보존. |
| 개인 Tistory→개인 Naver | personal/claude-jobs/공통규칙.md:83–90 및 naver_crosspost_personal.py. 공개 확인 뒤 지정6분야만, 학과·숏츠 전용 회차 제외. safeworking 강제·카테고리·표/그림/첨부·원문 링크·no_cta·제목RSS 중복. dry도 편집기 입력하므로 미리보기에서 호출 금지. |

TikTok queue.py 기준: 공개/예약+1800초, 최소간격10800초,07:00≤시각<23:00.14일 초과/tries≥5/skipped/posted 제외, hold_until과 영상 존재 확인. 새 영상→priority→not_before 정렬이며 backfill은3시간 안에 새 영상 예정이면 쉰다. 인프라 예외는 tries 미증가, 동일 화면 오류2회는 다음00:00까지 hold다. 기존 add가 지연을 소유하므로 새 미리보기가 지연을 이중 적용하지 않는다.

## 추가 경로

- 학과 Naver→학과 Blogger: run_weekly.py:90.
- 개인 Blogger→개인 Tistory 요약/원문 링크: tistory_crosspost.py:613, enabled=false만 차단·per_run 기본2. 사용자 중지 메모 유지.
- GeoAI 아침/저녁→개인 YouTube 커뮤니티.
- 학과 뉴스 YouTube→Naver 동영상뉴스·아나운서 조건 Instagram/Threads/X·별도 direct TikTok.
- 학과 진로/퀴즈 YouTube→TikTok 큐/Instagram/Threads/X, no-ig/no-threads 보존.
- 학과 재난 숏츠→TikTok 큐 및 Instagram/Blogger/Naver/Threads. published/shared_unconfirmed 대상은 재시도 생략. legacy crosspost 실행기가 YouTube 공개 상태도 바꿀 수 있어 import/호출 금지.

3단계에서는 이 경로의 주인을 legacy로 유지하며 관측·순수 계산만 한다. 실제 전환은 보호장치·중복 방지·현재 대상/상태 재확인 뒤 별도 수행한다.
