# 추가 비용 없는 로컬 SNS 도구 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 AutoSNS 웹에 추가 결제·API·credit 소비 없이 사용할 수 있는 로컬 패키징·썸네일·근거 기반 기획·CSV 성과 도구를 연결하고 기존 예약 실행 경계를 검증한다.

**Architecture:** 서버가 기능·비용·대상을 소유하고 순수 규칙/정규화 모듈을 공통 서비스로 조합한다. 콘텐츠 적용은 기존 ContentStore revision/CAS, 수동 성과는 MetricsStore의 legacy_reported·미배정, 예약은 기존 ExecutionService/worker/ledger를 재사용한다. 무료 MCP는 Codex 보조로 분리하며 웹에 외부 provider 실행 경로를 추가하지 않는다.

**Tech Stack:** 기존 Python3·unittest·SQLite, ES modules·Node 내장 test, 기존 Pillow/로컬 폰트가 가용할 때의 이미지 leaf. 신규 SaaS·유료 API·패키지 자동 설치 없음.

**Spec:** [승인 설계](../specs/2026-10-31-local-sns-toolkit-design.md), [공급자 검토](../../audits/2026-10-31-vidiq-metricool-replacement-review.md). 2026-10-31 사용자 설계·계획 작성 승인. **2026-10-31 사용자 실행 계획 승인·개발 시작 지시를 받았다.** 최대 병렬 SDD 방식은 이미 선택됐으며 다시 선택받지 않는다.

## Global Constraints

- 비용0은 **추가 SaaS 결제·유료 API·credit 소비0**이다. 기존 승인 구독·로컬 운영자원은 사용하되 총운영비0이라고 표시하지 않는다. vidIQ에 포함된150 credit도 자동 사용하지 않는다.
- 유료이거나 비용이 미확인이면 차단한다. 플랫폼 API의 실제 비용·기존 scope·할당량은 별도 확인하며 무료라고 추정하지 않는다. 신규 결제·가입·인증·권한 추가·외부 계정 호출·발행·스케줄 전환0이다.
- 무료 MCP는 Codex에서 승인된 연결의 비용0 읽기 보조로만 사용한다. 대화 쿠키·토큰·Metricool hash를 추출해 웹 runtime에 재사용하지 않는다. 유료 모델·학교 gateway·다른 provider/계정으로 자동 fallback하지 않는다.
- 별도 사이트나 toolkit 전용 최상위 메뉴를 만들지 않는다. 사용자 추가 지시로 기술사 메뉴가 추가된 기존 9개 메뉴를 유지한다. 현재 SNS 도구는 `accounts`의 `renderIntegrations()` 하위 패널이며 기획/성과/배포 상세와 함께 확장한다.
- 개인 `subscription_only`와 학과 작업별 기존 ProviderPolicy, 독립 calc/source 검토, revision/hash 결속을 유지한다. 기술사 블로그·친구 요청·PDF도 같은 경계를 적용한다. 새 기술사 원고를 생성하지 않는다.
- CSV는 `legacy_reported` 또는 미배정 관측으로 보존한다. CSV·기술 검사·사용 선호로 승인·verified_delivery·게시 검증·실인증을 합성하지 않는다. owner/destination·불변 target ID·읽기/쓰기 권한을 분리한다.
- startup/GET/preference 저장은 무쓰기·credential 조회/refresh·subprocess·외부 호출0이다. 실행은 계속 disabled이며 toolkit 기본 정책도 disabled다. 명시 주입한 로컬 정책만 격리 QA에서 활성화한다.
- 발행/브라우저 경로는 기존 `shared/axlock.py`, STOP·permit·quota·lease를 유지한다. API 예약도 발행 부수효과다. unknown 자동 queued/재발행·다른 전송기 우회0이다.
- 독점 검색량·경쟁도·시장 전체 outlier·예측 CTR·vidIQ 점수를 재현했다고 표시하지 않는다. 공개/저장 근거가 부족하면 unavailable이다. null·오류·미지원·미수집·실제0을 구분한다.
- 기존 23경로·TikTok 큐·중지/unknown·Blog5/YouTube2·기술사 일차/요청/자료를 보존한다. P0/P1 수락으로 6B~6D의 실제 운영 목표를 줄이지 않는다.
- 다른 에이전트가 같은 작업 트리에서 작업 중이다. 타인 변경을 되돌리거나 `git add -A`/전체 reset하지 않는다. 아래 파일 소유권 밖 수정은 통합 담당과 먼저 조정한다.

## Review Focus

1. CSV의 BOM·따옴표 안 줄바꿈·중복 헤더·수식 선행 문자·비정상 숫자: 조용한 열 이동/실행/0 변환 없이 정규화하거나 명시 거부한다. Task4 시험.
2. 미리보기 뒤 원고 수정·다른 계정 전환·늦은 HTTP 응답: 다른 revision/계정에 후보를 적용하지 않고 입력을 보존한다. Task6·Task8 시험.
3. 손상 이미지·과도한 픽셀·EXIF 회전·symlink 폰트/템플릿: 실제 decoder와 서버 자산 검증으로 차단하며 입력 경로·프로그램을 실행하지 않는다. Task3 시험.
4. 비용0 위조·만료된 증거·기존150 credit·read 성공으로 write 허용: 서버 정책을 우회하지 못하고 credential/외부 I/O 전에 거부한다. Task1·Task5 시험.
5. CSV 동일 요청/다른 파일·행 순서 변경·동시 가져오기·registry 변경: 영속 receipt/행키로 중복을 막고 대상이 바뀌면409, 운영 원장·승인·검증 상태는 변경하지 않는다. Task4·Task8 시험.

---

## 시작 전 dependency와 보호 배포

