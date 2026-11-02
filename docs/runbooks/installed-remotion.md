# 설치된 Remotion 고정 등록

`InstalledRemotion`은 이 저장소의 `common/remotion-shorts`와 `public/Pretendard-Bold.otf`만 대상으로 한다. 생성자는 파일·명령·네트워크에 접근하지 않는다. 서버가 지정한 템플릿과 글꼴 해시를 받아 명시 `verify()`에서 원본·의존성을 읽는다.

검사는 SurveyShort 진입점·구성·잠금 파일·글꼴 식별과 해시, 설치된 Remotion/CLI 버전, 작업공간 내부 CLI 링크를 확인한다. 임의 경로·명령·외부 링크는 받지 않는다. 실패 응답에는 절대 경로나 파일 원문을 넣지 않는다.

검사를 통과한 뒤 `create_registration`에 실제 자산 재사용 승인자·실측기·영상 검사기를 전달한다. 제작기 factory는 다시 같은 해시를 확인한 후 기존 `RemotionVideoRunner`만 만든다. 실제 호출 시에도 기존 runner가 템플릿·글꼴 해시를 다시 확인하고 `npx --no-install` 경로를 사용한다. 등록이나 검사 자체는 영상 렌더가 아니다.

검토 보류가 필요하면 신뢰된 서버 코드가 `defer_video_review=True`를 명시한다. 파일·규격·재사용 승인을 생략하지 않고 사람 확인만 대기한다. 웹의 임의 완료 플래그를 승인자나 검사기로 바꾸지 않는다.

2026-11-02 작업공간에 누락된 의존성을 기존 `package-lock.json`으로 복원했다. 잠금 파일은 npm 공식 저장소만 참조했으며 `npm ci --ignore-scripts --no-audit --no-fund`와 별도 캐시·빈 사용자 설정을 사용했다. 사용자 npm 인증이나 설치 스크립트를 실행하지 않았다. 추가 SaaS·유료 API 호출과 실제 영상 렌더도 하지 않았다.

읽기 전용 검사 결과는 `docs/audits/2026-11-02-remotion-readiness.json`에 있다. `verified=true`는 고정 파일·설치 버전 검사를 뜻하며 실제 영상 품질 검증이나 운영 활성화 승인을 뜻하지 않는다. 8769의 영상 제작 서비스는 계속 비활성이다.
