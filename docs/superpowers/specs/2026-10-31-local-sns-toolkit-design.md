# 추가 비용 없는 SNS 도구 자체 구축 설계

작성일: 2026-10-31. **상태: 사용자 미승인 설계안. 제품 구현·인증·발행·스케줄 전환 전이다.** 진행 중인 6A 구현·리뷰는 계속하며, 이 설계가 그 작업을 취소하거나 완료 범위를 바꾸지 않는다.

근거는 사용자 지시 “vidIQ, Metricool 이용으로 변경 할 수 있는것 검토 후 교체”, 추가 지시 **“유료인 경우 기능을 분석해서 여기에서 별도로 구축합시다”**, [공급자 교체 검토](../../audits/2026-10-31-vidiq-metricool-replacement-review.md)와 현재 AutoSNS 코드다. 이 설계를 위해 외부 조사·계정 호출을 반복하지 않았다.

## 목적과 선택

유료 SNS 도구의 유용한 작업을 AutoSNS 기존 웹에서 수행한다. 비용0은 **추가 SaaS 결제·유료 API·credit 소비0**을 뜻한다. 기존 승인 구독, 로컬 컴퓨터·저장소·전력·운영시간은 사용한다. 이를 총운영비0이라고 표시하지 않는다. vidIQ에 포함된150 credit도 자동 사용하지 않는다.

| 대안 | 장점 | 부담·제약 | 판단 |
|---|---|---|---|
| 유료 SaaS/API 중심 | Metricool의 상시 예약 API, vidIQ 데이터·제작 기능 활용 | Metricool HTTP API는 상위 유료 요금제, vidIQ 주요 연구·제작은 credit 사용. 현재 계정별 쓰기 권한과 상시 인증도 미확인 | 추가 지시와 맞지 않아 채택하지 않음 |
| 모든 기능 자체 재현 | 외부 SaaS 의존 축소 | 독점 검색량·시장 전체 데이터·CTR 예측까지 동등하게 재현할 근거가 없고 구현 범위가 큼 | 전체 재현을 목표로 삼지 않음 |
| 무료 기능 선택 활용 + 로컬 구축 | 현재 실행·원장·콘텐츠·성과 구조를 재사용하며 추가 비용 차단 가능 | 무료 MCP의 대화 인증은 웹 서버 인증이 아니며, 없는 데이터는 unavailable로 남음 | **권고안**. 사용자가 고른 “유료면 자체 구축” 방향을 구체화한 제안이며 이 세부 설계 자체는 아직 미승인 |

무료 MCP는 Codex에서 승인된 연결의 비용0 읽기 보조로만 사용한다. 웹 runtime은 독립 인증·지원·운영 증거 없이는 MCP를 호출하지 않는다. 대화 쿠키·토큰·Metricool hash를 추출해 재사용하지 않는다. 플랫폼 공식 API도 무료라고 가정하지 않으며 실제 호출 비용·기존 권한·할당량을 따로 확인한다. 유료이거나 비용이 미확인이면 차단한다.

## 범위와 사용자 흐름

별도 사이트나 새 최상위 메뉴를 만들지 않는다. 기존 8개 메뉴 중 다음 화면을 확장한다. 아래 화면·버튼명은 구현 제안이다.

| 기존 화면 | 확장 내용 | 사용자 동작의 결과 |
|---|---|---|
| SNS 도구 | 계정별 로컬 기능, 무료 외부 후보, 추가 비용, 구현·인증·실행 상태, 마지막 점검 | 상태 조회는 저장된 근거만 읽는다. 선호 저장과 실행 활성은 분리한다. |
| 기획 | 입력 원고·등록된 출처·저장 성과를 사용한 제목/태그 후보와 주제 제안 | 먼저 로컬 미리보기. 후보 적용은 명시 선택 후 기존 콘텐츠 revision/CAS 절차를 사용한다. |
| 성과 | 지표 정규화와 CSV 미리보기·검증·명시 가져오기 | 출처·관측 시각·기간·단위·계정·게시 ID·품질을 표시한다. 오류·미지원·미수집·실제0을 구분한다. |
| 배포 상세 | 선택된 로컬 전송기, 예약 시각, 대상, 준비 검사·차단 사유·최근 관측 | 기존 제출/승인/검증 흐름을 사용한다. 기술 검사·CSV 가져오기로 발행 승인이나 verified를 만들지 않는다. |

P1 기본 흐름은 `입력 snapshot → 서버 정책/대상 검사 → 순수 분석·정규화 → 근거가 있는 미리보기 → 명시 적용/가져오기`다. 생성·발행·외부 수집은 미리보기에 숨기지 않는다. 권한/Origin/CSRF 등 기존 관리 웹의 검사와 정확한 요청 필드 검증을 재사용한다. GET·startup은 무쓰기·외부 호출0이다.