- [ ] **D0:** [6A 수락 근거](../../audits/2026-10-30-web-phase6a-acceptance.md) 및 `.superpowers/sdd/2026-10-30-web-phase6a/progress.md`에서 진행 중 A9 수정·독립 재리뷰·전체 Node/필수 Python·브라우저 수락을 포함한 **6A code gate 완료**를 부모가 확인한다. 미완료를 toolkit 작업으로 덮지 않는다. 이 문서 작성과 별도로 제품 구현은 D0와 이 계획 승인 이후다.
- [ ] **D1:** 실행 시작 때 HEAD·staged diff·held manifest 및 추가 보호 index.html SHA를 기록한다. `.superpowers/sdd/2026-10-30-web-phase6a/web-artifacts/manifest.json`의 `original_sha256`/`artifact_sha256`와 현재 실제 webroot를 대조한다. **desired HEAD와 actual working old SHA는 다를 수 있다.** actual 파일을 옛 구현으로 판단해 되돌리거나 덮어쓰지 않는다.
- [ ] **D2:** 현재 보호 집합 held6는 `ax-console/app/web/{api.js,app.js,content_editor.js,operations_panel.js,styles.css,index.html}`다. 6A manifest의 기존5개에 부모가 추가 보호 중인 index.html도 포함한다. index.html은 이 계획에서 메뉴를 추가하거나 변경하지 않으며, 실행 시 현재 actual/desired SHA를 별도로 기록하고 변경이 없으면 stage하지 않는다. 해당 실제 파일은 기존8769/8767 owned 서버의 allowlist refresh·coordinated restart 전 덮어쓰기 금지. Task8만 desired HEAD를 별도 `.superpowers/sdd/2026-10-31-local-sns-toolkit/web-artifacts/`로 편집하고 manifest/QA overlay를 만든다. 최신 6A artifact가 HEAD와 다르면 부모와 baseline을 조정한다.
- [ ] **D3:** QA는 임시 source/W와 별도 webroot 복사본에 desired HEAD+artifact를 overlay하고 fixture auth/loopback 임시 포트를 쓴다. 실계정·원본 source·실제 프로필·8700·기존8769/8767 프로세스를 작업자가 변경하지 않는다. 새 모듈을 actual W에 써도 live app import는 먼저 바꾸지 않는다.
- [ ] **D4:** held6 커밋은 통합 담당이 artifact bytes를 `git hash-object -w --stdin`으로 넣고 `git update-index --cacheinfo 100644 <blob> <target>`로 **index만** 갱신한다. `git add <held-target>`는 사용하지 않는다. 커밋 전 staged 경로가 자기 소유 목록인지 확인하고 타인 stage를 포함하지 않는다. 실제 배포는 부모 조정 후 SHA 재검증·서버 allowlist 반영·restart·8769/8767 확인으로 별도 수락한다.

## 파일 지도·병렬 소유권

각 담당자는 자기 파일만 편집하고 타인의 변경에 맞춘다. 아래 신규 파일명은 이 계획의 확정 계약이며 아직 구현됐다는 뜻이 아니다.

| 작업 | 독점 파일/책임 | 선행 |
|---|---|---|
| Task1 정책 | 신규 `common/operations/provider_capabilities.py`, `tool_cost_policy.py`; `tests/operations/test_provider_capabilities.py`, `test_tool_cost_policy.py` | D0~D1 |
| Task2 텍스트 | 신규 `common/operations/packaging_rules.py`, `research_context.py`; 대응 unittest2개 | Task1 계약 |
| Task3 이미지 | 신규 `common/operations/thumbnail_checks.py`, `thumbnail_layout.py`; 대응 unittest2개 | Task1 계약 |
| Task4 CSV | 신규 `common/operations/metrics_normalization.py`, `metrics_csv.py`; 대응 unittest2개 | Task1 계약 |
| Task5 서비스/HTTP helper | 신규 `common/operations/local_toolkit.py`, `ax-console/app/web_tools.py`; `tests/operations/test_local_toolkit.py`, `tests/test_web_tools.py` | Task1~4 |
| Task6 독립 UI | 신규 `ax-console/app/web/toolkit_api.js`, `toolkit_controller.js`, `toolkit_panel.js`; `tests/web_toolkit.test.mjs` | Task1 계약·Task5 HTTP 계약 고정; fixture로 병행 가능 |
| Task7 예약/보존 | 신규 `tests/integration/test_local_schedule_recovery.py`; 필요 수정은 이 시험만, runtime 버그는 기존 소유자와 조정 | Task1 뒤 시험 준비 병행; GREEN은 Task5 필요 |
| Task8 통합/수락 | Modify `ax-console/app/web_server.py`, `ax-console/app/read_model.py`; held6는 artifact만. 신규 `tests/test_web_toolkit_server.py`, `tests/integration/test_local_toolkit_acceptance.py`, `tests/web_toolkit_integration.test.mjs`; 신규 수락 audit/runbook | Task1~7·D2~D4 |

Task1 완료 뒤 Task2/3/4를 가능한 최대 병렬로 진행한다. Task6은 고정 계약과 fake 응답으로 독립 개발하고 Task5 구현 뒤 실제 연결한다. Task7은 runtime 파일을 소유하지 않아 병행한다. 공유 web_server/read_model/app/CSS는 Task8에만 소유시켜 통합을 직렬화한다. 각 작업은 구현자 자체검토→새 독립 spec review→code quality review를 통과한 뒤 후행이 소비한다. 사용 가능한 슬롯보다 많은 agent를 동시에 만들지 않는다.

## 구현 확정값과 기존 계약

