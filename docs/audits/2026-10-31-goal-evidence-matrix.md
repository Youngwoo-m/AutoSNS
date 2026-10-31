# 전체 목표 증거 지도 — 2026-10-31

이 문서는 **운영 완료 판정이 아닌 남은 개발·수락의 지도**다. 기준 HEAD는 `1763a4d`이며 정적 파일·승인 문서·기존 수락 기록을 읽어 대조했다. 서버·브라우저·외부 계정·모델을 실행하지 않았다. 8769/8767의 실제 6A 유지 및 toolkit 배포 보류는 부모가 확인한 상태이며 이 문서 작성자가 재검증한 실행 증거가 아니다.

사용자 목표의 근거는 `docs/superpowers/specs/2026-10-30-account-channel-automation-design.md:11` 및 `:15`, 화면 목표는 `docs/superpowers/specs/2026-10-30-account-web-screens-design.md:12`다. 원본 소유와 게시 대상을 분리하고 기존 교차 게시를 보존한다. 이후 사용자 추가 지시로 기술사 메뉴를 포함한 **9개 메뉴**, 건축시공기술사, Instagram·Threads·X·Tistory·Facebook, 추가 SaaS/API/credit 소비 없는 자체 도구가 포함됐다. 옛 화면 설계의 8개 메뉴 표기는 최신 추가 범위를 취소하지 않는다.

## 요구별 구현·증거·남은 수락

아래 파일 경로와 줄은 기준 HEAD/현재 사본을 찾기 위한 근거다. held 정적 파일은 HEAD의 desired와 실제 배포 bytes가 의도적으로 다르므로 코드 존재를 배포 증거로 사용하지 않는다.

