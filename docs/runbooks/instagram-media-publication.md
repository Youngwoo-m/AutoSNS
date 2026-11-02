# Instagram 미디어 게시 연결

Instagram의 관리 게시 연결은 기존 제작물과 승인된 채널별 원고를 사용한다. 개인·학과는 AutoSNS의 소유 계정 구분이며, 실제 Instagram 프로페셔널 계정·권한을 별도로 확인해야 한다. 기존 브라우저 자동 작업을 새 경로로 전환하거나 다시 실행하지 않는다.

## 현재 구현 범위

순수 배포 준비·Facebook Login 계열 API client·공개 미디어 전달 경계, 구성 검토·화면·다단계 전송 원장과 공통 adapter/bridge·영수증 기반 검증/조회 복구를 연결했다. 기본 외부 transport·공개 파일 공급자·계정 권한 공급자는 없고 실제 로그인·파일 공개·API 호출·발행을 실행하지 않는다. native bootstrap은 명시적으로 차단하며 실제 최종 승인/STOP/permit를 조합하는 공급자 기동과 공개 probe의 실계정 수락은 아직 남아 있다.

고정 콘텐츠 버전의 `options.instagram`에서 `format`과 순서 있는 `asset_ids`를 명시한다. 단일 이미지에는 JPEG 하나, REELS에는 MP4 하나, 캐러셀에는 2~10개 JPEG/MP4를 선택한다. 이는 이번 구현의 지원 범위다. PNG·WebP를 자동 JPEG로 바꾸거나 누락 자산을 빼고 계속 진행하지 않는다. 변환이 필요하면 새 자산·새 해시를 생성하고 그 결과를 검토해야 한다. 2200자 캡션 준비 상한은 내부 정책이며 실제 앱/API의 모든 수락 조건을 증명하지 않는다.

원고는 해당 배포 계정의 고유 Instagram 변형 또는 원본을 그대로 사용한다. 중복 변형·다른 버전·다른 소유자·선택 자산 중복을 거부한다. 준비 단계는 자산 메타데이터만 다루며 실제 바이트 검증이나 게시 승인을 대신하지 않는다.

## 미디어 주소와 공개 노출

관리 웹의 자산 조회는 로그인한 로컬 접속용이다. `127.0.0.1` 주소와 인증 쿠키가 필요한 URL은 Meta 서버가 가져갈 공개 주소가 아니다. 자산 ID를 임의 URL로 바꾸거나 임시 공개 폴더에 자동 복사하지 않는다.

신뢰된 서버의 공개 전달 공급자는 다음을 결속해야 한다.

- 승인 문맥 해시와 콘텐츠 소유자·배포 계정·연결·대상 ID·불변 콘텐츠 버전
- 선택된 자산의 순서·ID·SHA256·크기·MIME과 실제 읽은 바이트
- 공급자의 전달 영수증과 동일 바이트 증명·허용된 HTTPS 호스트·만료 시각

전체 선택 자산을 검증하기 전에는 첫 자산도 전달하지 않는다. 최종 승인/STOP/실행 허용을 검사하는 서버 guard가 없거나 실패하면 전달하지 않는다. URL을 본문이나 사용자 입력에서 받아 공급자 확인을 건너뛰지 않는다. 실제 공급자 구현·비용·공개 노출 동의·만료 시 파일 회수와 서버 측 파일 접근 검증은 후속 수락 범위다. 가짜 공급자의 영수증은 실제 공개 접근의 증거가 아니다.

`InstagramMediaSourceFactory(media_loader, stager=..., approval_guard=..., allowed_hosts=..., clock=...)`는 생성 시 I/O가 없다. `prepare(ctx,prepared)`가 같은 준비 계약을 다시 검증하고, 전체 자산을 읽은 뒤 각 전달 직전 guard를 확인한다. stager 요청에는 본문·토큰 없이 승인 문맥 해시와 자산/대상 결속만 넣는다. 반환은 private repr의 불변 `InstagramHostedMedia` 목록이며, 공급자 영수증의 URL·동일 SHA/크기·5분 초과~24시간 만료를 검증한다. 최종 게시 서비스는 Meta에 URL을 보내기 직전에도 만료·현행 승인을 다시 확인해야 한다.

부분 전달 후 공급자 실패의 영속 복구·잔여 파일 회수와 각 자산 전달의 중단 기록은 아직 게시/미디어 원장에 연결되지 않았다. 이 factory만으로 실제 공개 호스팅을 활성화하지 않는다. 최소 JPEG/MP4 서명 검사는 실제 픽셀·코덱·길이·크롭 품질 수락을 대신하지 않는다.

