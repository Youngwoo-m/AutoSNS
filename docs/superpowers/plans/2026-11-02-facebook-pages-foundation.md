# Facebook Pages 발행 연결 구현 계획

**목표:** 개인·학과별 Facebook 페이지 발행을 기존 공통 승인·원장 경로에 연결한다. 개인 타임라인 게시를 지원으로 표시하지 않는다.

**설계 근거:** `docs/superpowers/specs/2026-10-31-sns-oauth-connections-design.md`의 Pages 대상 원칙과 기존 Threads의 순수 준비/명시 bridge 경계를 따른다. 기본 비활성, 실제 인증·발행 및 비용 정책은 그대로 유지한다.

## 구현 순서

- [x] `common/publishers/facebook_payloads.py`: 승인된 스냅샷의 계정·버전·manifest·게시 대상과 Facebook 변형을 결속한다. 텍스트 전용은 명시 승인된 경우만 허용하고 원문을 자르거나 자산을 변경하지 않는다. 개인/학과 교차 게시를 보존한다. 단위 시험으로 변형 중복·다른 계정·UTF-8·옵션 불일치를 거부하는지 확인한다.
- [x] `common/publishers/facebook_client.py`: 명시 API 버전과 주입 transport를 통해 Page identity, feed 텍스트 게시, 알려진 post 조회만 지원한다. 생성자·기본 호출은 외부 I/O가 없다. Bearer 헤더 외 토큰 전달, 임의 endpoint, 자동 재시도·오류 원문 노출을 허용하지 않는다. 공식 계약 근거와 미검증 항목을 문서화하고 가짜 transport 시험을 실행한다.
- [x] `facebook_services.py`, `facebook.py`, `facebook_runtime.py`: 원격 POST 전 영속 기록, 불명확한 응답의 재게시 방지, 정확한 페이지 대상/본문/게시 ID 검증, BridgeHost permit과 매 쓰기 직전 STOP 확인을 연결한다. 실제 native bootstrap은 공식 앱·권한·비용·페이지 tasks·공개 확인 수락 전까지 차단한다.
- [x] 공통 ledger/verification와 화면: 서버의 명시 text_only 능력이 있는 Facebook 연결만 선택할 수 있게 하며, 원본 자산 제외를 승인 화면에 표시한다. 공개 URL과 실제 공개 관측 없이는 verified로 승격하지 않는다. 준비 상태는 구현 사실과 실계정 성공을 구분한다.
- [x] 통합 시험 후 실제 앱 등록·인증·게시·공개 검증·성과·외부 접속 등 전체 목표의 남은 범위를 갱신한다. 이번 기반 코드만으로 채널 발행 완료를 주장하지 않는다.

## 검증 초점

API 버전이나 플랫폼 제한을 추측하여 자동 선택하지 않는다. 다른 페이지의 응답, 중복 JSON 키, 비정상 숫자·문자열, 토큰이 섞인 오류, 불명확한 POST 결과를 안전하게 구분한다. HTTP/API 시험은 가짜 transport로만 수행한다. 기존 운영 자료·교차 게시 규칙·비활성 스케줄은 수정하지 않는다.

OAuth 로그인 주체 ID와 Page ID, 실제 Page access token의 대상은 별개다. `/me`의 숫자 ID만으로 Page 유형이나 게시 권한을 증명하지 않는다. 후속 실연결은 명시 페이지 선택·membership/tasks·사용자 토큰에서 페이지 토큰으로 위임된 증거가 필요하며 현재 managed credential 모델만으로 이를 충족했다고 간주하지 않는다. 자동 첫 페이지 선택은 금지한다.

기존 RuntimeStore의 one-shot permit과 request_started, unresolved 차단은 같은 delivery의 자동 재게시를 이미 방지한다. 후속 leaf journal은 이를 대체하지 않는다. POST 성공 뒤 child→부모 응답 유실 전에 알려진 원격 ID를 보존하고, 새 delivery/명시 복구 경로에서도 같은 논리 intent를 재사용·차단하는 추가 경계로 설계한다.

원격 본문에만 의존해 media=[]를 만들지 않는다. client는 공식 PagePost.get_attachments edge를 별도로 관측하며, 서비스는 첨부 관측이 명시적으로 빈 목록일 때만 텍스트 전용 공개 증거를 만든다. 누락·첨부 존재·페이지네이션 다음 항목이 있는 빈 응답은 완료 증거가 아니다. 링크 미리보기/미디어 게시와 query형 permalink 지원은 별도 수락 범위로 유지한다.

## 검증 기록

발행 모듈 전체 250개, 공통 운영 모듈 985개(4개 건너뜀), 별도 계획 원장 15개, 웹/배포 화면 364개가 오류 없이 완료됐다. 운영 모듈 discovery는 상대 import를 보존하도록 `-t .`를 사용한다. 웹 시험의 임시 HTTP fixture는 localhost bind가 필요한 실행 권한에서 검증했으며 실제 로그인은 하지 않았다. 가짜 HTTP 통합 5개는 실제 client·서비스·leaf journal·handler·adapter·RuntimeStore·공개 검증을 연결하지만 InlineBridge를 사용하므로 실제 child permit 통신의 수락 증거는 아니다.

8769 관리 웹을 기존 환경으로 재기동했고 로그인 페이지 HTTP 200, 무인증 준비 현황 API HTTP 401을 확인했다. 실제 제작/인증/발행 서비스는 추가 활성화하지 않았다. 코드 백업은 `ax-console/data/deployment-backups/facebook-runtime-1877807.tar`에 보관했다. 기존 연결 11개·교차 규칙 23개·enabled 연결 0개와 Facebook 실제 등록 0개를 다시 확인했다.