| 요구 | 현재 구현 경로·근거 | 현재 증거와 한계 | 남은 수락 | 다음 단계·선행조건 |
|---|---|---|---|---|
| 개인·학과 원본 소유/게시 대상 분리 | `common/operations/registry.py:25`, `context.py:6`, `content_store.py:76`; 승인 설계 §4 | 등록 연결·불변 대상·소유 검증과 저장 계약 존재. 계정 필터는 인증 증거가 아님 | 잘못된 credential/target/account 조합의 실제 adapter 전 호출 차단, 계정별 인증 확인 | 6B 권한·연결 수명주기. 실제 대상 확인 후 읽기 수락 |
| 기획·원고·버전·자산·검토 저장 | `content_store.py:47`, `:130`, 웹 editor; 화면 설계 §4 | 기존 full-payload CAS 및 버전별 기록. toolkit 격리 UI에서 개인v3→학과 변환문 태그→v4 저장, 원문·다른 변환문 보존은 부모가 확인 | 최신 화면의 401/409/503·키보드·dirty 보존 전체 분기, 실제 자료 저장 복원 | toolkit UI 잔여 오류 해결→최신 통합/화면 수락 |
| 기술사 별도 메뉴·4종 | `ax-console/app/web/engineer_panel.js:2`에 측량/토목시공/건축시공/건설안전; 6A 수락서 §실제 UI | 8769 기술사/건축 필터 표시 증거가 있음. 메뉴가 발행 실행을 의미하지 않음 | 4종별 daily/friend/PDF 실제 제작·검토·배포·후처리 연결 | 건축 workflow를 포함한 6C 작업 계약 |
| 건축시공 daily·friend·PDF | toolkit 계획 필수 후속 표; `personal/claude-jobs/jobs/building-daily.md`, `building-friend.md`, jobs.json/operations 선언 | 기존 선언 존재, legacy/비활성/활성 미확인과 managed 운영은 별개 | 일차·접수순서·중복·요청없음·출처·수치·PDF 전 페이지·두 블로그·실제 URL/다운로드 검증 | 원문 시각·카테고리·불변 대상 확인→제작/발행 분리→실수락. 기존 잡 임의 활성화 금지 |
| 실제 제작과 독립 검토 | `common/operations/production.py:99`, `review_runner.py:23`, `:106`, `:158` | 6A fixture의 제작 unit/revision/hash 결속. 실구독·실검산·실출처 수락은 미실행(6A 수락서:48) | 개인 subscription_only, 학과별 허용 정책, 독립 reviewer provenance와 수정 후 재검토 | 6C 구독 전용 실행/검토 등록 확인→실자료 수락. 유료 fallback 금지 |
| 이미지·음성·영상·PDF 품질 | `common/operations/production_media.py`, toolkit thumbnail leaf | 실제 Pillow 출력의 격리 증거와 코드 계약. Voicebox/Remotion/실 PDF 검토 수락은 아님(6A 수락서:54) | 미디어 규격·장면·글꼴·음성·고지·재사용 권리·PDF 안전 파싱/전 페이지/다운로드 | 6C 매체별 독립 검사·실산출물 수락 |
| 로컬 배포 계획·별도 공개 승인 | `execution_service.py:86`, `:152`, `:162`, `:176`; 웹 delivery/operations 패널 | 계획 승인과 발행 승인 분리. 실행 서비스 기본 비활성/미주입 | 실제 연결 하나씩 읽기→비공개/예약/공개 허용 범위 분리, 동결 원고/대상 재검증 | 6B 인증/adapter 선행→6C 대상별 운영 체크포인트 |
| STOP·잠금·한도·중복·복구 | `shared/axlock.py`, `common/operations/worker.py:41`, runtime_store/ledger, `execution_service.py:253`, `:262` | 가짜 원격 결과와 실제 SQLite/잠금 경계 시험. 실제 원격 exactly-once 보장 아님 | 응답 유실·실제 remote ID 관측·unknown 해소·프로필 대기·부분실패만 복구 | 6C 실대상 원장 결속 및 복구. unknown 재게시/과거 DB 복원으로 이력 삭제 금지 |
| 기존 23교차 경로·TikTok 조건 보존 | 승인 설계 §9; `docs/audits/2026-10-30-web-phase6a-acceptance.md:19` | 23개 규칙(기존 true5/false1/unknown17) 및 사건 predicate 비교. 관리 전환/실출력 동치 완료 아님 | 각 경로 owner/destination/변환/고지/지연 단일 책임, TikTok 30분·3시간·게시창·hold·재시도 보존 | 6B 단일 부수효과 adapter/selector→23경로 대상별 shadow→6C 전환 |
| 블로그 5연결 | `common/publishers/blog_runtime.py:25`, `:43`, `:64`, `blog_adapter.py`; 6A 수락서:32 | managed Blog5 코드/fixture 존재. 대상별 실인증·실발행·본문 검증은 별도 | Naver/Tistory 불변 ID/강한 부재 증명, Blogger 자산 업로드 등 미지원 경계, 실제 본문·후처리 | 6B 연결 수명주기 보강→6C 실대상별 승인된 수락 |
| 개인·학과 YouTube 2연결 | `youtube_runtime.py:21`, `:38`, `:59`; 6A 수락서:46 | 원격 매체 bytes 정합 미확보 시 pending/unsupported 유지 | 실제 계정·채널 ID·scope·예약/공개 및 음성/영상 내용 검증 | 6B 권한 확인→6C 실대상 단계별 수락 |
| Instagram·Threads·X·TikTok | `docs/audits/2026-10-31-remaining-channel-entrypoints.md`의 함수·부수효과 표 | 기존 legacy leaf가 있으나 managed adapter/permit 등록 아님. dry도 외부 부수효과 가능 | 채널별 불변 대상/인증·prepare/write/observe 분리·결과 검증·후처리 | 6B 기존 leaf 감사 재사용, 큐 전체를 permit으로 감싸지 않고 단일 write 분리 |
| Facebook | 같은 leaf 감사의 현재 관리 등록 판정; 화면 설계 추가 채널 범위 | 조사 범위 기존 발행 leaf 없음, 설정/실계정 권한 미확인 | 공식 연결 가능 범위와 비용·권한 확인, adapter 및 원격 결과 검증 | 6B 별도 연결/구현 범위. 없는 연결을 등록됨으로 표시하지 않음 |
| 홈페이지·Kakao 및 보조 경로 | 승인 계정 설계:104 | 요청 접수/알림과 공개 SNS 게시 구별 요구 | 각 보조 실행의 실제 부수효과·권한·이력 결속 | 6B caller inventory와 T13 참조 이행에 포함 |
| SNS 도구 사용·관리 및 추가 비용 차단 | `tool_cost_policy.py`, `local_toolkit.py:60`, `:69`, `:78`; 승인 toolkit 설계/계획 | 서버 소유 비용 catalog, paid/credits/unknown 거부, 기본 disabled. vidIQ/Metricool 설치·선호는 웹 실인증 아님 | 미지원/미확인/권한을 사용자에게 정확히 표시, 실서비스 접속은 별도 공식 절차 | toolkit UI 잔여 해결 후 보호 배포. 추가 결제·credit 자동 사용0 유지 |
| 제목·태그·저장 근거·이미지·CSV | `local_toolkit.py:109`, `:139`, `:148`, `:156`, `:192`; 수락서 최종 판정 | 수정9a3607d 집중 Node55/Python32 및 artifact 없는 Node30/HTTP9. 전체 성공/배포 증거 아님. 재리뷰 Important2 | 빈 변환문 선택이 첫 항목으로 처리되는 오류, 이미지 검사 버튼 비활성 해결; 실제320/1280·에러 보존·검사 결과 표시 | 추가 수정 확인→두 반례 회귀→최신 통합/브라우저→배포. 현재 보류 |
| 실제 성과 수집 | `common/operations/metrics.py:28`, `:73`, `:93`; 기존 `common/analytics/collect_*`; `web_metrics.py:55` | 공개 검증 원장의 account/target/remote ID 결속 코드와 주입 collector 경계. 웹은 조회/수동 관측/제안 저장이며 실수집 실행 아님 | 계정별 읽기 권한·비용·할당량·신선도·정의/기간/오류/null/실제0 구별하는 managed collector | 6B 읽기 권한→6C 검증된 단일 게시물 실수집부터 연결 |
| 성과 진실성·기획 순환 | `metrics_store.py:50`, `metrics.py:147`, 저장 제안/연구 규칙; 화면 설계:86 | CSV는 legacy_reported/미배정. `collect_youtube.py:90–98` RSS fallback은 과거값 또는 신규0/공개/길이0 추정과 degraded quota를 반환 | 추정·stale·미수집을 실측0으로 포장하지 않는 normalization, 정의/기간·출처 결속, 원본 제작/대상 실적 귀속, 실제 다음 기획 연결 | 기존 collector 출력 무조건 wrapping 금지. normalization 계약→실수집→기획 제안 provenance 수락 |
| 계정별 폴더·데이터 물리 이행 | 원계획 T13(`:230`), 승인 계정 설계 §11; layout/import/path 감사 도구 | 이행 계획/참조 분석·가져오기 경계가 있어도 실제 파일 이동과 다름 | 코드·config·content/media/history·키·프로필·venv·launchd/외부 caller 참조·호환 링크 방향·USB 분리 수락 | 6D 대상별 manifest/backup/복원 계획→직렬 이동→shadow 비교→소유권 전환 |
| 실제 스케줄 전환·롤백 | 원계획 T15, `docs/runbooks/account-operations-cutover.md`; 6A 수락서:84–95 | 6A 개발 DB 빈 기존테이블 보존·추가테이블/integrity 증거. 비어있지 않은 운영 복원 아님 | 단일 실행 주인·launchd 전환·실제 backup restore·새 remote ID/unknown/quota/receipt 보존 rollback | 6C 대상별 실수락→6D 전환. 과거 DB 덮어쓰기로 공개이력을 잊지 않음 |
| Mac·휴대폰 외부 접속 | 화면 설계:16; `ax-console/app/web_server.py:278`, `:620–631`; `auth.py:93`, `:111`, `:155` | 현재 loopback만 허용, Origin은 http Host와 비교. 로그인 존재만으로 외부 HTTPS 준비 아님 | 보호된 접속 경로·프록시 신뢰·HTTPS Origin/cookie·세션/인증·실제 외부망 Mac/폰·재시작/정지/복구 | 6D 접속 방식 설계는 6B와 독립 준비 가능. 단순0.0.0.0/직접 인터넷 공개 금지 |

