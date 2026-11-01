# OAuth 연결 통합 수락 기록

2026-11-01 Task8 구현자·부모 검증 기록. 이 문서는 실계정 동의·배포·발행 완료 증거가 아니다.

|축|상태|근거/남은 gate|
|---|---|---|
|code_ready|전체 회귀 및 집중 통합 검증 완료, 최종 보완 검토 중|실제 SQLite/MemoryVault/fake provider/HTTP와 JS controller 연결. 부모 Python 1,020개/Node 251개 통과 후 lease·비용 표시 보완은 별도 집중 재검증|
|deployed|오프라인 준비 화면 적용 수락|부모 백업·SHA 검증 후8769 기동, 실제 화면과 DB 보존 확인. 실제 OAuth는 비활성|
|real_oauth_ready|false|앱 등록·실 scope/target·OS 자격 접근·정확한 HTTPS callback·cost0 수락 없음. main 서비스 미주입|
|live_publish_ready|false|연결 동의를 실행 권한으로 승격하지 않음. 6B/6C/6D와 실제 제작·검토·성과·발행·외부접속·이행 필수후속|

통합 반례: 성공한 confirm이 반환한 attempt baseline 0을 lifecycle CAS로 사용하고 연결 목록에서 신규 ID를 찾지 못하던 문제를 실제 HTTP로 RED 재현했다. 성공 뒤 안전한 connections GET을 추가해 현재 revision을 사용한다. refresh/disconnect/revoke도 같은 경계다. POST 성공 뒤 GET 장애는 pending 재생성/자동 retry 대신 성공+명시 조회 안내다.

격리 검증은 신규 null ID의 서버 발급, 명시 proposal 전 미연결, cross-site callback 303과 token 교환0, owned 결과 직접 선택, continue/inspect/confirm, 최신 revision refresh, 로컬 해제 projection, 새 service 재조립과 새 세션의 완료 연결 관리, 미완 타세션 거부, 계정/target/CAS 보존을 확인한다. 기존 HTTP 시험이 401/409/503·CSRF·readonly·cost unknown 외부0을 담당한다. credential expiry/attempt expiry와 관측 scope는 별도 metadata로 표시하며 발행 비활성을 유지한다.

운영 정적6파일 baseline은 `.superpowers/sdd/2026-11-01-sns-oauth-connections/web-baseline.json`, 배포 artifact와 SHA는 같은 경로의 `web-artifacts/manifest.json`에 있다. 원본 파일을 직접 수정하지 않았다. 제품 overlay는 최신 OAuth 우선, 일괄 SHA 검증, original/desired actual 허용, manifest 부재 tracked fallback을 사용한다.

실제 브라우저320/1280·keyboard·multi-tab·401409503 화면 및 screenshot, 전체 Python/Node suite, 실제8769 가용성·DB/자산/registry 보존·원복 gate는 부모가 추가한다. 가상 browser helper는 작성만 했으며 구현자는 실행하지 않았다. 공식 authorize 링크로 외부 이동하지 않고 stdin callback emulation을 사용해야 한다.


## 부모 검증

- 전체 Python: `PYTHONDONTWRITEBYTECODE=1 …/.venv/bin/python -m unittest discover -s tests -t .` — 1,020개, 102.105초, OK. 첫 실행의 `-t .` 누락은 publishers 패키지 import 오류4개였고 올바른 수집 루트로 다시 실행했다. 로그 `/private/tmp/oauth-full-python.log`.
- 전체 Node: `node --test tests/*.test.mjs tests/test_*.mjs` — 251개, 실패·skip0. 로그 `/private/tmp/oauth-full-node.log`.
- Git index의 desired app.js를 `checkout-index`로 깨끗한 임시 경로에 내보내 `.superpowers` 없는 상태에서 OAuth 통합·단위·host focus 39개 PASS. baseline만 가진 임시 복사본에 신규 host 함수가 없던 검토 지적은 이 최종 패키지 검증으로 해소했다.
- 격리 브라우저에서 로그인·채널/계정 drawer·개인 YouTube 가상 동의 준비·Escape 닫기/진입 버튼 포커스 복귀·깨끗한 결과 경로를 확인했다. 실제 공식 동의 링크는 열지 않았다. 320/1280 DOM 폭 overflow0. 이미지: `ax-console/design/previews/oauth-integration-320.png`, `oauth-integration-1280.png`. 브라우저 전체 callback/lifecycle 및 오류별 화면 수락은 아직 미실시이며 HTTP/DOM 시험 근거와 구분한다.
- preview helper의 혼합 쿠키 파싱과 macOS 임시 경로 정규화만 보완했다. 운영 인증이나 전역 보안 정책은 바꾸지 않았다.