- 기존 `ContentStore.update(content_id, expected_revision, payload)`는 **전체 편집 payload**를 받으며 root `tags` 필드가 없다. 태그 제안은 선택 variant의 `text` 초안에만 반영하고 `title,kind,series,status,original,variants,sources`를 보존해 기존 저장을 호출한다. owner는 update로 변경할 수 없다. `read_asset(content_id,revision,asset_id)->(metadata,bytes)`를 사용하고 HTTP에서 경로를 받지 않는다.
- 기존 `MetricResult` status는 `ok|unsupported|error`, `MetricObservation.source_kind`는 `verified_delivery|legacy_reported`다. 수동 행의 정상 status는 **legacy_reported**이며 ok로 저장하지 않는다. 미배정은 새 enum이 아니라 nullable owner/destination/connection 등과 `uncertainties`다. `MetricsStore.import_rows(plan, request_key=...)`, `get_import_result(preview_digest,request_key)`의 영속 receipt·트랜잭션을 재사용한다. 운영 DB schema3/성과 schema1을 바꾸지 않는다.
- 아래 크기·규칙은 플랫폼 공식 한도가 아닌 **로컬 도구의 확정 제한**이다: CSV UTF-8/BOM,256KiB/1000행; 이미지 PNG/JPEG/WebP,8MiB/20,000,000pixels/변4096px; 키워드20개·각50자; 제목 후보 최대3개·태그10개. 규칙 문구에 “플랫폼 API 한도 검증”이라고 쓰지 않는다.
- 썸네일 로컬 preset은 `landscape.v1=1280×720`, `portrait.v1=1080×1920`, safe inset 각 변5%, text 최대3줄이다. 긴 문구는 말줄임/자동 의미 변경 없이 overflow로 반환한다. 서버 등록 `common/remotion-shorts/public/Pretendard-Bold.otf`의 hash와 읽기 가능성으로 폰트를 검증하며 없으면 unavailable. 기존 RemotionVideoRunner는 MP4 leaf이므로 PNG renderer라고 가장하지 않는다. 기존 Pillow 템플릿의 순수 배치만 이식하고 legacy 모듈 import/네트워크는 하지 않는다.
- CSV 열은 필수 `platform,target_id,remote_id,metric_name,value,observed_at,basis`, 선택 `period_start,period_end,timezone,title`다. owner/source_kind/content/delivery/credential 열을 받지 않는다. 사용자 문자열의 경로·URL을 열지 않는다. count 지표 `views,likes,comments,shares,saves,clicks,impressions`만 v1에서 다루며0이상 정수만 정상 값이다. `ctr,watch_time,cost` 등 단위/분모가 필요한 미등록 정의는 unsupported다.

### Task 1: 서버 capability·추가 비용0 정책

**Files:** Create `common/operations/provider_capabilities.py`, `common/operations/tool_cost_policy.py`, `tests/operations/test_provider_capabilities.py`, `tests/operations/test_tool_cost_policy.py`.

**Interfaces:** Produces frozen `ToolCapability`(승인 spec 필드), `ToolkitPolicy(enabled:bool=False)`, `CostEvidence(kind:str,credit_units:int,additional_cost_zero:bool|None,evidence_ref:str,valid_until:str|None)`, `ToolActionContext(owner_account_id:str|None,destination_account_id:str|None,connection_id:str|None,target_id:str|None,policy:ToolkitPolicy,runtime_kind:str,cost_evidence:CostEvidence,now:datetime,read_scope_status:str='unknown',write_scope_status:str='unknown')`, `DEFAULT_CAPABILITIES`. `evaluate_tool_action(action_id:str, context:ToolActionContext, *, catalog=DEFAULT_CAPABILITIES)->dict` returns `allowed:bool,reason_codes:list[str],evidence_refs:list[str]`. `capabilities_snapshot(account_id:str, registry, *, policy:ToolkitPolicy)->dict` returns `account_id,toolkit_enabled,external_execution_supported,items,connections`이며 stored registry만 읽는다. toolkit_enabled는 로컬 기능 정책값이고 external_execution_supported=False는 이 toolkit의 외부 실행 미지원이다. 전역 발행 enabled를 이 값으로 덮어쓰지 않는다. context/evidence는 서버 전용이며 HTTP body에서 직접 생성하지 않는다. bool/int/timezone·enum·중첩 불변성을 검증한다.

- [ ] **RED 작성:** `test_paid_credit_unknown_and_forged_zero_never_run`, `test_expired_evidence_and_read_does_not_grant_write`, `test_catalog_is_not_authenticated_runtime`, `test_default_disabled_has_no_io`를 작성한다. credits150·`cost=0` 요청·expired evidence·external_write/read-only 조합을 모두 allowed=false로 assert한다. socket/subprocess/credential resolver spy는0이다.
  ```python
  self.assertFalse(decision['allowed'])
  self.assertEqual(external_calls, [])
  self.assertEqual(default_snapshot['toolkit_enabled'], False)
  ```
- [ ] **RED 실행:** `python3 -m unittest tests.operations.test_provider_capabilities tests.operations.test_tool_cost_policy -v` → 신규 모듈 부재 FAIL을 확인한다.
- [ ] **구현:** catalog에 `local.packaging.preview`, `local.research.preview`, `local.thumbnail.inspect`, `local.thumbnail.render`, `local.metrics.csv.preview`, `local.metrics.csv.import`, `local.schedule.inspect`를 고정한다. 로컬 built-in version을 cost evidence로 쓰고 render/import는 local_write로 구별한다. Metricool 유료 API·vidIQ credit 기능은 차단 사유를 갖는 후보만, 무료 MCP 후보는 runtime_kind=codex_assisted로 반환한다. caller가 catalog·비용·권한을 교체할 수 없다. 개인 ProviderPolicy는 수정하지 않는다.
- [ ] **GREEN 실행:** 위 두 unittest → OK. `python3 -m unittest tests.test_integration_store tests.operations.test_production_providers -v` → 기존 preference/구독 guard 회귀 OK.
- [ ] **자체검토:** frozen 구조 안 list/dict 우회가 없는지, client 주장으로 비용 증거가 되는 경로가 없는지 확인하고 task report에 command/결과·미확인을 기록한다.
- [ ] **커밋:** 자기 네 파일만 `git add`한 뒤 `git commit -m "feat: add server-owned zero-cost toolkit policy"`. staged 타인 파일은 포함하지 않는다.

### Task 2: 제목·태그 규칙과 저장 근거 기획

**Files:** Create `common/operations/packaging_rules.py`, `common/operations/research_context.py`, `tests/operations/test_packaging_rules.py`, `tests/operations/test_research_context.py`.

**Interfaces:** Consumes Task1 gate(서비스에서 호출), 기존 `build_planning_context(account_id,registry,store,*,runtime_store=None)`. Produces `build_packaging_preview(snapshot:Mapping, *, platform:str, keywords:tuple[str,...]=())->dict` (`input_hash,rules_version,candidates,findings,evidence_refs,unavailable_fields`), `build_research_preview(account_id:str, registry, metrics_store, content_store, *, runtime_store=None)->dict` (`groups,missing,evidence_refs,unavailable_fields`). 후보는 `id,title,hashtags,reasons`이며 순서는 결정적이다.