기존 `dept/naver-blog-auto/geoai_assets.py` 경로는 공개 저장소 생성·자동 이미지 변환·자격 fallback·실패 파일 건너뛰기가 있어 새 승인 경계에 직접 연결하지 않는다. 기존 경로 자체는 보존한다.

## 공식 API 경로 구분

Facebook Login 기반 Instagram Graph 경로는 `graph.facebook.com`과 연결된 Facebook Page/Instagram 계정 관계 및 해당 scope를 사용한다. Instagram Login 경로는 `graph.instagram.com`과 `instagram_business_*` scope를 사용한다. 토큰·제공자·호스트를 묵시적으로 전환하지 않는다.

현재 client 기반은 명시 API 버전의 Facebook Login 계약만 구현하며 기본 transport는 미등록이다. 계정 ID/사용자 이름 관측이 프로페셔널 계정·Page 위임·게시 권한의 증명은 아니다. 이미지/REELS/캐러셀은 컨테이너 생성 후 상태 확인과 별도 `media_publish`를 거친다. 자동 상태 폴링이나 POST 재시도는 하지 않는다. 직접 resumable 영상 업로드의 실제 header/바이트 전송·재개 계약과 Instagram Login 지원은 계속 필수 후속 작업이다.

## 검토·공개 검증·후속 실행

기존 이미지 권리/시각 확인과 제작 영상 검토는 보존한다. 새 `InstagramReviewStore`는 선택 자산·순서·형식·캡션·대상·불변 원고의 15개 준비 필드 해시별 수동 확인을 별도 append-only 원장에 저장한다. 권리·시각·캡션·구성 네 항목과 영상이 포함된 경우 오디오 확인을 요구한다. 철회는 새 기록이고 다른 버전·대상·순서의 검토는 승계하지 않는다.

`InstagramReviewService.get/record`는 실제 저장된 계획과 등록부, 최신 원고 버전, 선택된 자산 바이트/크기/SHA를 재확인한다. 클라이언트가 owner·target·actor·임의 원고를 입력해 검토를 생성할 수 없다. `authorize(ctx,prepared)`는 실제 PublicationContext의 현행 수동 검토만 검사하며, 독립 원고 검토·공통 계획 승인·최종 발행 승인·STOP·일회성 permit를 대신하지 않는다.

계획 준비에는 인증 없는 `InstagramPreparationContext`를 사용한다. 실제 대상 ID가 미확인이어도 명시 미디어 선택 계획은 저장할 수 있지만 승인/최종 검토는 차단한다. 기존 `plan` 능력의 선택 메타데이터이며 실제 게시 능력을 추가하지 않는다. 저장된 계획은 현재 등록부의 공개 대상 ID를 표시한다. API GET/POST `/api/v2/deliveries/{id}/instagram-review`는 인증·동일 출처·엄격한 필드/CAS를 요구하며, GET는 저장소를 생성하지 않는다.

배포 화면에서 형식과 순서 있는 자산 ID를 명시 선택하고, 저장된 Instagram 계획의 접힌 최종 검토 패널을 펼쳐 캡션·순서·불변 자산 링크를 확인한다. 체크·메모와 명시 저장/철회만 변경 요청을 보낸다. 충돌·시간 초과·불일치 응답에서는 초안을 보존하며 미저장 검토나 처리 중 요청이 있으면 부모 원고 변경과 계획 전환을 막는다. 검토 저장은 실제 게시나 파일 공개가 아니다.

`InstagramJournal`은 명시 초기화하는 별도 private DB에서 staging·자식/부모 컨테이너·publish의 시작과 결과를 CAS·OS 잠금으로 영속 기록한다. `InstagramServices.submit(ctx,prepared,target)`는 기본 공급자/권한/검토 guard가 없으면 차단한다. 신뢰된 서버의 신선한 프로페셔널 계정·게시 권한 증명, 현재 수동 검토, 인증/URL 만료, 매 쓰기 직전 STOP/permit hook을 확인한다. 훅 뒤 검토도 다시 확인한다.

알려진 ready 컨테이너의 `IN_PROGRESS`는 새 컨테이너를 만들지 않고 다음 명시 호출에서 기존 ID만 확인한다. 응답 유실·중단된 started·unknown 상태는 POST를 반복하지 않는다. factory 진입 전 확정 차단은 `staging_blocked`로 기록해 같은 문맥의 명시 재개만 허용한다. factory 진입 후 불명확한 실패는 다시 stage하지 않는다. publish ID를 받은 뒤 저장 실패해도 검증된 ID를 unknown 결과에 보존한다. 원격 게시 ID를 받았다는 사실만으로 공개 검증을 완료하지 않는다.