## 실인증 전 필수 보완

재시작 orphan 자격 정리는 catch 내부의 참조 보존 처리만 있으며, 강제 종료 이후 자기 namespace의 비활성 orphan을 정리하는 명시 recovery 진입점은 아직 없다. 활성·불명확 참조를 임의 삭제하지 않는다. 이 부분은 실인증/OS backend 수락 이전의 필수 작업이며, 현재 코드 검증을 crash cleanup 완결로 해석하지 않는다. 실제 Keychain·OAuth 서비스는 운영 main에 주입하지 않는다.


최종 보완 후 부모 집중 재검증: service+실제 HTTP 통합 Python **52개 OK**, 화면+HTTP Node **36개 PASS**, 모두 skip0. 중단 lease의 unknown/수동확인·GET DB/vault/provider 부수효과0·중복작업 차단, endpoint 없는 Tistory 비용 unknown을 포함한다. 전체 suite 1,020/251 수치는 이 보완 전 검증과 구분한다.


## 오프라인 화면 적용 수락

최종 독립 검토는 **main 미주입·실인증/발행 비활성 범위 Approved**이며, crash recovery/resolver 필수 후속을 유지한다. Task8 독립 검토도 clean export 최종40개 PASS로 기존 P2 해소를 확인했다. 부모가 auth_status unknown을 추가해 갱신·해지 재기동2회귀를 다시 통과시켰다.

기존8769/8767 PID는 존재하지 않았고8769 리스너가 없음을 확인했다. 전체 관리workspace·기존web를 `ax-console/data/deployment-backups/oauth-20261101T110011Z/`에 백업한 뒤 정적6·신규3 SHA를 선검증하고 app.js를 적용했다. 동일 source/auth/관리workspace와 `AX_LOCAL_TOOLKIT=1`로8769 PID69193/session42834 기동. OAuth service/vault/transport는 mainNone, 원본8700·launchd·STOP·프로필은 변경하지 않았다. 8767은 재기동하지 않았다.

실제 IAB43에서 개인 YouTube **로그인 준비 안 됨 / 비용 미확인 호출 차단 / 동의 시작 disabled**를 확인했다. 화면 `ax-console/design/previews/oauth-deployed-preparation.png`. 실제 동의 버튼 클릭·계정 권한 부여·모델/API/크레딧 소비·원격 게시0. 기존 관리자료2개는 백업 대비 DB logicaldump/schema/user_version/integrity 동일, 비DB SHA 동일이며 OAuth DB 생성0. 백업 before/after.json에 보존 근거를 저장했다.

이 수락은 오프라인 준비 화면 적용까지만 포함한다. 실인증 준비·crash cleanup·실제 실행/성과/외부 접속/물리 이행 등 전체 목표는 완료되지 않았다.


## 후속 자격 projection 경계 보완

복구 계획의 실제 API 대조와 별개로, pending 갱신·해지 lease가 남은 자격이 실행용 catalog/projected registry에 들어가는 경계를 수정했다. durable connection row·lease·자격 ref는 보존하되 실행용 credential_refs와 catalog에서는 제외한다. connected이면서 명시 credential_status가 active가 아닌 경우도 제외한다. 기존 authorization=None 기록의 조회 호환은 유지하며 이것을 실제 실행 수락으로 승격하지 않는다.

