# 5단계 공급자 공식 문서 확인

2026-10-30. 다음 단계 설계에 필요한 공개 공식 문서만 확인했다. 실제 서비스 API·계정·토큰·로그인 프로필에는 접근하지 않았다. 미확인 권한과 API 제약은 사용 가능으로 추정하지 않는다. 이 문서는 실연결 완료 증거가 아니다.

# 후속 5단계 YouTube 공식문서 확인

확인일: 2026-10-30. Google Developers 정적 공식문서 6개만 확인했다. 계정·토큰·업로드 코드 조회와 사용자 API 호출은 하지 않았다. 이 문서는 수집기 구현 또는 실행 승인이 아니다.

## 조회와 ID 검증

| 목적 | 공식 메서드·요청 후보 | 검증/반환 필드 |
|---|---|---|
| 발행 영상 조회 | `GET https://www.googleapis.com/youtube/v3/videos`, `part=snippet,status,statistics`, `id=<저장된 video ID>` | `items[].id`, `snippet.channelId`, `snippet.publishedAt`, `status.privacyStatus`, `status.uploadStatus`, `statistics.viewCount/likeCount/commentCount` |
| 핸들→채널 확인 | `GET https://www.googleapis.com/youtube/v3/channels`, `part=id,snippet`, `forHandle=<handle>` | 반환 `items[].id`와 사전 등록 채널 ID 비교. `@` 접두사 허용 |
| 인증 주체 채널 확인 | 같은 `channels.list`, `part=id,snippet`, `mine=true` | 인증 사용자가 소유한 채널 반환. `mine`과 `forHandle`은 한 요청에 함께 넣지 않음 |

두 list 메서드는 각각 호출당 1 quota unit이다. `videos.list`는 영상 ID 목록을 받으며, 채널 목록 필터도 한 번에 하나만 지정한다.[^1][^2]

설계 제안(공식의 필수 절차라는 뜻은 아님): 발행 로그의 영상 ID로 조회한 뒤 `items[].id` 일치와 `snippet.channelId == 등록 channel ID`를 함께 확인한다. 제목·핸들 문자열만으로 계정 일치를 판정하지 않는다. 결과 없음/권한 오류는 0 조회수와 구분한다. `snippet.channelId`는 영상이 다른 채널로 재지정되면 바뀔 수 있으므로 불일치를 자동 덮어쓰지 않는다.[^3]

## 최소 읽기 권한과 기존 업로드 토큰

- 공개 메타데이터 읽기와 소유자 전용 읽기를 분리한다. `mine=true`는 적절히 승인된 요청이 필수다. 이번에 확인한 list 본문은 일반 읽기의 OAuth 허용 scope 목록을 열거하지 않는다. 따라서 `youtube.readonly`를 소유자 읽기의 최소권한 후보로 두되, 각 메서드의 현재 허용 scope를 추가 정적 문서 확인 없이 확정하지 않는다.[^1][^2]
- OAuth의 `scope`는 접근 가능한 자원을 결정한다. 기존 업로드용 토큰이 있다는 사실만으로 읽기·Analytics 권한까지 부여됐다고 판단할 수 없다. `youtube.upload`만으로 이번 읽기를 수행할 수 있다고 단정하지 않는다. 실제로 부여된 scope, 대상 채널, 유효성은 이번 작업에서 모두 미확인이다. 재동의 없이 재사용할 수 있다는 결론도 내리지 않는다.[^6]
- `reports.query`는 모든 요청에 승인이 필요하다. 공식 상단은 `https://www.googleapis.com/auth/youtube.readonly`가 이제 필요하다고 명시하고, 권한 표는 활동 보고서용 `https://www.googleapis.com/auth/yt-analytics.readonly`를 별도로 명시한다. 둘 중 하나만 충분하다고 단정하지 않는다. 후속 설계는 두 읽기 scope를 요구 후보로 기록하고, 구현 전 현재 공식 허용 조합을 확인한다. 수익 지표는 별도 `yt-analytics-monetary.readonly` 범위이며 이번 기본 지표 범위에 넣지 않는다.[^4]

## 시점·누적값과 기간 지표

`videos.list`에는 기간 필터가 없다. `statistics`는 조회 당시 영상 카운터의 스냅샷으로 저장하고 `collected_at`을 붙이는 설계가 적절하다. `viewCount`는 시청 횟수, `likeCount`는 좋아요를 표시한 사용자 수, `commentCount`는 영상 댓글 수다. 기간 내 발생 횟수와 동일시하지 않는다. 두 스냅샷 차이도 Analytics의 공식 기간 지표로 이름 붙이지 않는다.[^1][^3]