- [ ] **RED 작성:** `test_korean_unicode_zero_width_duplicates_and_length`, `test_candidate_changes_only_input_vocabulary`, `test_owner_destination_evidence_is_not_crossed`, `test_incompatible_definitions_and_small_samples_are_unavailable`을 작성한다. NFC 정규화·앞뒤 공백 제거만 수행하고 보이지 않는 제어문자는 findings로 표시한다. 후보/태그 한도, 원문/출처 불변, 실제 CTR/search_volume 필드 부재, legacy_reported를 verified 성과 합계에 넣지 않음을 assert한다.
  ```python
  self.assertLessEqual(len(preview['candidates']), 3)
  self.assertEqual(snapshot, before_snapshot)
  self.assertIn('search_volume', preview['unavailable_fields'])
  ```
- [ ] **RED 실행:** `python3 -m unittest tests.operations.test_packaging_rules tests.operations.test_research_context -v` → 신규 모듈 부재 FAIL.
- [ ] **구현:** 입력 문장/명시 keyword만 조합한다. 허위 수치·자격·경험을 추가하지 않는다. 제목은300자 저장 한도 안에서 길이·중복·키워드 포함 여부를 규칙으로 안내하고 태그는 입력 어휘만 최대10개로 정규화한다. 기획은 기존 projection이 분리한 대상·definition·basis·period별로 보존하며 표본3건 미만은 추천 순위를 만들지 않고 근거 목록만 반환한다. 증거 없는 검색량/경쟁도/CTR은 unavailable이다. 새로운 웹/LLM 호출은 없다.
- [ ] **GREEN 실행:** 위 unittest 및 `python3 -m unittest tests.operations.test_planning_context -v` → OK. source URL 문자열은 근거 참조일 뿐 fetch가 없음을 spy로 확인한다.
- [ ] **자체검토:** snapshot 전체를 반환해 비밀을 노출하지 않는지, 후보 적용에 새 root tags를 요구하지 않는지, source/owner를 추정하는 분기가 없는지 점검한다.
- [ ] **커밋:** 자기 네 파일만 add 후 `git commit -m "feat: add local packaging rules and evidence-based planning"`.

### Task 3: 썸네일 실제 기술 검사·로컬 템플릿

**Files:** Create `common/operations/thumbnail_checks.py`, `common/operations/thumbnail_layout.py`, `tests/operations/test_thumbnail_checks.py`, `tests/operations/test_thumbnail_layout.py`.

**Interfaces:** Produces `inspect_thumbnail(data:bytes, *, media_type:str, expected_sha256:str|None=None)->dict` (`status:ok|error|unavailable,sha256,width,height,findings`), `render_thumbnail(request:Mapping, *, renderer=None)->dict` (`status:completed|blocked|unavailable,reason_code,asset:dict|None,findings`), server-only `PillowThumbnailRenderer(font_path:Path, *, font_sha256:str)` callable. request는 `preset_id,title,image_bytes|None,image_sha256|None`만 사용한다. 완료 asset은 `data:bytes,filename,media_type,sha256,width,height,font_sha256,template_version`; 미디어는 렌더 후 다시 decode·hash한다. 출력 PNG도8MiB 한도를 적용한다.

- [ ] **RED 작성:** `test_signature_is_not_successful_decode`, `test_pixel_bomb_exif_orientation_and_oversize`, `test_font_symlink_or_hash_change_blocks`, `test_three_lines_safe_box_overflow_never_truncates`, `test_unavailable_renderer_never_calls_network`를 작성한다. 실제 작은 PNG와 손상 파일, EXIF 회전 fixture를 decode하고20M/8MiB/4096 제한을 검증한다.
  ```python
  self.assertEqual(render_thumbnail(request)['status'], 'unavailable')
  self.assertNotEqual(inspect_thumbnail(broken_png, media_type='image/png')['status'], 'ok')
  self.assertEqual((rendered['asset']['width'], rendered['asset']['height']), (1280, 720))
  ```
- [ ] **RED 실행:** `python3 -m unittest tests.operations.test_thumbnail_checks tests.operations.test_thumbnail_layout -v` → 신규 모듈 부재 FAIL.
- [ ] **구현:** Pillow는 실제 실행 시에만 사용하고 미설치 시 unavailable이다. load 후 EXIF orientation을 정규화해 측정하며 decompression warning은 차단한다. 서버 고정 font/template만 사용하고 입력 이미지 hash·재사용 허용은 Task5가 ContentStore asset으로 확인한다. 기본 renderer=None이면 unavailable, 누락 폰트 대체/다운로드0. 순수 배치만 이식하고 `make_thumbnail.py`를 import하지 않는다. PNG를 `render_registered_media`의 새 KINDS로 임의 등록하거나 reviewed=true를 만들지 않는다.
- [ ] **GREEN 실행:** 위 unittest → OK. 기존 font와 Pillow가 가용한 격리 테스트에서 두 preset 출력의 decode·치수·hash·한글 text bbox를 확인한다. 미설치는 성공으로 가장하지 않고 unavailable 시험과 함께 환경 미확인으로 기록한다. `python3 -m unittest tests.operations.test_production_media -v` → 기존 미디어 권한 회귀 OK.
- [ ] **자체검토:** 입력 경로/외부 이미지 URL·명령을 받지 않는지, renderer가 글을 임의 축약하지 않는지, 기존 Voicebox/Remotion life-cycle과 승인 경계를 변경하지 않았는지 확인한다.
- [ ] **커밋:** 자기 네 파일만 add 후 `git commit -m "feat: add local thumbnail checks and registered templates"`.

### Task 4: 지표 정규화·CSV preview/import 계획

**Files:** Create `common/operations/metrics_normalization.py`, `common/operations/metrics_csv.py`, `tests/operations/test_metrics_normalization.py`, `tests/operations/test_metrics_csv.py`.