기존 연결은 credential/profile fallback 없이 unknown 진단으로, 새 managed 연결도 자격 없는 unknown 진단으로 남아 수동 확인·로컬 해제 경로를 유지한다. disconnected/revoked/reauth_required는 각 상태를 그대로 유지한다. 원본 registry·unmanaged 연결·DB는 변경하지 않는다.

검증: 임시SQLite의 refresh/revoke lease2반례 RED 확인 후 GREEN, explicit unknown/pending/stored/reauth_required catalog4반례는 baseline module에서 RED 확인, 신규 진단 연결과 inactive metadata 회귀도 검증했다. 부모 managed/service **62개 OK**, HTTP/실제 service 통합 **23개 OK**, skip0. 독립 검토에서 inactive 상태를 unknown으로 덮던 중간 회귀를 찾아 수정했으며 해당 회귀 독립 시험1개 PASS. 같은 시험 수를 합산하지 않는다. 로그 `/private/tmp/oauth-credential-boundary.log`, `/private/tmp/oauth-boundary-http.log`.

이 보완은 코드에 반영했으며 현재8769 PID69193은 기존 mainNone 오프라인 모드로 계속 실행 중이다. 서버 재기동·실 Keychain/계정/API/발행0. 이 변경을 실제 OAuth runtime 조립 또는 최신 세대·scope·permit 결속 resolver 완료로 해석하지 않는다. [runtime 경계 감사](2026-11-01-oauth-runtime-credential-boundary.md), [복구 실행 전 계획](../superpowers/plans/2026-11-01-oauth-crash-recovery.md), [다음 실제 연결 산출물](2026-11-01-sns-next-deliverables.md)을 따른다.


## 동일 snapshot의 자격 세대·연결 소유 결속

후속 코드에서는 catalog와 registry 각 활성 행 양쪽에 동일 validator를 적용했다. canonical key·map ID·connection ID·account/platform/provider·현재 CredentialRef·정확한 int generation이 모두 일치해야 한다. 현재 catalog 항목 누락도 고정 StoreError로 거절한다. 한 연결의 유효 catalog를 다른 개인/학과 연결이 빌리거나, generation2 key 아래 generation1 ref를 넣는 조합을 차단한다. 실제 vault/provider 조회·원본 registry/DB mutation은 없다.

RED: stale/key/현재ref 불일치4개와 2행 alias3개를 순수/임시SQLite 시험으로 확인했다. 최종 부모 managed/service **64개 OK**, HTTP+실제 service integration **23개 OK**, skip0. 기존 lease/nonactive 차단, 정식 refresh 후 generation2만 사용, 원본 registry 보존을 포함한다. 독립 검토는 16개 거절 조합이 모두 credential_owner_mismatch이고 정상generation2가 성공함을 별도 probe로 확인했다. 로그 `/private/tmp/oauth-generation-boundary.log`, `/private/tmp/oauth-generation-http.log`, [독립 검토](2026-11-01-oauth-generation-boundary.md).

이것은 전달된 snapshot 내부 정합성 검증이다. 자격 사용 직전 최신 DB 재검증, runtime action/permit CAS, 실제 OAuth 공급과 publisher child 조립은 아직 구현되지 않았으며 [조립 계약 조사](2026-11-01-oauth-runtime-assembly-contract.md)에 구분했다. 실제 성과의 수집 요청 멱등·원격 ID/목적지 결속·누락값 보존과 다음 기획 연결은 [성과 접합부 조사](2026-11-01-youtube-metrics-binding-contract.md)에 정리했다. 두 조사 문서는 구현/설계 승인/실수집 증거가 아니다. 현재 복구 실행 계획 검토 질문은 답변 대기이며 복구 신규 구현·실계정/발행은 시작하지 않았다.