주의: 확인일의 공식 영상 문서는 **2026-08-24부터 모든 형식(일반·Live·Shorts)의 `viewCount`를 재생 시작 시 집계**한다고 설명한다. 과거 Shorts의 2025년 설명만 재사용하지 않는다. `dislikeCount`는 영상 소유자로 인증한 응답에만 포함되고 `favoriteCount`는 폐기되어 항상 0이다. `publishedAt`은 업로드 시각과 다를 수 있어 수집 시각 또는 정확한 업로드 시각의 대용으로 쓰지 않는다.[^3]

Analytics는 `GET https://youtubeanalytics.googleapis.com/v2/reports`에 `ids=channel==MINE` 또는 현재 인증 사용자의 채널 ID, `startDate`, `endDate`(`YYYY-MM-DD`), `metrics`를 지정한다. 기간의 `views`, `likes`, `comments` 등을 조회하는 체계다. 요청 `endDate`까지 모든 지표가 준비되지 않았다면 응답은 모든 요청 지표가 가용한 마지막 날짜까지만 나온다. 오늘 요청했다고 오늘까지 확정됐다는 뜻이 아니다.[^4]

Analytics `views`는 보고서 종류에 따라 의미가 달라진다. `engagedViews`는 첫 프레임 이후까지 시청하거나 클릭/탭하여 재생한 횟수이며, `estimatedMinutesWatched`는 시청 분, `averageViewDuration`은 평균 재생 초, `likes/comments`는 해당 행동 발생 횟수다. 따라서 Data API 현재 카운터와 Analytics 기간 행동 지표는 이름과 데이터 출처를 분리한다.[^5]

## 미확인과 설계 경계

프로젝트 실제 일일 quota/증액, 사용자 토큰 scope·갱신 가능 여부·채널 소유권, 비공개 영상별 반환 가능 필드, 정확한 지표 지연 SLA, Analytics 날짜 경계의 시간대, 보고서별 metric 조합 지원은 확인하지 않았다. list 1 unit과 별개로 Analytics quota 비용은 이 6페이지에서 확정하지 않았다. 실제 토큰/API 호출로 보완하지 않는다. 구현·실행 전 별도 승인과 제한된 검증이 필요하다.

