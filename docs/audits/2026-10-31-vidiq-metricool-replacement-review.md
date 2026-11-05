# vidIQ·Metricool 교체 검토

2026-10-31. 사용자 요청: “vidIQ, Metricool 이용으로 변경 할 수 있는것 검토 후 교체”. 추가 지시: **“유료인 경우 기능을 분석해서 여기에서 별도로 구축합시다.”** 현재 6A 구현·리뷰를 이어 가면서 공급자 교체 범위를 좁힌 검토다. 기준 HEAD는 `d98f29c`이며 진행 중인 작업 트리도 읽었다. 이 문서만 작성했으며 실행 코드·운영 설정·인증·스케줄은 변경하지 않았다. 실제 발행·예약 생성·메타데이터 수정·생성 작업·유료 리서치는 실행하지 않았다.

## 결론

**무료 MCP와 0 credit 기능만 선택적으로 활용하고, 유료 예약 API·리서치·제작 기능은 AutoSNS에서 자체 구축한다.** Metricool의 기능 분류는 SNS 예약·성과, vidIQ는 YouTube 리서치·패키징에 적합하지만, 무료 접속 가능과 개별 기능 무료는 다르다. 아래 기술적 대체 후보는 결제·활성화 권고가 아니다.

- 먼저 자체 구축할 범위는 기존 스케줄·플랫폼 전송·성과 저장 경계에 맞춘 **로컬 예약·collector**, 승인된 구독 텍스트와 규칙 기반 **기획·패키징 보조**, 기존 **Voicebox·Remotion 미디어 leaf**다. 공통 원장·콘텐츠 revision·독립 검토·승인·잠금·quota·복구는 유지한다.
- 신규 결제·Advanced 업그레이드·유료 API·credit 소비·신규 가입·권한 추가·인증 시도는 실행하지 않는다. 포함된 vidIQ150 credit도 자동 소모하지 않는다. 무료 MCP·0 credit 읽기 도구는 현재 승인된 연결에서만 활용하며 쓰기0을 기본으로 한다.
- 현재 Codex의 연결 조회 성공은 상시 웹 서버 연결 성공이 아니다. Metricool의 유료 HTTP API는 현재 우선 구현에서 제외한다. 별도 무료 MCP runtime 가능성도 인증·재시작·계정 격리의 운영 증거가 없으므로 미확인이다. Codex의 쿠키·토큰·커넥터 비밀을 추출해 재사용하지 않는다.
- **즉시 활성화 가능한 상시 교체는 미확인**이다. 현재 등록부의 YouTube 대상 ID가 비어 있고 vidIQ에 연결된 YouTube 채널은 없다. default disabled를 유지하면서 명시적 provider/대상 바인딩을 구현하는 것이 최소 변경이다.
- 네이버·Blogger·Tistory 발행, 개인 구독 전용 producer, 독립 계산·출처 검토, 기존 23개 교차 게시 규칙은 유지한다. 기존 자동 작업을 제거하거나 중지 상태를 해제하지 않는다.

## 확인한 근거와 한계

### 현재 코드

| 경계 | 정적 확인 결과 | 교체 시 의미 |
|---|---|---|
| `common/operations/integration_store.py` | Metricool 6개 SNS, vidIQ YouTube/Instagram/TikTok을 설정값으로 허용한다. 저장 응답은 항상 `unknown`/`not_connected`다. | 후보 allowlist다. 실제 capability·인증·실행 성공을 뜻하지 않는다. preference를 켜서 발행기를 자동 등록하면 안 된다. |
| `ax-console/app/read_model.py:_integration_catalog` | Metricool 후보에는 Instagram/Threads/X/Facebook만, vidIQ에는 YouTube/TikTok/Instagram을 표시한다. | Metricool YouTube/TikTok 누락과 vidIQ 기능별 차이를 서버 소유 capability 투영으로 정리할 필요가 있다. 플랫폼 합집합을 “발행 가능”으로 표시하면 안 된다. |
| `common/publishers/__init__.py`, `blog_adapter.py`, `youtube.py` | 6A의 Blog 5개·YouTube 2개 연결용 adapter와 bridge가 존재한다. 인자 없는 factory는 빈 값이며 연결 enabled/target 조건을 검사한다. | 10/30 조사 당시 “어댑터 없음”은 현재 코드 상태에 적용되지 않는다. 기존 계약 내부에 provider 전송을 추가하고 연결별 하나만 선택한다. |
| `common/operations/bootstrap_config.py:build_execution_service` | 기본 `ExecutionPolicy`에서는 adapter를 만들지 않는다. 활성 정책에만 factory를 호출한다. producer도 서버 주입값이며 기본 빈 map이다. | 새 provider 때문에 startup/GET/기본 worker에서 외부 호출을 시작하지 않는다. |
| `common/operations/metrics.py`, `metrics_models.py`, `metrics_store.py` | 별도 성과 저장소와 `MetricResult`가 존재한다. 수집기는 명시 주입이며 없으면 unsupported. 원장의 공개 verified·remote ID·대상·소유자 대조가 필수다. 웹 snapshot은 collection disabled다. | “성과 기능 없음”이 아니라 “실제 수집기 미등록”이다. Metricool/vidIQ 응답을 검증된 게시 ID에 정규화하는 collector만 추가한다. |
| `common/operations/production.py`, `production_providers.py`, `provider_policy.py`, `production_models.py` | 텍스트 생산·미디어 leaf·출력 검증·revision ingest를 분리한다. 기본 공급자 정책 catalog는 비어 있다. 개인 정책은 subscription_only이며 허용 provider는 `claude-subscription`, 매체는 text로 제한한다. | vidIQ 생성·리서치를 개인 기존 producer의 fallback으로 붙일 수 없다. 비용이 드는 새 작업은 별도 정책이 필요하다. 이번 요청으로 개인 구독 제한을 삭제하지 않는다. |
| `common/operations/cutover.py`, `ax-console/config/crossposts.json` | 진입점·교차 경로 baseline과 실운영 증거를 구분해 전환을 차단한다. | Metricool 예약 성공만으로 23경로 전체 전환·공개 검증·운영 수락을 합성하지 않는다. |