**Interfaces:** Consumes 기존 `MetricResult`, `MetricObservation`, `MetricsStore`. Produces `normalize_metric_row(row:Mapping)->MetricResult`, `build_csv_preview(csv_bytes:bytes, *, account_id:str, registry)->dict`, `import_csv(store, csv_bytes:bytes, *, account_id:str, registry, preview_digest:str, request_key:str)->dict`. preview는 `preview_digest,registry_revision,rows,counts,warnings,can_import`와 내부 전용 `plan`을 가지며 plan은 `{preview_digest,observations:[{observation_key,observation}]}`다. HTTP는 내부 plan을 내보내지 않는다.

- [ ] **RED 작성:** Review Focus1/5에 해당하는 `test_bom_quoted_newline_duplicate_header_and_formula`, `test_nan_bool_negative_fraction_and_null_not_zero`, `test_registry_scope_mismatch_and_unmapped_owner`, `test_duplicate_row_reorder_concurrent_receipt`, `test_changed_registry_or_payload_digest_is_conflict`를 작성한다. 행 순서만 바꾼 새 파일은 기존 행 추가0, 같은 request_key/다른 preview는409, 잘못된 한 행으로 부분 저장0을 assert한다.
  ```python
  self.assertEqual(saved['source_kind'], 'legacy_reported')
  self.assertIsNone(saved['owner_account_id'])
  self.assertEqual(second_import['imported'], 0)
  self.assertEqual(missing_value.values, {})
  ```
- [ ] **RED 실행:** `python3 -m unittest tests.operations.test_metrics_normalization tests.operations.test_metrics_csv -v` → 신규 모듈 부재 FAIL.
- [ ] **구현:** stdlib csv strict parser로 확정 열·256KiB·1000행을 검사한다. 구조 오류/중복 헤더/수식 선행 `=,+,-,@`(좌측 공백·제어문자 포함)는 거부한다. 숫자 음수는 거부 사유로 분리한다. 빈 value는 error·빈 values이며 NaN/Infinity/bool은 거부한다. 정의는 `manual.csv.<platform>.<metric>.v1`, basis는 lifetime 또는 완전한 interval만 허용한다. 미등록 정의는 unsupported·빈 values다.
- [ ] **구현 계속:** registry의 정확한 platform/target 일치가 하나일 때만 destination/connection을 붙인다. CSV만으로 원본 owner를 알 수 없으므로 owner/content/delivery는None, uncertainty에 manual_source와 owner_unassigned를 남긴다. 다른 선택 계정의 대상은 거부하고 미등록 대상은 미배정 보존한다. 정상 행도 source_kind/status=legacy_reported이며 verified_delivery 생성0이다. normalize 입력의 source_kind는 서버가 legacy_reported로 고정하며 CSV 열에서 받지 않는다. preview digest는 원본 bytes hash·정규화 plan·account·registry revision을 결속한다. observation key는 정규화한 최종 관측의 canonical hash로 만들고 provenance에 변동시각/파일명/파일순서/registry revision을 넣지 않는다. registry revision만 바뀌고 매핑·관측이 같으면 기존 행이며, 실제 매핑 변경은 별도 불변 관측으로 보존한다.
- [ ] **GREEN 실행:** 위 unittest와 `python3 -m unittest tests.operations.test_metrics_store tests.operations.test_metrics tests.operations.test_metrics_legacy -v` → OK. import는 현재 registry로 preview를 재계산한 뒤 digest 대조→영속 receipt→`import_rows` 순서다. registry가 바뀌면 동일 요청도409이며 새 미리보기가 필요하다. 성공 재전송은 기존 저장 결과와 같은 counts/IDs다.
- [ ] **자체검토·커밋:** 내부 plan/CSV원문을 HTTP에 노출하지 않는지, source_kind/status enum을 발명하지 않았는지 확인한 뒤 네 파일만 add하여 `git commit -m "feat: normalize and import manual CSV metrics safely"`.

### Task 5: 로컬 서비스·정확한 HTTP helper

**Files:** Create `common/operations/local_toolkit.py`, `ax-console/app/web_tools.py`, `tests/operations/test_local_toolkit.py`, `tests/test_web_tools.py`. 이 작업은 `web_server.py`를 수정하지 않는다.

**Interfaces:** `LocalToolkitService(*, registry, content_store=None, metrics_store=None, runtime_store=None, policy=ToolkitPolicy(), thumbnail_renderer=None, thumbnail_authorizer=None, clock)`; `.capabilities(account_id)`, `.packaging_preview(body)`, `.research_preview(body)`, `.thumbnail_inspect(body)`, `.thumbnail_render(body)`, `.csv_preview(body)`, `.csv_import(body)`, `.schedule_inspect(body)` 각각 dict 반환. 서버 전용 `thumbnail_authorizer(snapshot:Mapping,asset:Mapping)->bool`은 기존 자산 재사용 승인과 exact hash를 검증하는 주입 callback이다. `web_tools.recognizes(path)->bool`, `handle(service,method,path,query,read_body)->dict|None`을 제공한다. 서버 조립은 Task8이다.

- [ ] **RED 작성:** `test_exact_fields_and_disabled_before_asset_read`, `test_wrong_account_connection_revision_and_target`, `test_credit_and_unknown_cost_never_call_leaf`, `test_thumbnail_returns_bytes_without_ingest_or_review`, `test_csv_changes_only_metrics_store`를 작성한다. `read_asset`/renderer/import/credential spies를 통해 validation·gate 순서를 검사하고 operations DB/ContentStore·approval hash가 전후 동일함을 assert한다.
  ```python
  self.assertEqual(operations_bytes_after, operations_bytes_before)
  self.assertEqual((asset_reads, credential_reads, submit_calls), ([], [], []))
  self.assertNotIn('credential_ref', public_result)
  ```