[^1]: [Videos: list](https://developers.google.com/youtube/data/reference/rest/v3/videos/list)
[^2]: [Channels: list](https://developers.google.com/youtube/data/reference/rest/v3/channels/list)
[^3]: [Videos resource](https://developers.google.com/youtube/data/reference/rest/v3/videos)
[^4]: [Reports: Query](https://developers.google.com/youtube/analytics/reference/reports/query)
[^5]: [YouTube Analytics metrics](https://developers.google.com/youtube/analytics/metrics)
[^6]: [Implementing OAuth 2.0 Authorization](https://developers.google.com/youtube/data/guides/authentication)


---

# 후속 5단계 SNS 성과 조회 — 공식 문서 확인

확인일: 2026-10-30(KST). 정적 공식 문서 웹 검색·열기만 수행했다. 실제 계정·토큰·프로필·서비스 API에는 접근하지 않았다. 아래의 문서상 기능은 실제 대상 계정의 이용 가능성을 뜻하지 않는다. 이번 확인은 수집기 구현·연결·실행 승인이 아니다.

## Instagram

- **확인된 기능:** Meta 제공 공식 Postman 문서는 Instagram 전문가 계정의 미디어 조회 및 인사이트 수집 기능을 설명한다. Facebook Login 경로는 Business/Creator 계정과 연결된 Facebook Page, Facebook App, 사용자 액세스 토큰을 요구하며 일반 소비자 계정은 접근 대상이 아니다. 문서의 전체 컬렉션 권한 목록을 인사이트 최소 권한으로 해석하면 안 된다.
- **미확인:** 현재 인사이트 endpoint별 지표·최소 scope, Instagram Login 경로의 인사이트 권한, App Review/Advanced Access 조건, 유료 접근 제약. 개발자 인사이트 본문은 접근 제한으로 확인하지 못했다. 따라서 최신 권한 조합과 실제 조회 가능 여부는 설계 확정 전에 재확인해야 한다. 유료 조건 미확인을 무료 보장으로 해석하지 않는다.
- **공식 근거:** [Meta Instagram API 컬렉션](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api?entity=request-23987686-b9dac9f7-5415-4659-bcfd-795298a07e91).
- **재확인할 공식 본문(열기 실패):** [Instagram Insights](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/insights/).

## Threads

- **확인된 기능:** Meta 공식 컬렉션의 Read Threads Insights에 `GET /{thread_id}/insights?metric=...` 게시물 인사이트 요청과 Get Account Insights 항목이 존재한다. Meta App에 Threads use case를 설정하고 사용자가 데이터 접근을 승인하여 OAuth 토큰을 받아야 한다. 공식 컬렉션 인증 안내에 `threads_basic`, `threads_manage_insights`가 포함된다. 발행·답글 권한까지 나열된 전체 컬렉션이므로 전부를 읽기 전용 필수 권한으로 채택하지 않는다.
- **미확인:** 현재 지표별 제공 범위, 계정 인사이트 경로 상세, 전문가 계정 전환 필요 여부, 최소 권한의 완전한 집합, 심사·운영 접근 조건 및 유료 접근 제약. 컬렉션 자체가 최신 기능을 전부 반영하지 않을 수 있다고 명시하며 개발자 본문은 429로 열리지 않았다.
- **공식 근거:** [Meta Threads API 인증·설정 안내](https://www.postman.com/meta/threads/documentation/dht3nzz/threads-api), [Meta Get Post Insights](https://www.postman.com/meta/threads/request/34203612-385abc7d-b3cc-4e5d-9937-ebbe7174e041).

## Facebook

- **현재 판정:** 이번 좁은 확인에서는 최신 공식 Page Insights 본문을 확보하지 못했다. [Page Insights 공식 참조](https://developers.facebook.com/docs/graph-api/reference/insights/)는 429, [Pages API Insights](https://developers.facebook.com/docs/pages-api/insights/)는 열기 실패였다. 비공식 미러·외부 구현 예시는 근거에서 제외했다.
- **미확인:** 현재 읽기 endpoint와 지표, Page/개인 프로필 지원 범위, Page task·토큰 유형, `read_insights`/`pages_read_engagement`의 현행 필수 조건, 심사·유료 제약. 이 상태를 API 미지원으로 단정하지 않는다. 공식 문서 재확인 전에는 수집 가능 항목을 확정하지 않는다.

## X

- **확인된 기능:** X API v2는 게시물과 영상 성과 지표를 제공한다. `public_metrics`는 Bearer Token으로 노출·좋아요·재게시·답글 등을 읽는다. 비공개 클릭 지표 및 organic/promoted 지표에는 사용자 컨텍스트 OAuth가 필요하고 소유한 게시물 등 문서상 대상 제한을 따른다. 비공개·organic·promoted 지표는 최근 30일 내 생성된 게시물만 제공된다. Metrics 문서에는 Business/Creator 전환 요건이 제시되지 않는다.
- **유료 제약:** 현행 공식 가격 문서는 구독제 대신 선불 크레딧 기반 사용량 과금으로 설명한다. 일반 Post Read는 반환 리소스당 $0.005이다. 특정 자기 데이터 endpoint는 인증 사용자가 개발자 앱 소유자이며 ID가 일치할 때 Owned Reads $0.001/리소스가 적용된다. 모든 성과 조회에 이 할인 가격을 일반화하지 않는다. 요금은 변경 가능하다.
- **미확인:** 실제 앱·계정의 접근 자격과 잔액, 선택 endpoint의 OAuth scope 및 최종 요금은 확인하지 않았다.
- **공식 근거:** [X Metrics](https://docs.x.com/x-api/fundamentals/metrics), [X API pricing](https://docs.x.com/x-api/getting-started/pricing).

## Tistory

- **확인된 종료 범위:** 2023-12-22 공식 공지는 티스토리 Open API의 종료와 유지보수 중단을 알린다. 공지상 일정은 2023년 12월 말부터 2월 말까지 순차 종료이며, 파일 첨부 → 글 관련 → 댓글 관련 → 그 외 기능 순이다. 글 작성·수정, 이미지·파일 첨부, 댓글 작성·수정 불가를 구체적으로 안내한다. 일부 쓰기 endpoint만 종료한다는 공지가 아니라 Open API 전체에 대한 종료 공지다.
- **미확인:** 현재 대체 성과 조회용 공식 읽기 API, 방문·조회 통계 endpoint, 계정·권한·유료 접근 조건은 확인하지 못했다. 이 공지만으로 RSS·관리자 통계 화면 등 다른 기능까지 종료됐다고 해석하지 않는다. 공식 성과 API 문서를 찾지 못했다는 사실을 모든 읽기 방식 미지원으로 단정하지 않는다.
- **공식 근거:** [티스토리 Open API 종료 공지](https://notice.tistory.com/2664).

## 후속 설계에서 유지할 경계

Metricool이 Codex에 설치·연결되어 있다는 사실은 AutoSNS 웹 서버나 상시 수집 runtime이 Metricool API를 호출할 권한·토큰·요금제를 확보했다는 뜻이 아니다. 이 확인에서는 Metricool이나 각 SNS의 연결 상태를 조사하지 않았다. 문서 확인, 실제 계정 접근 가능성, 상시 runtime 권한을 별도로 판단해야 한다.