이전 조사 [플러그인 runtime 준비도](2026-10-30-plugin-runtime-readiness.md)의 “설정≠인증≠실행” 결론은 유효하다. adapter·성과 저장소의 존재 여부는 위 현재 코드로 갱신한다. 이 문서는 진행 중인 6A 전체 시험 통과를 주장하지 않는다.

### 이번 세션의 무료 연결 관측

아래는 부모 작업이 실제 수행한 무료 도구 조회 결과를 전달받아 재사용한 것이다. 이 문서 담당은 계정 조회를 반복하지 않았다. 표시 이름·반환 항목은 연결 관측이며 현재 토큰의 쓰기 권한·최종 대상 소유권·상시 runtime 인증을 검증한 결과가 아니다.

| 공급자 연결 | 관측된 항목 | 아직 확인하지 못한 것 |
|---|---|---|
| Metricool `SMUDS`, brand `7747536` | Instagram `smu_ds_official`, TikTok `smuds2025`, YouTube `UCyB8hWjVghfgzZgj8fwmZrQ` | AutoSNS dept와 불변 ID 일치, 현재 자동 발행 권한, 요금제/API 권한 |
| Metricool `Primary`, brand `7747381` | TikTok `kor.geo.panda`, YouTube `UCbHDlxMFIackeJRwW2iTYew` | AutoSNS personal과 불변 ID 일치, 현재 자동 발행 권한, 요금제/API 권한 |
| Metricool 두 연결 | 이 조회에서 X·Threads·Facebook 항목은 반환되지 않았다. | 미연결/권한 없음/조회 차이 중 어떤 이유인지는 미확인. 서비스 전체 미지원으로 판단하지 않는다. |
| vidIQ 두 연결 | `user_channels=[]`; 잔액 조회 각각 total 150, renewable 150/150, add-on 0, 다음 갱신 2026-11-30; 해당 무료 호출 `_credits.used=0` | 연결된 YouTube 채널 없음. 소유자 private analytics·수정 권한은 확인되지 않았다. Instagram 소유 계정 연결도 미조회다. |

`ax-console/config/operations.json`의 `dept.youtube`와 `personal.youtube`는 모두 `target_id=null`, `expected_login_subject=null`, `target_evidence=[]`다. 따라서 위 두 YouTube ID와 등록부 간 **불변 ID 대조는 현재 불가능**하다. 기존 `common/analytics/collect_youtube.py`의 `CHANNEL_ID`는 SMUDS의 YouTube ID와 일치하지만 이는 정적 보조 근거이며 현재 로그인·등록부 대상 확정을 뜻하지 않는다. SMUDS/Primary라는 이름만으로 account_id를 배정하지 않는다. 나머지 SNS도 표시 handle 외에 서버가 확인한 플랫폼 고유 ID와 정확한 connection 바인딩이 필요하다. 개인 TikTok 등록이 없는데 Primary의 TikTok을 새 개인 대상에 자동 편입해서도 안 된다.

원본 응답·Metricool hash·OAuth 토큰·쿠키·API 키·서명 URL은 이 문서와 preference 저장소에 보관하지 않았다.

## 공식 기능과 인증 범위

공식 문서 확인일은 2026-10-31이다. 서비스 문서, 이 세션에서 노출된 도구 설명, 실제 무료 관측을 구분했다. 노출된 도구가 있다고 호출 성공을 주장하지 않는다.