현재 private 전달 영수증은 최초 context_hash에 묶이므로 인증/permit/run 문맥이 바뀐 미완료 시도의 자동 재사용은 차단된다. 안전한 새 문맥 재승인·이미 처리된 컨테이너 재결속과 운영 복구 UI는 후속 필수 작업이다. 실제 runtime/adapter는 이 제약을 숨기거나 재POST로 우회하면 안 된다.

전송 성공 시 `instagram_upload_receipt_v1`은 문맥 해시·계정/대상·원고 버전/manifest·실제 선택 자산 메타데이터·캡션 해시·형식·부모/자식 컨테이너 ID·최종 게시 ID를 보존한다. 원격 미디어 해시를 합성하지 않으며 공개 미디어의 사설 전달 주소/영수증 ID는 parent 증거에 복사하지 않는다. 이 영수증이 없는 기존 시도를 로컬 원고만으로 완료 처리하지 않는다.

캐러셀의 초기 `published_children=None`은 미확정 상태다. 실제 현재 권한의 소유자 API에서 원격 캡션·형식·개수·유형 순서가 원본 준비물과 맞을 때만 첫 자식 ID 순서를 private 원장에 CAS 고정한다. 잘못되거나 부분적인 첫 관측은 영구 고정하지 않는다. 이미 고정된 순서는 이후 조회 결과로 덮어쓰지 않는다. 조회 실패 뒤에도 새 POST를 하지 않고 정상 읽기에서만 핀을 확정한다. known ID와 유효한 원본 영수증이 있는 unknown도 로컬 관측 핀만 저장하고 unknown 상태를 유지한다.

`InstagramServices.observe`는 실제 원격 캡션을 해시하고 원격 미디어 해시는 `None`으로 둔다. 별도 공개 probe의 정확한 게시 ID·대상·캡션 해시·URL·형식·자식 순서와 신선한 시각이 일치할 때만 public으로 관측한다. 기본 probe가 없으면 unknown이다. 실제 owner API 관측이나 permalink 존재만으로 공개 검증 완료를 만들지 않는다.

`instagram_upload_identity`는 실제 시작된 attempt의 저장된 원본 영수증을 승인 snapshot과 다시 대조한다. 초기 핀이 미확정이면 private 원장이 반환한 최종 영수증이 자식 핀 외 모든 필드에서 초기 영수증과 같아야 한다. 원격 캡션·형식·시각·현재 자식 ID 순서·실제 공개 URL이 일치해야 최종 완료되며, 최종 증거에 `verification_method=instagram_upload_receipt_and_public_observation`, `media_sha256=None`을 남긴다. Meta가 변환한 이미지/영상의 해시를 로컬 원본 SHA256이라고 주장하지 않는다.

공통 factory는 활성·실제 대상이 있는 고정 개인/학과 연결만 조립한다. 기본 catalog는 비어 있고 실제 child bootstrap은 미설정으로 거부한다. BridgeHost는 기존 일회성 permit·부모 잠금 증명·계정별 자격·STOP 검사를 유지하며 새 managed OAuth의 publication 차단을 해제하지 않는다. 미디어 공급자 내부의 각 공개 전달 guard에도 실제 STOP/permit/최종 검토를 결합한 수락이 필요하다.

공통 조회 복구는 원본 전달 영수증이 있는 알려진 ID만 일치시킨다. unknown 시도의 읽기 증거를 `link_existing`으로 원장에 결속한 뒤 별도 공개 검증을 진행하며, 목록 스캔·텍스트 유사성이나 프로세스 종료만으로 게시 존재/부재를 판단하지 않는다. 원장 자체 손상·게시 ID의 이중 저장 실패·새 인증 문맥 재결속은 추가 명시 복구가 필요하며 자동 재게시로 우회하지 않는다.

기존 교차 게시 23개 중 `news.instagram`, `career.instagram`, `disaster.instagram`은 모두 학과 YouTube→학과 Instagram의 `legacy` 실행 소유 경로다. 새 구현 때문에 이를 `managed`로 전환하거나 동일 콘텐츠를 중복 게시하지 않는다. 첫 댓글·캡션 보완도 별도 후처리 승인과 원장 작업으로 남긴다.

공식 계약 근거: [Meta IGUser SDK](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/iguser.py), [Meta IGMedia SDK](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/igmedia.py), [공식 Instagram Platform API Postman collection](https://github.com/fbsamples/messenger-platform-samples/blob/main/postman/instagram-platform-api.postman_collection.json). 현재 앱·버전·권한·비용 및 실제 네트워크 수락은 별도로 확인해야 한다.