## P0: 서버 소유 capability와 비용 정책

클라이언트가 provider·임의 endpoint·credential 경로·가격·scope·실행 명령을 지정할 수 없다. 기존 `IntegrationStore`는 계속 비밀 없는 preference만 저장한다. 별도 서버 catalog가 action 단위 기능을 소유한다.

`ToolCapability` 제안 필드는 `action_id, provider_id, platforms, effect(read|local_write|external_write), implementation_status, runtime_kind(local|codex_assisted|unavailable), cost_kind(no_additional_cost|credits|paid|unknown), required_evidence`다. 연결별 관측 투영은 `account_id, connection_id, target_id, auth_status, read_scope_status, write_scope_status, checked_at, last_failure`를 분리한다. 문서상 지원, 도구 노출, 실제 인증, 웹 구현, 실행 활성은 서로 대체하지 않는다.

서버의 `evaluate_tool_action(action_id, context) -> allowed, reason_codes, evidence_refs`는 부수효과 없이 검사한다. 추가 API 비용·credit은0만 허용하고 paid/credits/unknown은 거부한다. `no_additional_cost`라는 catalog 값도 실제 근거가 없으면 허용 증거가 되지 못한다. 플랫폼 호출은 별도 현재 비용/권한 증거가 필요하다. 기존 승인 구독 제작은 기존 `ProviderPolicy`를 그대로 통과해야 하며 이 catalog로 허용 범위를 넓히지 않는다.

외부 호출 입구에서 재검사하고 다른 provider/계정·유료 모델·학교 gateway로 자동 fallback하지 않는다. 목록·환경 변수·요청 body로 정책을 완화하지 않는다. 이 기능의 기본 배포는 disabled이며 catalog 조회 자체로 credential 조회·refresh·process 시작을 하지 않는다.

## P1: 먼저 자체 구축할 기능

### 제목·태그·근거 기반 기획

신규 `packaging_rules.py`는 원고·등록 출처·명시 키워드·선택한 플랫폼만 받는 순수 함수다. 제목 길이, 중복, 빠진 핵심어, 금칙 표현, 태그 수·중복, 필요한 AI 고지 등을 검사한다. 입력 어휘로 후보를 조합하고 변경 이유를 반환한다. 결과는 `input_hash, rules_version, candidates, findings, evidence_refs, unavailable_fields`로 고정한다. 글자 수 규칙이나 어휘 빈도를 실제 검색량·경쟁도·예측 CTR·vidIQ 점수로 부르지 않는다.

`research_context.py`는 기존 `planning_context.py`와 저장 성과/콘텐츠 이력을 읽어 같은 계정·같은 정의·호환 기간의 주제별 결과와 근거를 제시한다. 표본 수·관측 기간·누락을 드러내고 원인이나 시장 전체 추세로 확대하지 않는다. 자료가 부족하면 제안을 제한하고 unavailable을 반환한다. P1에서 새 웹 수집·유료 리서치는 하지 않는다.

문장 생성이 필요하면 이미 승인된 구독 텍스트 제작 흐름을 명시 선택해 실행한다. 설치·실행 능력 증거 없는 provider는 사용할 수 없다. 개인 `subscription_only`와 학과 작업별 기존 정책을 유지하며, 새 provider 등록이나 구독 제한 완화는 이 설계에 포함하지 않는다. 후보 적용 후 내용이 바뀌면 새 revision으로 독립 계산·출처 검토를 다시 받는다.

### 썸네일 기술 검사와 로컬 템플릿

`thumbnail_checks.py`는 업로드된 로컬 자산의 형식·크기·해상도·종횡비·파일 hash와 템플릿의 글자 넘침·safe 영역을 검사한다. 가독성 규칙은 규칙 설명과 함께 표시하며 시각적 성공이나 CTR 예측을 보장하지 않는다.

`thumbnail_layout.py`는 검토된 기존 이미지·폰트·고정 템플릿으로만 로컬 출력한다. `production_media.py`의 asset/provenance 검증과 Remotion template hash 계약을 재사용한다. 템플릿 runner·폰트가 준비되지 않았으면 unavailable이다. 생성형 새 그림·비용이 드는 이미지 API로 우회하지 않는다. 기존 `VoiceboxAudioRunner`·`RemotionVideoRunner`를 사용하는 음성/영상도 같은 명시 media leaf 경계를 지키며 앱 강제종료·Voicebox 재기동을 자동 수행하지 않는다.