| 항목 | 공식 문서·도구에서 확인 | 상시 runtime 판단 |
|---|---|---|
| Metricool MCP | 모든 요금제(Free 포함)에서 접근 가능. 브랜드·성과·예약 생성/조회/수정·리뷰·게시 추천 시각 도구가 있다. [공식 비교](https://help.metricool.com/mcp-vs-api-access-what-is-the-difference-5y3ib) | 대화 연결과 별도의 runtime OAuth·클라이언트 운영 증거가 필요하다. MCP의 존재를 HTTP API 이용권으로 바꾸지 않는다. |
| Metricool HTTP API | Advanced·Custom에서 제공. 토큰과 userId/blogId를 사용하며 예약 CRUD endpoint가 있다. Planner 모든 기능을 API로 쓸 수 있는 것은 아니다. 미디어는 공식 요구조건대로 전달해야 한다. [API 통합 가이드](https://help.metricool.com/basic-guide-for-api-integration-r97af) | 유료 조건이므로 현재 채택 제외. 실제 구독·토큰·권한은 미확인. 상시 예약·성과는 로컬 경계 재사용으로 자체 구축한다. |
| Metricool 요금 한계 | MCP가 Free 한도를 올리지 않는다. Free 예약 월20개·성과 이력30일. [공식 한도](https://help.metricool.com/mcp-limits-and-plan-requirements-h72jg) | 현재 요금제·두 연결의 청구/공유 범위·잔여 예약량 미확인. 두 브랜드가 다른 비용 주체인지도 추정하지 않는다. |
| Metricool 대상 SNS | Instagram Business/Creator, Facebook Page, Threads, X, TikTok, YouTube 등을 연결할 수 있다. X는 유료 요금제 add-on 대상이다. 브랜드당 같은 SNS 계정은 하나다. [연결 안내](https://help.metricool.com/how-to-connect-social-media-and-ad-platforms-to-metricool-qrkvn) | Facebook 개인 프로필과 Page를 구별한다. handle·브랜드 이름으로 destination을 정하지 않는다. |
| Metricool 예약·성과 | 지원 형식은 SNS마다 다르다. YouTube는 Shorts/긴 영상, Instagram은 게시물/Reels 등, TikTok은 영상/사진이 문서화돼 있다. 성과는 여섯 대상 SNS의 organic을 지원하지만 지표·플랜 예외가 있다. [발행 형식](https://help.metricool.com/scheduling-and-posting-options-by-social-network-cwmb3), [성과 범위](https://help.metricool.com/your-metrics-in-metricool-full-guide-pcwam) | 형식·게시 ID·기간·timezone·지표 정의별 매핑 시험이 필요하다. 브랜드 합계는 검증된 delivery 한 건의 실적으로 저장하지 않는다. |
| vidIQ MCP | 모든 요금제에서 접근 가능. 공식 원격 MCP와 별도 API key 경로를 문서화한다. 일부 YouTube 변경·Instagram Reel 발행은 API key로 불가하며 로그인 인증이 필요하다. private YouTube 분석은 연결된 채널만 가능하다. [vidIQ 공식 MCP 안내](https://support.vidiq.com/en/articles/15082430-vidiq-mcp) | 키를 쓰는 읽기 전용 runtime과 OAuth 쓰기 기능을 동등하게 취급하지 않는다. 범용 REST API 제공/상시 서비스 OAuth 갱신·운영 보장은 이번 조사에서 미확인이다. |

Metricool API를 선택하면 기존 플랫폼별 credential 대신 Metricool credential이 필요한 경로가 생긴다. 그렇더라도 AutoSNS owner/destination 검사는 제거하지 않는다. 별도 MCP runtime을 택하더라도 계정별 동의·비밀 참조·만료/철회 처리·재시작·호출 복구를 명시해야 한다. [Metricool 연결 안내](https://help.metricool.com/how-to-connect-metricools-mcp-eqp9h)

Metricool에는 Facebook Group 직접 발행, YouTube Community/Shorts 썸네일 등 제약이 있다. MCP 예약 목록은 현재 예정된 게시물만 조회하므로 “목록에 없음”은 이미 공개/실패/삭제/미제출 중 하나를 확정하지 못한다. [공식 플랫폼 제한](https://help.metricool.com/api-limitations-per-social-network-n7zlr), 세션 도구 설명 `getScheduledPosts`.

vidIQ의 현행 세션 도구에는 TikTok/Instagram outlier 리서치와 Instagram owner insights/Reel 발행이 보인다. 반면 공식 FAQ는 TikTok 미지원이라고 설명해 차이가 있다. 따라서 **TikTok 리서치는 노출된 도구의 제한된 후보**, TikTok 발행·소유자 성과 지원은 미확인으로 둔다. 세션의 `vidiq_video_upload`는 vidIQ 내부 편집/분석용 가져오기다. **신규 YouTube 채널 업로드 도구는 현행 surface에서 확인되지 않았다.** `vidiq_update_video`의 예약 시각 수정은 기존 영상 변경이며 신규 업로드 대체가 아니다. [공식 FAQ](https://support.vidiq.com/en/articles/15082430-vidiq-mcp)

## 기능별 교체 판정

“조건부”는 기술적 기능 후보가 있지만 코드 구현·대상 검증·인증·정책 수락이 남았다는 뜻이다. **현재 채택 판단은 다음 절의 0 credit·자체 구축 표가 우선한다.** 아래 모든 새 상시 경로는 미등록/비활성 상태를 기본으로 한다.

| 기능 / 현재 구현 | 추천 provider | 대체 가능 범위 | 실인증 관측 | 웹 runtime 준비 | 남은 필수 | 비용·권한 범위 |
|---|---|---|---|---|---|---|
| Instagram 게시물·Reel 배포 / legacy·6B 대상 | 로컬 adapter 우선; Metricool 무료 MCP 후보 | 유료 runtime 교체 제외 | SMUDS Instagram 항목 반환 | 어댑터·credential 미등록 | 정확한 계정 ID, 형식·미디어·공개 검증, 예약 ID→게시 ID 연결 | Professional 계정·실제 publish 권한·현 요금제 미확인 |
| TikTok 배포 / 기존 큐·교차 규칙 | 로컬 큐 유지; Metricool 무료 MCP 후보 | 큐 정책 유지·자체 경계 구현 | 두 브랜드 TikTok 항목 반환 | 어댑터 미등록 | 대상 계정 확정, 중지 상태·hold·재시도·슬롯 동치, AI 고지·옵션 확인 | 실제 publish scope·잔여 한도 미확인 |
| YouTube 새 영상·Shorts / `YoutubeAdapter` 2개 | 기존 adapter 유지 | Metricool은 기술상 후보, 현재 유료 runtime 제외 | 두 브랜드 YouTube ID 반환, AutoSNS 대조 불가 | Metricool 구현 없음 | target 고정, audience/공개 범위/예약·본문·매체 동치, 처리 실패·lookup/verify | API 요금제·scope 미확인; vidIQ 신규 업로드 대체 불가 |
| Threads·X·Facebook / 설정 후보·6B 대상 | 로컬 adapter 조건부 개발 | Metricool 서비스 문서상 후보; 유료 runtime 제외 | 이번 브랜드 조회에 항목 없음 | 구현·인증 없음 | Threads/X 불변 ID, Facebook Page ID, 지원 형식·권한 | X add-on·Facebook Page 권한·현 플랜 미확인 |
| 위 SNS 게시별 성과 / `MetricsStore`, collector 미등록 | 로컬 collector; 무료 Metricool 읽기 후보 | 유료 API 대체 제외 | 브랜드 조회만 성공; 지표 조회 미실행 | 결과 정규화 필요 | verified delivery/게시 ID 대조, 기간·definition·출처, 오류/미지원/0 구분 | 상시 API 접근·이력 한도 미확인 |
| 추천 게시 시각 / 기존 계획·슬롯 | 저장된 자체 실적 기반 제안; 무료 Metricool 후보 | 보조 제안만 | 미조회 | 구현 없음 | timezone·추천 기간, 기존 슬롯·hold 우선, 사용자 일정 변경과 분리 | 지원 네트워크별 확인; 도구상 Threads는 추천 시각 대상 아님 |
| YouTube 키워드·경쟁·트렌드·댓글 리서치 / 기존 기획 | 로컬 근거·이력 기반 기획 | vidIQ 유료 연구는 채택 제외 | 도구 인증 무료 응답 있음; 유료 연구 미실행 | 자체 제안 구현 필요 | 실제 검색량/전체 시장 추세 unavailable 처리, 제안과 원고 구분 | 대부분 연구 호출5 credits; public 조사도 비용 발생 |
| 제목·썸네일 평가/제안 / 기존 producer 보조 | 승인된 구독 텍스트·로컬 규칙/렌더 | vidIQ credit 기능은 채택 제외 | 미실행 | 로컬 추가 구현 필요 | 산출물 provenance·revision·재검토, 규칙 검사≠CTR 예측 | 제목 제안5·썸네일 생성22 credits |
| YouTube private 성과·유지율 / collector 미등록 | 기존 권한의 공식 collector 검토 | vidIQ 유료 분석은 채택 제외 | 양쪽 `user_channels=[]` | 미등록 | 정확한 authorized channel, 지표별 수집·비용·기간 | private scope 미확인; 공개 조회를 private로 대체 표시 금지 |
| 기존 YouTube 제목·설명·태그·공개/예약·썸네일 변경 | 기존 플랫폼 경계로 별도 검토 | vidIQ 유료 수정은 채택 제외 | authorized 채널 없음 | 별도 변경 기능 미등록 | owner/OAuth 검증, 변경 전후 기록, 별도 변경 permit | 수정5 credits/호출, 썸네일 별도; API key 경로로 대체 불가 |
| 대본·썸네일·클립·영상·음성 제작 / 개인 구독 producer | 기존 개인 producer 유지; vidIQ 학과 별도 후보 | 개인 기본 교체 불가 | 생성 호출0 | vidIQ producer 없음 | 학과 작업별 provider/media/budget 정책·job 복구·로컬 산출물 검증 | 대본1/min, 클립9/source min, 음성14/1000자, 영상 모델별. 기존 개인 구독 정책 완화0 |
| Instagram owner Reel 실적·Reel/Trial 발행 | vidIQ 0 credit 기능 제한 후보; 로컬 경계 유지 | 무료 범위 별도 비교 | vidIQ Instagram 연결 미조회 | 둘 다 미등록 | platformAccountId·publishingAvailable·OAuth·정확한 영상/캡션/AI표시·다단계 복구 | 세션 설명상0 credits, 실제 권한 미확인; 무료가 발행 승인 대체 아님 |
| 네이버·Blogger·Tistory / Blog 5개 adapter | 기존 발행기 | 유지 | 이번 조사에서 미검증 | 기존 6A 경계 유지 | 기존 플랫폼별 인증·검증 후속 | 두 서비스의 해당 블로그 원문 발행 대체 근거 없음 |
| 독립 calc/source 검토·axlock·STOP·원장·quota·복구 | AutoSNS 기존 공통 경계 | 유지 | 해당 없음 | 기존 계약 유지 | provider도 같은 경계를 통과 | Metricool 내부 리뷰는 독립 계산/출처 검토·AutoSNS permit 대체 아님 |

vidIQ 비용 숫자는 공식 MCP 안내와 현행 도구 설명을 대조한 참고값이다. 잔액150도 자동 사용하지 않는다. 허용된 0 credit 호출에서도 실제 `_credits.used`를 보존하며 가격 미확인 호출은 실행하지 않는다. 현재 구독 가격·세금·계정별 결제 수단·실제 추가 비용은 미확인이다. [vidIQ 비용 안내](https://support.vidiq.com/en/articles/15082430-vidiq-mcp)

## 0 credit 기준의 실제 채택과 자체 구축

우선순위 P0는 비용·실행 경계, P1은 기존 기능 재사용으로 구현할 범위, P2는 부족한 실자료·권한 때문에 범위를 제한할 기능이다. 파일명에 “신규 제안”으로 표시한 항목은 아직 존재하거나 구현됐다는 뜻이 아니다. 현재 허용된 기존 구독의 고정비까지 새 무료로 계산하지 않는다.

| 기능 | 무료 활용 가능 범위 | 요금 조건 | 자체 대체: 구체 재사용·신규 파일/시험 제안 | 제한 | 우선순위 |
|---|---|---|---|---|---|
| 계정·브랜드·credit 상태 | 이미 수행한 Metricool 브랜드·vidIQ 채널/잔액0 credit 조회 재사용 | 신규 API 결제 불필요 | `integration_store.py`는 preference 유지. 신규 제안 `common/operations/provider_capabilities.py`, `tests/operations/test_provider_capabilities.py`: 기능별 비용·인증·runtime 상태를 서버가 구분 | 무료 연결 조회는 publish/상시 권한 증거가 아님 | P0 |
| 예약·스케줄 | Metricool 무료 MCP는 플랜 한도 안에서 예약 기능을 제공하나 이번 작업에서 쓰기0 | 상시 REST는 Advanced/Custom 필요 → 채택 제외 | `schedule_time.py`, `worker.py`, `worker_service.py`, `execution_service.py`, `RuntimeStore`·ledger·기존 플랫폼 adapter 재사용. 신규 제안 `tests/integration/test_local_schedule_recovery.py`: 시각·재시작·중복·STOP·unknown·quota 검증 | 기존 adapter가 없는 SNS는 새 개발·대상 인증이 여전히 필요. Metricool에 맡기던 상시 서버의 내구성을 자체 worker가 책임짐 | P1/6B |
| 게시별 성과 | 무료 MCP의 허용 지표 조회는 가능 후보지만 이번에는 재조회0 | Metricool 상시 API는 유료. vidIQ YouTube 분석5 credits → 채택 제외 | `metrics.py`·`metrics_store.py`·`metrics_models.py` 재사용. 신규 제안 `common/operations/metrics_collectors.py`, `tests/operations/test_local_metrics_collectors.py`: 기존 `common/analytics/collect_*`의 순수 정규화 부분만 계정별 계약으로 이식 | 브라우저·token 경로가 고정된 기존 CLI를 통째로 import/실행하지 않음. 현재 권한·허용 비용으로 못 얻는 수치는 unavailable | P1/6B |
| 제목·대본·설명·태그 제안 | vidIQ 제목5/대본1분당1 → 자동 이용0 | 포함 credit도 사용하지 않음 | 승인된 `ClaudeSubscriptionProvider`·`ProviderPolicy`·`produce_content` 재사용. 신규 제안 `common/operations/packaging_rules.py`, `tests/operations/test_packaging_rules.py`: 입력 근거·길이·중복·금칙어·AI고지 검사와 제안. 개인 구독 전용 정책 유지 | 새 유료 LLM/학교 gateway fallback0. 구독 실행 자체도 설치·기능 증거가 있어야 함. 글자 수/규칙 점수는 CTR 예측이 아님 | P1/6B |
| 썸네일 | vidIQ 평가/생성은 credit 필요 → 이용0 | 평가 대부분5, 생성22 credits | 재사용 이미지·기존 Remotion 템플릿/폰트·`production_media.py`·`probe_media`로 로컬 렌더. 신규 제안 `common/operations/thumbnail_layout.py`, `tests/operations/test_thumbnail_layout.py`: safe 영역·해상도·텍스트 넘침·출력 hash | vidIQ 독점 click score와 동등한 예측을 만들었다고 표시하지 않음. 생성형 새 그림은 별도 비용 없는 승인 도구가 없으면 미지원 | P1/6B |
| 음성·영상·클립 | vidIQ 가져오기/상태는0이나 생성은 유료 → 생성 이용0 | 음성14/1000자·클립9/source min·영상 모델별 | `production_media.py`의 `VoiceboxAudioRunner`·`RemotionVideoRunner`, `probe_media`, 기존 검토한 템플릿 재사용. 신규 제안 `tests/integration/test_local_media_pipeline.py`: 음성·자막·프레임·길이·hash 검증 | 실제 runner 주입/로컬 모델 준비는 미확인. Voicebox 자동 종료/재기동·앱 강제종료0. 새 AI 영상·음원 생성과 동등 기능은 아님 | P1/6B |
| 키워드 검색량·경쟁·트렌드·CTR 예측 | vidIQ public research라도 보통5 credits → 이용0 | 포함 credit도 자동 소비0 | `planning_context.py`·저장된 `MetricsStore`·기존 콘텐츠 이력으로 자체 채널의 주제/성과 추세·근거 링크 기반 제안. 신규 제안 `common/operations/research_context.py`, `tests/operations/test_research_context.py` | vidIQ 검색량·경쟁도·시장 전체 outlier·proprietary score 재현 아님. 공개 근거 없으면 unavailable; 로컬 빈도/휴리스틱을 실제 검색량/예측 CTR로 이름 붙이지 않음 | P2/6B |
| 최적 게시 시각 | Metricool 무료 MCP 후보; 이번 미조회 | 플랜별 지표·추천 가능 범위 확인 필요 | `planning_context.py`·기존 슬롯 유지. 신규 제안 `common/operations/posting_time_proposals.py`, `tests/operations/test_posting_time_proposals.py`: 충분한 관측 시에만 요일·시간별 표본·기간·불확실성 표시 | 추천은 자동 스케줄 변경이 아님. 표본 부족이면 unavailable, 기존 hold/슬롯 우선 | P2/6B |
| Instagram owner insights/Reel 발행 | 세션 도구 설명상0 credit | 0 credit여도 별도 OAuth/계정·최종값 승인 필요 | 현 단계는 도구 후보 표시만. 성과를 사용할 때 기존 MetricResult 경계로 정규화. 발행은 기존 permit/adapter 계약 선행 | 연결 미조회·쓰기0. 무료 기능을 이유로 새 권한·외부 변경을 자동 실행하지 않음 | P2/6B |
| 독립 검토·잠금·원장·블로그 | 기존 경계 유지 | 새 provider 비용 없음 | 기존 calc/source authority·axlock/STOP·ledger·Blog adapter 회귀 유지 | Metricool 리뷰·vidIQ AI 분석이 독립 기술 검토를 대신하지 않음 | P0 |

지표를 얻기 위한 기존 플랫폼 API도 비용·권한이 자동 무료라고 가정하지 않는다. 현재 허용된 공식 read scope·할당량·비용으로 확보할 수 있을 때만 새 collector를 활성화한다. 기존 브라우저 collector를 사용해야 하면 `shared/axlock.py` 프로필 잠금이 선행하며, 이 검토에서는 브라우저를 열지 않았다.

## 0 credit·자체 구축을 위한 최소 코드 변경 지도

아래는 후속 구현 단위이며 이 문서에서 적용하지 않았다. 진행 중인 6A의 원장·공통 실행 경계는 계속 사용한다.

1. **기능·대상·비용 바인딩:** `common/operations`에 서버 소유 provider capability/connection binding을 별도로 둔다. 외부 후보는 `(account_id, connection_id, provider_id, brand_id, platform_target_id)`를 검증하고 문서상 지원/도구 노출/실인증/웹 구현/실행 활성/최근 실패를 분리한다. 기본 추가비용 예산은0이며 미확인 비용도 차단한다. `integration_store.py`의 preference는 비밀 없는 선호 설정으로 유지한다. `read_model.py`는 Metricool YouTube/TikTok 후보를 포함하되 actual ready로 합성하지 않는다.
2. **로컬 읽기 전용 collector부터:** `metrics.py`의 기존 주입 계약에 맞춰 게시별 결과를 `MetricResult`로 정규화한다. 기존 analytics의 하드코딩 계정·token 경로·브라우저 실행을 분리하고 서버 고정 credential/target allowlist를 사용한다. `definition_id`, lifetime/interval, 기간·timezone·관측 시각을 보존한다. 웹 GET는 저장 결과만 읽고 수집은 별도 명시 작업으로 한다. 유료 Metricool HTTP client는 이번 자체 구축의 필수 의존성에서 제외한다.
3. **로컬 예약·PublicationAdapter 재사용:** 기존 `ExecutionService`·worker·ledger·`schedule_time.py`가 실행 시각·영속 상태·permit을 소유한다. 기존 Blog/YouTube adapter를 유지하고 나머지 SNS adapter는 6B에서 지원·권한 확인 후 구현한다. `common/publishers/__init__.py`에는 서버가 선택한 정확한 connection의 전송 하나만 등록한다. prepare는 순수 함수, submit은 permit 소비 뒤 원격 변경이다. 무료 MCP를 사람이 선택해 활용할 수 있어도 무인 worker의 인증을 합성하지 않는다.
4. **예약과 최종 게시 구분:** 로컬 예약도 접수·원격 제출·공개 검증 상태를 분리한다. 추후 무료 Metricool MCP를 연결하는 경우 planner id/uuid와 SNS remote ID를 별도로 결속한다. 현행 도구 설명상 예약 수정·리뷰 요청은 id가 바뀌고 uuid는 유지된다. 예약 접수는 `scheduled`까지만 기록하고 공개 본문·미디어 검증 뒤에만 `verified`로 간다. 목록 부재·통신 실패·리뷰 통과를 미게시/공개 성공으로 합성하지 않는다. 응답 유실은 unknown으로 보존하며 무조건 재전송하지 않는다.
5. **로컬 연구·패키징·미디어:** 승인된 기존 구독 텍스트 provider와 규칙 기반 검사, Voicebox·Remotion leaf를 명시 등록해 사용한다. vidIQ 유료 연구/생성 provider는 등록하지 않는다. 산출물 hash·재시작 중복 방지·producer provenance를 기록하고 콘텐츠 revision으로 ingest해 독립 검토를 받는다. 개인 `ProviderPolicy` 제한과 학과 작업별 기존 정책을 유지하며 신규 유료·학교·다른 계정 fallback을 차단한다. 유료 연구값을 자체 추정으로 위장하지 않는다.
6. **전환과 상태 UI:** 구현·실인증·쓰기 범위가 없는 기능은 미확인/미지원으로 표시한다. adapter/collector 등록만으로 `operations.json enabled`, 실행 정책, 기존 job schedule owner, legacy TikTok 큐, crosspost enabled를 바꾸지 않는다. 경로별 실증거와 rollback을 확보한 뒤 기존 cutover 절차로 단일 실행 주체를 전환한다.

Metricool 한 요청에 여러 SNS를 묶으면 플랫폼별 일부 성공과 응답 유실이 생긴다. 최소 구현은 **delivery당 정확한 대상 하나**로 제한하고, 배치 최적화는 후속으로 둔다. 미디어를 공개 호스팅/정규화하는 작업도 외부 부수효과이므로 producer의 단순 준비 단계에 숨기지 않는다. 공식 API는 미디어 URL·mediaId 등 별도 요구를 제시하므로 임시 vidIQ URL을 영구 예약 자산으로 그대로 쓰지 않는다. [Metricool API 미디어 요구](https://help.metricool.com/basic-guide-for-api-integration-r97af)

Metricool/vidIQ의 내부 리뷰·댓글 답글·북마크·경쟁 목록 변경도 외부 상태 변경이다. 특히 Metricool 리뷰 발송은 이메일 알림을 발생시킬 수 있다. 독립 calc/source 검토를 대신하거나 자동으로 외부 리뷰어에게 보내는 경로로 연결하지 않는다.

### 6A 완료 경계와 후속 6B

현재 6A는 공통 실행·원장·독립 검토 계약·기존 Blog5/YouTube2 bridge·23경로 보존 및 전환 차단 증거를 구현·검토하는 범위다. 위 자체 구축을 이유로 6A 완료 조건을 “전체 무료 서비스 구현”으로 확대하거나 진행 중인 수정·리뷰를 취소하지 않는다.

6B의 새 계획에는 비용0 capability 정책, 로컬 예약 복구 수락, 미등록 SNS adapter, 계정별 read-only collector, 로컬 패키징·미디어 pipeline, 지표 기반 기획 제안, 무료 MCP의 선택적 수동 활용을 묶는다. 각 기능은 기존 원장 경계를 재사용하되 실제 구현·운영 수락을 별도로 한다. 이 검토는 6B 구현 완료나 실계정 인증을 의미하지 않는다.

## 필요한 검증

문서 작성만 수행했으므로 아래 시험은 실행 결과가 아닌 후속 수락 기준이다.

| 시험 | 필수 결과 |
|---|---|
| 기본 disabled·startup·GET·preference 저장 | credential 조회·OAuth refresh·subprocess·네트워크·credit 소비·발행0 |
| Metricool 브랜드/플랫폼 ID가 다른 owner/destination에 바인딩됨 | 제출·성과 저장0, 명시적인 target mismatch. 브랜드명/handle만으로 통과0 |
| vidIQ authorized channel 없음·API key로 쓰기 요청 | private analytics·영상 변경·Reel 발행0; 공개 지표로 성공 위장0 |
| 개인 구독 정책으로 vidIQ 연구/생성 fallback | 정책 위반으로 차단, 개인 제한 완화0, 다른 계정 credential 조회0 |
| 포함 vidIQ150 credit·비용 미확인 도구·유료 Metricool API 호출 | 잔액이 있어도 자동 호출0, 신규 결제/업그레이드/키 발급/권한 추가0, 금액을0으로 추정0 |
| 자체 패키징·리서치 점수 | 근거·규칙·표본만 표시. 실제 vidIQ 검색량/경쟁도/proprietary score·예측 CTR로 표시0, 자료 부족은 unavailable |
| 예약 접수·공개 처리·실패·목록 부재 | 접수≠공개, scheduled/unknown 보존, 최종 remote ID·내용·미디어 검증 전 verified0 |
| 같은 request key·응답 유실·재시작·id 변경/uuid 유지 | 외부 중복 제출0, 기존 remote reference·unknown·quota 보존, 승인 snapshot 바뀌면 재검토 |
| Metricool 성과0/error/unsupported/null·기간·브랜드 합계 | 실제0 보존, 오류를0으로 변환0, 다른 게시 ID/대상 혼입0, lifetime을 월 실적으로 합산0 |
| provider 산출물·리뷰 뒤 내용/미디어 변경 | revision/hash 결속, 독립 producer/reviewer 신원 유지, 원고 수정 뒤 이전 승인 재사용0 |
| 23개 교차 경로·TikTok 큐·중지 상태 | owner/destination·조건·슬롯·변환·AI고지·지연 책임·enabled/unknown 보존, news.tiktok 자동 활성0 |
| 발행 잠금·STOP·quota·permit | 기존 axlock 공유 자원과 비상 정지 검사를 거침. API 예약도 발행 부수효과로 통제. 브라우저가 필요한 경로는 기존 profile 잠금 유지 |
| 인증 만료·권한 철회·서비스/요금 한도 오류 | 최근 실패와 이전 성공 분리, 실패를 다른 provider/계정으로 자동 우회0, 비밀 노출0 |

기존 회귀 대상은 `tests/test_integration_store.py`, `tests/test_web_integrations.py`, `tests/publishers/test_blogs.py`, `tests/publishers/test_youtube.py`, `tests/operations/test_metrics*.py`, `tests/operations/test_production*.py`, `tests/integration/test_phase6a_acceptance.py`, `tests/integration/test_owner_fences.py`다. 새 provider에는 fake transport를 주입해 위 경계를 먼저 확인하고, 실제 인증/비공개·예약·공개 시험은 그 결과와 구분해 기록한다.

## 남은 미확인과 완료 범위

- 두 Metricool 연결의 실제 요금제·API 허용·X add-on·청구 주체·게시 잔여량·read/write 권한.
- AutoSNS 각 connection의 플랫폼 불변 대상 ID와 브랜드 바인딩. 현재 YouTube null 값을 추정으로 채우지 않았다.
- 상시 runtime의 공식 별도 인증 제공·저장·만료·철회·복구 경로. 대화 인증의 이관은 실행하지 않았다.
- vidIQ YouTube/Instagram 소유 계정 연결, 쓰기 OAuth 및 private 분석 권한. 공식 FAQ와 세션 TikTok 도구 범위 차이.
- 실제 게시 결과 조회로 본문·미디어·최종 URL을 검증할 수 있는지, 각 지표의 history/지연·누락·정의, 기존 23경로의 출력 동치.

**이번 완료 범위는 무료·유료 기능 분류, 자체 구축 범위와 구현 지도 작성이다. 실제 발행 공급자 교체·인증·credit 소비·스케줄 전환·전체 운영 수락은 실행하지 않았다.**
