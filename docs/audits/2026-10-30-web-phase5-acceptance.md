# 운영 웹 5단계 수락 기록

2026-10-30. 사용자 승인 범위는 저장 성과 조회·근거 기반 기획제안 저장·계정별 경로 이행 준비다. 실제 API 수집·모델 호출·발행·운영 파일 이동은 실행하지 않는다. 현재 코드/화면 검증을 마쳤으며 최종 결합 검토와 실제 관리 개발 서버 반영은 아래 별도 확인 항목으로 남아 있다.

## 구현과 보존 경계

- 관리 운영 원장 v3는 유지한다. 별도 `metrics.sqlite3` schema1에 불변 관측·제안·가져오기 receipt를 저장한다. 생성자/GET는 초기화하지 않고 startup의 명시 initialize만 DB를 만든다.
- 실제0·error·unsupported·미수집·legacy_reported를 구분한다. 관측/수집/파일수정 시각은 별도이고, legacy의 시각 미확인을 mtime으로 채우지 않는다. 누적값을 기간 발생량으로 표시하지 않는다.
- 서버 수집 계약은 실제 RuntimeStore의 검증 이벤트·공개 상태·게시ID·대상/등록부를 재대조한다. 버전/manifest는 서버 source에 결합하고 원시 provider 응답은 공개하지 않는다. 실제 수집기는 미등록이며 collection_enabled=false다.
- 관련 계정 조회는 owner OR destination, 채널 집계는 실제 대상에 한 번, 제작예산 근거는 production_id당 소유 계정에 한 번 귀속한다. 예산 예약/정산을 실제 과금으로 추정하지 않아 금액·통화 미확인은 null이다.
- 최신 수집 오류/미등록은 같은 물리 게시의 이전 성공 근거와 연결하고 그 scope를 표시한다. 이전 성공값은 보존하지만 최신 수집 성공으로 위장하지 않는다.
- importer는9개 allowlist JSON만 제한 읽는다. 검색어·site/page·YouTube v 등 원본 식별 차원을 보존하고 query로 식별이 불명확한 행은 원본 위치를 유지한다. 명시 대상을 확인한 legacy는 destination만 귀속하고 원본 owner는 추정하지 않는다.
- POST 가져오기는 최신 미리보기를 재검증한다. receipt와 관측/결과를 원자 저장해 응답 유실·DB 재개방·원본 변경 뒤 같은 요청이 원래 결과를 반환한다. 다른 digest로 같은 key를 쓰면409다.
- 기획제안은 별도 draft다. 기존 ContentStore 원본 생성·승인·실행을 호출하지 않는다. 성과에서 저장한 수동 제안을 기획 보드의 AI 기록과 별도 표시한다.
- 경로 도구는 명시 allowlist의 정적 코드/alias/caller/환경 기호 참조만 보고한다. unknown 계정 fallback과 실제 이동은 없고 physical_migration_ready=false다. 공용 운영 DB·기존 .venv·토큰·로그인 폴더를 이동하지 않는다.

## 자동 시험

- S1: 신규23개. verified 성공의 관측 시각 누락 모델/append/import 거부 및 import 선행행 롤백, 실제0·불변 모델·동시 키·별도 제안·원장v3 불변을 확인했다.
- S2: 최초17개에서 검색어/영상/동적page 식별과 실제 Naver enum/target 접합 회귀를 추가했다. 최종 관련49개가 통과했다. 실제 원본은 읽기 전용 대조만 하고 저장하지 않았다.
- S3: 서비스20개. 실제 RuntimeStore 임시 원장 검증과 DB 바이트 불변, 물리 게시 중복 제거, 실제 collector 예외/None의 실패 연결 및 회복·타게시 격리를 확인했다.
- S4: localhost HTTP/receipt/순수경계13개 통과(3.232초). 인증·Origin·엄격 body/query·무쓰기 GET·미확인 계정·재전송/동시 receipt·미리보기 ID의 제안 거부·원본 생성0을 확인했다.
- S5:17개 및 실제 원본 allowlist 코드29개/alias13개/정적관계49개 조사. 두 관측의 파일 hash/mtime이 같고 subprocess/network guard 아래 외부 호출0이었다. 운영 전체 파일/호출자를 전수 조사한 것은 아니다.
- S6/S7: 성과 모듈23개와 app 포커스 연결3개를 포함한 전체 Node100개 통과(472.201429ms), 실패/skip0. 현재 app 통합은 HEAD/임시 QA webroot/아티팩트 bytes가 같고 실행 중8769 보호를 위해 working app은 적용 대기다.
- 전체 Python: `python3 -m unittest discover -s tests -p 'test_*.py'` **469개 통과**,47.243초, 실패/skip/warning0. 코드 기준01ca788. 로그 `/private/tmp/autosns-phase5-final-python.log`.

## 실제 원본의 읽기 전용 대조

원본 `common/analytics/snapshots/parts`의9개 파일을 새 load/build로 두 번 읽었다. 파일 모두ok, 가져오기 후보978행·오류0, 등록 대상과 일치한 학과132행·귀속 미확인846행이었다. 원본 소유는978행 모두 미확인이다. 등록 대상이 부족한 자료에 계정을 추정해 넣지 않았다.

최초 대조의 전부 미귀속 결과에서 Naver `naver`/실제 등록부 `naver_blog` 및 target 표현 차이를 발견해 수정·독립 검토했다. 이후132행이 등록된 학과 대상으로 연결됐다. 전후9개 파일 내용 hash/mtime은 같고 같은 입력의 preview digest도 같았다. 소켓/subprocess guard 아래 외부 호출0, 실제 import는 실행하지 않았다. 근거 `/private/tmp/autosns-phase5-live-legacy-preview.json`.