### 성과 정규화와 CSV

P1은 로컬 파일·저장된 지표부터 시작한다. `metrics_normalization.py`의 순수 변환은 `platform, target_id, remote_id, metric_name, value, observed_at, basis, period, timezone, source_kind`를 받아 `MetricResult` 계약에 맞게 검증한다. 불명확 지표 정의·단위·기간을 추정으로 채우지 않고 error/unsupported와 빈 values로 구분한다. null을0으로 바꾸지 않는다.

`metrics_csv.py`는 허용된 열·파일 크기·행 수·숫자/시간 형식만 받고 수식·HTML·명령을 실행하지 않는다. preview에는 정규화된 행·오류·대상 미확인·source digest를 표시한다. import는 `preview_digest, request_key`를 검증하며 같은 파일/행 재전송은 중복 저장하지 않는다. 파일 경로·임의 parser/import 모듈을 요청에서 받지 않는다.

CSV는 플랫폼의 공개 검증 증거가 아니다. 초기 구현은 기존 legacy import 방식의 `legacy_reported` 또는 미배정 관측으로 보존하고, 서버가 허용한 실제 source_kind/필드만 사용한다. 알려지지 않은 enum을 추가해 우회하지 않는다. owner/destination이 확정되지 않은 행은 미배정으로 남긴다. `verified_delivery`는 계속 원장의 공개 verified·정확한 target/remote ID·revision 검증이 필요한 기존 collector 경계만 생성한다. CSV로 승인·발행 상태·remote ID 검증을 합성하지 않는다.

### 로컬 예약 재사용

새 SaaS 스케줄러를 구현하지 않고 `schedule_time.py`, `ExecutionService`, `WorkerService`, `RuntimeStore`, ledger와 기존 adapter를 재사용한다. 예약 시각은 offset과 timezone을 함께 검증하고 재시작 후 같은 회차를 복구한다. dispatch 전에도 최신 정책·대상·승인·잠금·quota를 확인한다. 접수/예약/제출/공개 검증을 분리하며 응답 유실은 unknown으로 남긴다. unknown을 자동 queued로 되돌리거나 다른 전송기로 재발행하지 않는다.

## P2 및 기존 6B·6C·6D와의 연결

P1의 로컬 도구 완료를 전체 SNS 운영 완료로 취급하지 않는다. 다음은 기존 필수 후속과 함께 남는다.

| 후속 | 남는 필수 범위 |
|---|---|
| 6B | 미등록 SNS adapter, 계정별 실제 대상·읽기/쓰기 권한 수명주기, 실수집 collector, local media runner 실연결, 23경로·TikTok 큐 출력/조건 동치, 경로별 실제 발행·관측·롤백 수락 |
| 6C | 기존 계획의 계정별 코드·자료 물리 이행과 경로/credential/profile 경계 검증. 이 도구 설계 때문에 해당 목표를 생략하지 않음 |
| 6D | 기존 계획의 보호된 외부 접속·실제 Mac/휴대폰 운영 검증·전체 수락. 로컬 웹에서 미리보기가 된 사실로 대체하지 않음 |

플랫폼 API의 허용 비용·권한을 확보할 수 없으면 그 기능을 차단하고 남은 항목으로 유지한다. 무료 기능으로 축소해 전체 목표를 완료 처리하지 않는다. 현재 `operations.json`의 YouTube target_id가 null인 상태도 이름으로 채우지 않는다.

## 계정·발행·실패 경계

- 원본 owner와 destination을 별도로 유지한다. 개인 원본→학과 배포의 제작비/콘텐츠 소유권은 개인이며 실적과 전송 credential은 학과 대상에 결속한다. 미등록 개인 SNS 계정을 만들어 연결하지 않는다.
- 서버가 선택한 connection의 불변 target ID와 실제 관측이 일치해야 한다. 읽기 성공을 쓰기 권한으로 확대하지 않고 다른 계정 토큰을 조회하지 않는다.
- 발행·브라우저 프로필 사용은 기존 axlock/STOP·permit·quota·lease 계약을 유지한다. API 방식 예약도 발행 부수효과다. `shared/axlock.py`를 거치지 않는 새 경로를 만들지 않는다.
- 생성·기술 검사·플랫폼 내부 리뷰는 독립 calc/source 검토를 대신하지 않는다. 내용/미디어 변경은 새 revision/hash와 필요한 재검토를 요구한다.
- 순수 로컬 미리보기는 같은 입력 hash로 다시 계산할 수 있다. 외부 제출·비용이 있는 작업은 효과 확인 없이 자동 retry하지 않는다. 과거 성공·최근 실패·미확인 상태를 각각 표시하고 비밀·원본 인증 응답은 웹에 노출하지 않는다.