## 개발 의존 순서

1. **현재 toolkit 수락:** Important2를 해결한 증거가 생기기 전에는 보호 정적 파일을 덮어쓰거나 배포 완료로 기록하지 않는다. 이후 새 코드 기준 통합·실제 브라우저·DB 보존·자기 소유 서버 coordinated restart를 분리한다.
2. **6B 연결과 단일 효과:** 정확한 registry connection/target/권한과 기존23경로를 입력으로 각 추가 SNS의 prepare/write/observe 계약을 만든다. Facebook 공백과 TikTok 큐의 복합 부수효과를 별도 범위로 유지한다. 기존 leaf 목록 재조사는 하지 않는다.
3. **6C 읽기→제작·검토→실대상:** verified 게시물 하나의 실제 읽기 성과와 신선도 normalization을 먼저 수락할 수 있다. 실제 제작/독립검토/미디어·PDF는 별도 축이며 결과를 특정 동결 버전에 결속한 뒤 단계별 비공개/예약/공개·본문 검증을 거친다. 읽기 성공이 쓰기 권한을 승인하지 않는다.
4. **6D 보호 접속·물리 이행:** 외부 접속 설계는 병렬 준비할 수 있지만 실제 공개/권한 확대는 구체 범위가 필요하다. 데이터·프로필·스케줄 이동은 운영원장/rollback 증거를 갖춘 뒤 직렬로 전환한다.

6B~D 상세 실행 계획은 현재 승인된6A/toolkit 계획으로 대체되지 않는다. 설계·파일별 계획 준비와 실인증/쓰기/스케줄·키·프로필 변경 체크포인트를 구분한다. 전체 목표는 유지되며 이 문서·코드·fixture만으로 운영 완료를 선언하지 않는다.