이978행은 과거 통계/게시목록/검색·색인 근거이며 오늘 공개 실적이나 현재 verified 관측 수가 아니다.

## 실제 브라우저 수락

임시8768과 전용 `ax_phase5_fixture_session` 쿠키를 사용했다. 실제 계정·원본·인증 자료는 연결하지 않았다. 화면의 `[5단계 검증 자료]`는 fixture이며 실제 채널 실적이 아니다.

1. 1280px에서 실제0·조회 오류·미지원·과거 보고·계정 귀속·지원 상태를 구분했다. 필터 값 변경 뒤 activeElement가 해당SELECT로 유지됐다.
2. 근거 선택·개인 계정·제목/메모를 입력하고 재조회해 선택/입력이 보존됐다. 명시 저장 후 제안1개가 성과와 기획 보드에 나타났고 원본/승인은 생성되지 않았다.
3. 기획 메뉴 진입 뒤 자동 refresh가 제목 포커스를 BODY로 잃는 문제를 실제 재현해 수정했다. 새 아티팩트 reload 후 자동조회가 끝나도 activeElement=H1/page-title을 확인했다. 입력 등 다른 포커스는 빼앗지 않는 회귀시험을 추가했다.
4. 미리보기 후 임시 원본만 변경하자409가 발생하면서 미리보기·요청이 유지됐다. 명시 요청 버리기→새 미리보기→저장 후 과거 보고2개만 추가됐다.
5. 개인 보기3개, 학과 보기4개 관측으로 교차 원본이 양쪽에서 발견되고 다른 대상/미귀속 기록은 필터에 맞게 제외됐다.
6. 320px에서 viewport/body/html 폭 모두320, 긴 식별자·관측 시각·출처를 연 상세에서도 전체 가로 넘침0이었다. Escape는 상세를 닫고 SUMMARY에 포커스를 돌려줬다. 임시 viewport override는 검증 후 해제했다.
7. 브라우저 console warn/error0. QA DB는 관측6·제안1·가져오기 receipt1, 운영 원본/실행/발행 승인 각0이다. 임시 source STOP은 부재다.

이미지: `ax-console/design/previews/phase5-metrics-desktop.jpg`, `phase5-proposal-desktop.jpg`, `phase5-metrics-mobile.jpg`. DB 근거 `/private/tmp/autosns-phase5-browser-db-proof.json`.

## 독립 검토와 최종 반영

S1/S3/S5 및 S6 모듈은 지적 수정 뒤 한정 재검토를 통과했다. S2는 원본 식별 손실을 두 차례 보완한 뒤 통과했고, 실제 Naver 접합도 별도 검토를 통과했다. S4 코드 검토와 S7 제목 포커스 수정 재검토도 통과했다. 원래 지적을 현재 초록 시험으로 덮어쓰지 않았으며 각 회귀 반례를 남겼다.

최종 전체 결합 검토: 대기. 실제8769 백업/반영/보존 확인: 대기. 실제 운영 코드/launchd/8700/큐/키/프로필 변경은 이번 범위에 없다.

## 남은 전체 목표

실제 채널별 발행/조회 어댑터와 공식 인증·SNS 도구 연결, 발행 권한 없는 제작기·실제 독립 검산/출처 검토·구독 전용 격리, 모든 기존 진입점/스케줄의 단일 실행 주인 전환, 원격 예약/공개/내용 검증, 실제 API 성과 수집·계정 귀속 보완, 안전한 물리 폴더 이행, 보호된 Mac/휴대폰 외부 접속·롤백은 후속 필수 작업이다. 이번 로컬 성과·이행 준비 수락으로 전체 목표를 완료 처리하지 않는다.

## 판단 기록과 변경 비용

| 순서 | 판단 | 틀렸을 때의 비용·남은 연결 |
|---|---|---|
| 1 | 사용자 지정 병렬 작업과 파일 소유 분리 | 계약 차이는 통합 재작업으로 보완 |
| 2 | MetricsStore(root).initialize() 규약 사용 | 호출부 변경 시 관련 소비자를 함께 수정 |
| 3 | 성과 별도 DB와 원본과 다른 제안 draft | 자동 원본 전환은 후속 트랜잭션 설계 필요 |
| 4 | 관련 계정은 owner OR destination, 실적은 대상·제작비는 소유 | 잘못 합산하면 교차 게시 누락/중복이므로 시험으로 고정 |
| 5 | UI 모듈 검토와 실제 통합·브라우저 수락 분리 | 모듈 통과만으로 전체 UI 완료 처리 불가 |
| 6 | legacy 채널은 대상만 증명, 원본 소유 추정 금지 | 강한 원본 매핑 전 미귀속 자료가 남음 |
| 7 | quota 제작예산과 실제 지출 구분 | 공급자별 실과금 관측은 계속 구현해야 함 |
| 8 | 가져오기 영속 receipt를 저장소 원자 경계에 추가 | 새 테이블/초기화/동시성 검증이 추가됨 |
| 9 | S2 재검토 중 S4의 독립 receipt/auth 작업 병렬 시작 | importer 계약 변경 시 끝점 시험 조정 필요, 실제 결합은 게이트 뒤 수락 |
| 10 | preview ID는 표시 전용 | 저장/기획 근거로 쓰면 안 되며 API가 거부해야 함 |
| 11 | 실행 중 app은 보존하고 git/임시 QA에 새 통합 기록 | 최종 HEAD 재적용·서버 갱신·해시 대조를 빠뜨리면 실제 UI는 구버전 |