## 파일 지도와 구현 순서

아래 신규 파일은 제안이며 아직 생성하지 않았다. 기존 파일의 실제 수정 위치·HTTP 계약은 이 설계 승인 후 구현 계획에서 확정한다.

| 순서 | 신규 제안 | 재사용·수정 지점 | 시험·수락 대상 |
|---|---|---|---|
| 1/P0 | `common/operations/provider_capabilities.py`, `tool_cost_policy.py` | `integration_store.py`, `read_model.py`, SNS 도구 UI | 신규 `test_provider_capabilities.py`, `test_tool_cost_policy.py`: paid/credits/unknown 차단·상태 정직성·요청 변조·GET 무호출 |
| 2/P1 | `packaging_rules.py`, `research_context.py` | `planning_context.py`, ContentStore 기존 CAS·기획 UI | 신규 `test_packaging_rules.py`, `test_research_context.py`: 결정성·근거·계정 격리·비용0·잘못된 점수 표시0 |
| 3/P1 | `thumbnail_checks.py`, `thumbnail_layout.py` | `production_media.py`·검토된 템플릿·기획/배포 상세 | 신규 `test_thumbnail_checks.py`, `test_thumbnail_layout.py`: 크기·넘침·자산 권한·hash·runner unavailable |
| 4/P1 | `metrics_normalization.py`, `metrics_csv.py` | MetricsStore/MetricResult·기존 legacy import·성과 UI | 신규 `test_metrics_normalization.py`, `test_metrics_csv.py`: 0/null/오류·기간·미배정·digest·중복·검증 상태 위조0 |
| 5/P1 | 새 운영 스케줄러 없음 | `schedule_time.py`, worker/service/ledger·배포 상세 | 신규 `tests/integration/test_local_schedule_recovery.py`와 기존 회귀: 재시작·시간대·unknown·동일 회차 중복0 |
| 6/P2 | 플랫폼별 adapter/collector는 6B 계획에서 지정 | `common/publishers`의 명시 factory와 `metrics.py` 주입 경계 | 실제 비용/권한·대상·게시·성과 증거를 fixture와 구분해 수락 |

UI에는 별도 자격증명 입력·결제·가입·임의 실행 설정을 넣지 않는다. 미리보기는 읽기 분석/로컬 산출물 준비이며 적용·가져오기·배포 상태 변경과 버튼·응답을 구분한다. 기존 콘텐츠 편집·성과 가져오기 계약을 재사용할 수 없으면 새 계약을 명시해 검토한 뒤 구현한다.

## 완료 기준

| 기준 | 수락 증거 |
|---|---|
| 추가 비용0 | paid/credits/unknown 도구가 호출 전 차단됨. 포함150 credit 보유·provider 응답 변조·fallback에도 외부 소비0. 기존 승인 구독 정책 변경0 |
| 실행 기본값 | startup/GET/preference 저장에서 credential 조회·refresh·subprocess·외부 호출0. 실행은 계속 disabled |
| 결과 정직성 | title/tag 규칙과 표본 설명은 제공하되 독점 검색량/CTR 동등 주장0. 데이터 부족은 unavailable |
| 계정·권한 | owner/destination/connection/불변 target 불일치·미등록 계정·타계정 credential은 거부. read 성공으로 write 허용0 |
| 콘텐츠·검토 | 후보 적용 CAS 충돌409, revision/hash 변경 후 이전 승인 재사용0. 독립 calc/source 경계 유지 |
| CSV·성과 | 동일 request/file/row 중복0, null≠0, incompatible 기간 합산0, 미배정 보존, CSV로 verified 생성0 |
| 예약·복구 | timezone·동일 회차·응답 유실·재시작·STOP·잠금·quota 회귀 통과. unknown 유지, 자동 재발행0 |
| 기존 운영 보존 | 23개 교차 경로의 owner/대상/조건/슬롯/변환/AI고지·disabled/unknown 및 TikTok 중지 상태 보존. 기존 Blog5/YouTube2·웹 8메뉴 회귀 통과 |
| 단계 구분 | P1 로컬 도구 수락과 6B 실제 권한/수집/발행, 6C 이행, 6D 외부접속·실기기·전체 운영 증거를 따로 기록 |

문서 승인 후에는 P0→P1의 구현 계획을 작성하고, 6A의 진행 중 변경을 보존하면서 파일 소유권과 회귀 범위를 확정한다. **현재 문서는 설계 제안이며 구현 완료·실계정 인증·실제 발행 성공을 주장하지 않는다.**