- [ ] **RED 실행:** `python3 -m unittest tests.operations.test_local_toolkit tests.test_web_tools -v` → 신규 모듈 부재 FAIL.
- [ ] **구현:** URL은 GET `/api/v2/tools/capabilities?account=all|personal|dept`; POST는 같은 base의 `packaging-preview,research-preview,thumbnail-inspect,thumbnail-render,metrics-csv-preview,metrics-csv-import,schedule-inspect`만 허용한다. unknown 필드·query·중복/비정상 ID는 StoreError(invalid), stale revision/digest는 ConflictError, disabled/미등록 runner는 명시 blocked/unavailable이다. POST body의 provider/cost/actor/credential/command/path는 받지 않는다.
- [ ] **구현 계속:** packaging body=`{content_id,revision,connection_id,keywords}`, research=`{account_id}`, inspect=`{content_id,revision,asset_id}`, render=`{content_id,revision,asset_id|null,preset_id,title}`, CSV preview=`{account_id,csv_text}`, import=`{account_id,csv_text,preview_digest,request_key}`, schedule=`{delivery_id}`로 고정한다. snapshot과 registry에서 owner/destination/platform/target을 만든다. null target은 로컬 분석만 가능하며 실제 연결 미확인을 별도 표시한다. 작업마다 gate를 재검사한다. 썸네일 입력 이미지는 ContentStore에 있다는 사실만으로 재사용 허가하지 않는다. asset/hash에 대한 서버 thumbnail_authorizer가 없거나False면 renderer 호출 전 차단한다. asset_id=null인 텍스트 전용 고정 템플릿도 서버 등록 폰트/hash를 검증한다. 출력은 base64 PNG와 기술 메타데이터로만 반환하며 ContentStore ingest/독립검토 통과를 하지 않는다.
- [ ] **GREEN 실행:** 위 unittest → OK. GET는 policy disabled여도 상태를 반환하고 작업 실행/초기화0이다. W=None이면 상태 조회 외 작업은503, CSV 오류는400/413·digest conflict409, renderer 미등록은 상태unavailable이다. schedule_inspect는 `delivery_id,state,target_id,remote_id,scheduled_at,execution_enabled,reason_codes`를 root에 반환하고 prepare/submit/lookup/verify는 호출하지 않는다. 응답에서 내부 path/credential/profile/raw provenance를 제거한다.
- [ ] **자체검토:** read-only 서비스가 task runner가 되지 않았는지, 기존 subscription generation·발행 메서드를 추가하지 않았는지, `MetricResult(ok)`를 CSV verified로 저장하지 않는지 점검한다.
- [ ] **커밋:** 자기 네 파일만 add 후 `git commit -m "feat: expose guarded local toolkit service contracts"`.

### Task 6: 기존 화면에 끼울 독립 UI 모듈

**Files:** Create `ax-console/app/web/toolkit_api.js`, `toolkit_controller.js`, `toolkit_panel.js`, `tests/web_toolkit.test.mjs`. held6/app/CSS는 편집하지 않는다.

**Interfaces:** `createToolkitApi({fetcher=globalThis.fetch}={})`는 Task5 경로별 메서드를 제공한다. `createToolkitController({api,onChange})`는 계정별 입력/보고서·generation을 보존하며 `setContext({account,contentId,revision,connectionId})`, `preview(kind,payload)`, `stageCandidate(candidateId,{contentId,revision,inputHash})`, `isBusy()`, `isDirty()`, `discard()`를 제공한다. `createToolkitPanel({controller,document})`는 `.render({section,context,writable})`, `.element`, `.isBusy()`, `.isDirty()`를 제공한다. stageCandidate는 로컬 편집 patch만 반환하며 save/publish를 호출하지 않는다.

- [ ] **RED 작성:** `test_render_and_scope_change_never_submit`, `test_late_response_cannot_overwrite_other_account_or_revision`, `test_preview_then_dirty_edit_blocks_candidate_apply`, `test_csv_401_409_503_preserves_text_and_request_key`, `test_untrusted_titles_are_text_and_no_ctr_score`를 Node 테스트로 작성한다. fake DOM/fetch를 주입하고 클릭/키보드·busy/dirty/focus·중복 클릭을 검사한다.
  ```javascript
  assert.equal(writeCalls.length, 0);
  assert.equal(controller.isDirty(), true);
  assert.equal(personalDraft.csv_text, originalCsv);
  ```
- [ ] **RED 실행:** `node --test tests/web_toolkit.test.mjs` → 신규 모듈 부재 FAIL.
- [ ] **구현:** HTMLElement/textContent로만 출력한다. capability/비용/권한은 별도 라벨, unavailable은 안내로 표시한다. “초안에 반영”은 후보와 현재 content/revision/input hash가 같고 기존 editor가 clean일 때만 반환한다. 저장은 기존 editor 저장 버튼, 태그는 명시 선택 variant.text의 draft에만 붙인다. base64 이미지 다운로드와 “기존 첨부 기능으로 저장”을 구분한다. CSV는 사용자 파일을 브라우저에서 텍스트로 읽고 현재 hash/digest와 결속하며 변경하면 이전 preview/import를 무효화한다.
- [ ] **GREEN 실행:** 위 Node → pass. account 변경 시 이전 응답 취소/무시, 실패 시 draft/request key 보존, import 성공 전 실패를 미게시/성공으로 표시0, 메뉴 추가0·자동 호출0을 assert한다.
- [ ] **자체검토:** candidate/CSV 출력에 innerHTML·자동 download/import/save가 없는지, render/refresh가 외부 endpoint·쓰기 작업을 호출하지 않는지 확인한다.
- [ ] **커밋:** 자기 네 파일만 add 후 `git commit -m "feat: add isolated local toolkit UI modules"`.

### Task 7: 기존 로컬 예약·재시작·기술사 경계 회귀

**Files:** Create `tests/integration/test_local_schedule_recovery.py`. 기존 runtime·job·기술사 원문은 수정하지 않는다.

**Interfaces:** Consumes 실제 `normalize_schedule(value,timezone='Asia/Seoul')`, `ExecutionService.submit`, 기존 WorkerService/RuntimeStore·ledger와 fixture adapter. Produces 새로운 스케줄러가 아닌 재사용 수락 증거. fixture helper는 `tests/integration/test_worker_service.py`의 ServiceTests 계약에 맞추되 복사한 fake 예약 구현으로 대체하지 않는다.

