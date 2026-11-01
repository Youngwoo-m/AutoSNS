# SNS OAuth 연결 운영 안내

채널·계정의 **공식 OAuth 연결·준비 상태**에서 개인/학과와 공식 방식을 선택한다. 전체 계정은 조회 전용이다. 도구 사용 선호의 활성 값은 실제 계정 인증이나 발행 권한이 아니다.

기본 main은 OAuth 서비스·vault·provider transport를 주입하지 않는다. 10개 방식의 catalog와 준비 차단 상태만 조회하며 연결 POST는 503이다. 앱 등록·OS 자격 저장소·정확한 HTTPS callback·scope·비용 0 증거를 개별 수락하기 전 실제 동의를 시작하지 않는다. 현재 실 OAuth와 발행 준비 완료를 뜻하지 않는다.

명시적으로 구성된 격리 환경의 순서는 계정/방식 → 준비 상태와 요청 scope 확인 → 동의 시도 → callback 임시 수신 → 같은 세션에서 돌아온 시도 직접 선택 → 연결 계속 → 주체/대상 조회 → 표시명과 원격 ID/제안 revision 확인 → 대상 확인이다. callback만으로 token 교환이나 연결 확정이 되지 않는다. 결과 화면은 `/connections/oauth-result`이고 URL query의 code/state/token을 화면에 복사하지 않는다.

연결 확인·갱신·로컬 해제·원격 해지 성공 뒤 현재 연결 목록과 CAS revision을 GET으로 다시 읽는다. POST가 성공하고 GET만 실패하면 성공 상태와 입력을 보존한다. **등록·연결 상태 조회**를 직접 눌러 확인하며 mutation을 자동 재전송하지 않는다. 401/409/503 불확실 요청은 원래 request key와 입력을 보존한다. 409 재검증은 조회 후 별도 클릭으로 새 요청을 제출한다.

로컬 연결 해제는 overlay 사용을 중단한다. 원격 권한 해지·기존 발행 자격 삭제와 다르다. Google의 프로젝트 전체 영향이 미확인이면 원격 해지를 차단한다. 신규 연결 overlay는 로컬 해제 후 목록에서 사라질 수 있다. 완료 연결은 같은 console actor의 새 로그인 세션에서 관리할 수 있지만 미완 시도의 소유권/continue는 원래 세션 결속을 유지한다.

닫기·Escape·바깥 클릭·계정 전환은 host guard를 거쳐 busy 또는 미확인 대기 요청을 보호한다. OAuth drawer의 새로고침은 busy/pending을 버리지 않는다. 브라우저 이탈도 진행 중/대기 요청을 보호한다. 기존 원고 편집/기술사/발행 패널/9개 메뉴는 유지한다.

## 격리 브라우저 검증

부모가 `.superpowers/sdd/2026-11-01-sns-oauth-connections/preview-oauth.py`를 실행한다. 임시 source/workspace/검증 webroot, 가상 비밀번호 `fixture-password`, MemoryVault, fake provider와 명시 test-only callback만 사용한다. 운영 서버·실계정·Keychain·실 provider HTTP를 사용하지 않는다. 화면 상단과 drawer에 가상 검증 경고를 표시한다.

공식 동의 링크는 클릭하지 않는다. 시도 ID를 확인한 뒤 실행 프로세스 stdin에 `{"callback":"시도ID"}`를 보내 가상 callback만 수신한다. 일반 GET은 외부 호출을 하지 않는다. `{"stop":true}`로 종료하면 임시 자료를 정리한다. 이 helper는 제품 main이 아니며 운영 배포 대상으로 복사하지 않는다.

## 적용과 원복

운영 정적 파일은 OAuth manifest의 original/desired actual SHA 및 모든 artifact/module SHA를 먼저 검증하고 전체 검증 뒤 복사한다. 시험 overlay는 OAuth → toolkit → tracked checkout 순서로 선택하며 예전 toolkit artifact를 최신 OAuth 위에 덮지 않는다. ignored manifest가 없어도 tracked checkout으로 시험하며 누락 skip을 사용하지 않는다.

8769의 오프라인 준비 화면 적용과 자료 보존 확인을 완료했다. 전체 suite·320/1280 격리 화면 검증과 실제 서버 비활성 상태 근거는 수락 기록을 따른다. 실제 OAuth lifecycle의 브라우저 수락은 별도 gate다. 원복은 호환 코드와 신규 oauth.sqlite3를 보존한 기능 비활성이다. 새 사용자 자료·unknown receipt를 과거 backup으로 지우지 않는다. 8767/8700/원본R/프로필/launchd/STOP/quota를 변경하지 않는다.


## 중단·재시작 확인

갱신/원격 해지의 operation lease가 남으면 읽기·자격 상태를 불확실로 표시하고 수동 확인을 안내한다. GET은 DB·vault를 변경하거나 외부 작업을 재시도하지 않는다. 로컬 해제와 원격 권한 해지는 다르다.

강제 종료 후 비활성 orphan을 정리하는 명시 recovery는 아직 구현되지 않았다. 실제 인증을 활성화하기 전에 stage journal, workspace/stage 소유 증명, 공통 배타 잠금, 활성·결과불명 참조 보존, 명시 정리와 crash 회귀 검증을 완료해야 한다. 표식 없는 기존 자격은 자동 삭제하지 않는다. 이 항목이 남은 상태에서는 실제 OAuth/Keychain 서비스를 운영 main에 주입하지 않는다.

관리 자격 projection은 operation_lease/명시 비활성 자격을 실행용 catalog에서 제외하도록 보완했다. 실행 어댑터를 연결할 때는 별도로 최신 snapshot/세대·scope·기한·permit 결속 resolver 검증이 필수다. 현재 관리 Connection.enabled는 false이며 실제 실행기로 자동 전달하지 않는다.