- [ ] **RED 작성:** 신규 `test_toolkit_schedule_inspect_requires_real_delivery`, `test_timezone_unknown_and_restart_never_resubmit`, `test_toolkit_preview_does_not_change_engineer_jobs_or_policies`를 작성한다. Task5의 schedule_inspect가 없거나 아직 real delivery 투영을 연결하지 않은 상태에서 FAIL을 기록한다. DST ambiguous/nonexistent·offset 불일치·기존 remote ID/unknown·동일 회차 재전송·STOP/quota를 포함한다.
  ```python
  self.assertEqual(schedule_read['state'], 'unknown')
  self.assertEqual(submit_calls, [])
  self.assertEqual(job_config_bytes_after, job_config_bytes_before)
  ```
- [ ] **RED 실행:** `python3 -m unittest tests.integration.test_local_schedule_recovery -v` → schedule_inspect contract 미연결 FAIL. 순수 회귀가 처음부터 통과하면 그 결과를 정직하게 기록하고 RED를 만들기 위한 가짜 기능/guard 약화를 추가하지 않는다.
- [ ] **최소 연결:** schedule_inspect 구현이 필요하면 Task5 담당에게 정확한 실패를 전달하고 해당 파일 소유권 아래 구현한다. 반환 필드는 실제 delivery state/target/remote_id/scheduled_at·실행 policy·차단 사유의 안전한 projection뿐이다. worker claim/verify/submit/재예약은 호출하지 않는다. 새 task마다 저장된 policy·근거를 다시 표시하고 tool ready를 runtime active로 바꾸지 않는다.
- [ ] **GREEN 실행:** 신규 unittest와 `python3 -m unittest tests.integration.test_worker_service tests.integration.test_owner_fences tests.integration.test_phase6a_acceptance tests.operations.test_production_providers -v` → OK. 실제 source registry/crosspost/job bytes 전후 hash 동일, 외부 쓰기·모델 생성0을 확인한다.
- [ ] **자체검토:** 개인 측량·토목·건설안전·건축시공의 기존 blog daily/friend 지시문·PDF·구독·검토 경계가 유지되는지 정적 보존 시험으로만 확인한다. 기존 선언 존재가 managed 활성/실제 운영 증거가 아님을 보고한다.
- [ ] **커밋:** 시험 파일만 add 후 `git commit -m "test: preserve local scheduler and engineer workflow boundaries"`.

### Task 8: 서버·기존 8메뉴 통합과 보호 수락

**Files:** Modify `ax-console/app/web_server.py`, `ax-console/app/read_model.py`; held6는 D2 artifact로만 편집. Create `tests/test_web_toolkit_server.py`, `tests/integration/test_local_toolkit_acceptance.py`, `tests/web_toolkit_integration.test.mjs`, `docs/audits/2026-10-31-local-sns-toolkit-acceptance.md`, `docs/runbooks/local-sns-toolkit.md`, `.superpowers/sdd/2026-10-31-local-sns-toolkit/web-artifacts/manifest.json`. `ax-console/app/web/metrics_panel.js`·`ax-console/app/web/integration_settings.js`는 수정하지 않고 새 toolkit 패널을 옆에 조합한다.

**Interfaces:** Consumes Task5 handle/서비스, Task6 panel/API, Task7 수락. `create_server(...,toolkit_policy=None,toolkit_renderer=None,toolkit_asset_authorizer=None)` kw-only 인자만 추가하며 default는 disabled/미등록이다. 기존 서비스/metrics_registry/content_store와 동일 객체를 LocalToolkitService에 주입한다. `_STATIC`에 새 모듈3개를 추가하고 `_validated_target`에 capabilities의 account query만 허용한다. 모든 tools 경로는 기존 auth/Host/Origin·중복 header/JSON 검사 뒤 handle로 보낸다.

- [ ] **RED 작성:** 실제 loopback HTTP로 `test_tools_auth_origin_body_limits_and_readonly`, `test_csv_import_receipt_keeps_operations_unchanged`, `test_cost_and_target_tampering_never_calls_leaf`, `test_full_cas_save_after_staging_requires_new_review`를 작성한다. Node 통합은 기존 accounts/planning/analytics/detail에서 panel mount·8개 nav 유지·320/1280폭·dirty/focus·stale response를 검사한다. held 실제 bytes 보존/manifest 원본 hash 불일치 차단도 assert한다.
  ```python
  self.assertEqual(unauthenticated_status, 401)
  self.assertEqual(stale_revision_status, 409)
  self.assertEqual(before_operations_bytes, after_csv_import_operations_bytes)
  self.assertEqual(actual_held_file_sha, original_held_file_sha)
  ```
- [ ] **RED 실행:** `python3 -m unittest tests.test_web_toolkit_server tests.integration.test_local_toolkit_acceptance -v`, `node --test tests/web_toolkit_integration.test.mjs` → 신규 route/mount 미연결 FAIL. 소켓 sandbox 거부는 제품 실패와 구분해 부모에게 격리 loopback 검사 권한을 요청하며 같은 거부를 반복하지 않는다.
- [ ] **구현:** 서버 helper를 연결하고 read_model 후보를 Task1 기능별 투영으로 표시하되 snapshot 기본 계약/schema를 깨지 않는다. SNS 도구는 accounts 안, 규칙/기획은 planning·editor 안, CSV는 analytics 옆, schedule은 배포 상세에 조합한다. 기존 editor의 busy/dirty·하위 배포계획 guard를 보존한다. 후보는 draft에만 반영하고 기존 fullpayload PUT에서 revision 충돌409/새 revision·재검토를 확인한다. 실행·리뷰·발행 버튼을 새 도구가 대체하지 않는다.
- [ ] **GREEN 실행:** 위 집중 시험→OK/pass. `python3 -m unittest discover -s tests -p 'test_*.py'`, `node --test tests/*.test.mjs`를 실행해 전체 결과를 새 근거로 기록한다. `python3 -m py_compile common/operations/provider_capabilities.py common/operations/tool_cost_policy.py common/operations/local_toolkit.py ax-console/app/web_tools.py ax-console/app/web_server.py`와 `git diff --check`도 확인한다. 과거6A806/다른 단계 숫자를 이번 결과로 복사하지 않는다.
- [ ] **브라우저 수락:** D3 임시 webroot/auth에서8메뉴·SNS도구·규칙 적용→기존CAS저장·CSV오류/0/미배정/중복·썸네일 실제출력/미등록 안내·예약 unknown 표시·401/409/503 입력 보존·계정전환/늦은응답·320/1280폭·키보드/focus를 확인하고 screenshot/console 결과를 남긴다. 계정 호출/실제 모델/실발행은0이다.
- [ ] **자체검토·수락 문서:** local_rules_ready/manual_csv_ready/thumbnail_environment_ready/local_toolkit_enabled/live_collection_ready/production_ready를 분리한다. 실제 미수집/발행/인증·6B~D·아래 건축시공 필수 후속은 미완료로 남긴다. 기본 disabled·개인 구독·23경로 보존과 추가비용0 증거, 테스트/환경제약·held SHA를 runbook/audit에 기록한다.
- [ ] **커밋:** 신규 모듈/시험/문서·server/read_model만 경로별 add하고 held6는 D4 index-only로 stage한다. `git diff --cached --name-only`로 타인 staged 변경을 제외했는지 확인 후 `git commit -m "feat: integrate zero-cost local SNS toolkit with protected rollout"`. 부모의 coordinated deployment·allowlist refresh/restart 전 실제 held6는 덮지 않는다. 배포가 남으면 code_ready와 deployed_ready를 구분해 보고한다.

## 필수 후속: 건축시공 포함 기술사 운영과 6B~6D

최신 사용자 범위는 **건축시공기술사도 블로그 기획·제작·검토·정기 발행·친구 요청·PDF까지 동등하게 포함**한다. 현재 정적 확인상 `personal/claude-jobs/jobs/{building-daily,building-friend}.md`, `jobs.json`, `ax-console/config/automations.json`, `operations.json`에 두 선언이 있다. operations의 두 job은 legacy/enabled=false/activation_status=unknown이다. 따라서 “기존 선언 없음”도 “managed 운영 구현 완료”도 사실이 아니다. 숏츠4종 순환만으로 건축 블로그 요구를 충족했다고 보지 않는다.

| 필수 후속 파일 지도 | 실제 수락 조건 | 현 계획에서 하는 일 |
|---|---|---|
| 기존 `personal/claude-jobs/jobs/building-daily.md`, `building-friend.md`, `공통규칙.md`, `jobs.json`; 후속 신규 `personal/claude-jobs/managed/building-contract.md` 제안 | 정기/친구요청의 입력·일차/중복·접수순서·요청없음·출처·수치·PDF 요구를 분해하고 순수 제작/발행 분리. 실제 원문 지시·시각을 검증, 임의 시각 발명0 | 원문/설정 보존·미완료 항목 추적. 새 원고 생성·기존 잡 활성화0 |
| 후속 `operations.json`의 명시 managed job/binding, execution catalog·production/review 등록; `tests/integration/test_building_workflow.py` 제안 | 기존 개인 Tistory/Blogger 후보의 불변 대상·카테고리 ID·권한·실행 주체 확인. 개인 구독만 사용하고 calc/source 독립 실행·PDF 전 페이지 검토/다운로드 확인. 인증 없는 대상·임의 category·다른 계정 추정0 | 이 계획에서는 설정/target/카테고리 변경0. 기존 Blog5와 개인 정책 경계 보존 |
| 후속 `docs/superpowers/plans/2026-10-31-building-engineer-workflow.md` 제안 | daily/friend 각각 제작→검토→PDF→두 블로그 배포→채널별 실패 복구·unknown/중복 방지·실제 URL/본문/PDF 증거, 기존 요청·일차 이력 유지 | 별도 후속 구현·실수락 **필수**로 남김. 로컬 toolkit 완료로 대체0 |

6B는 남은 공식 권한 수명주기·SNS adapter·다중 부수효과·23경로/TikTok 전환, 6C는 실제 구독 제작/검산/출처/미디어/PDF·실대상 비공개/예약/공개·실성과 기획순환·launchd 전환/롤백, 6D는 물리이행·보호된 외부접속·실제 Mac/휴대폰 수락을 유지한다. 무료화로 불가능한 기능은 blocker로 남기고 목표를 축소하지 않는다.

## 작성자 자체검토와 실행 인계

- [x] **Spec coverage:** P0→Task1/5, 텍스트·기획→Task2/6, 이미지→Task3/6, CSV→Task4/5, 로컬예약→Task7, 기존화면/수락→Task8로 연결했다. Voicebox·Remotion·독립검토/기술사 운영은 기존 경계 보존과 필수6B~D/건축 후속으로 추적했다.
- [x] **Step scan:** 모든 Task에 RED 작성·실행, 정확한 구현 계약, GREEN 명령·예상 결과, 자체검토·한정 커밋을 넣었다. Task7의 기존 회귀가 처음부터 GREEN일 때 가짜 RED를 만들지 않는 예외를 명시했다.
- [x] **Type consistency:** MetricResult/MetricObservation status/source_kind, ContentStore fullpayload·read_asset tuple, MetricsStore plan/receipt를 실제 코드와 대조했다. CSV 내부 plan은 HTTP에 직렬화하지 않는다. 새 root tags·source_kind·schema 변경은 없다.
- [x] **Review Focus:** 다섯 조건을 Task1/3/4/5/6/8의 이름 있는 반례 시험에 연결했다. cost context는 서버 전용, 계정/소유와 연결 target은 별도다.
- [x] **Proportion/parallel:** 하나의 toolkit 조합에 필요한8개 테스트 가능한 단위로 제한했다. 본문 구현 대신 인터페이스·확정 값·시험을 적었고 공유파일은 Task8 단독, 나머지는 병렬 소유권으로 나눴다.
- [x] **6A/후속/배포:** code gate 선행, held6 HEAD/actual SHA 구분·artifact/index-only·부모 coordinated restart를 적었다. 6B~D·건축시공 동등 운영의 미완료 범위를 남겼다.

계획 검토 후 사용자가 구현을 승인하면 이미 선택한 **최대 병렬 SDD** 방식으로 진행한다. 실행계획 검토 전에는 제품 구현·외부 호출·결제·발행을 시작하지 않는다.
