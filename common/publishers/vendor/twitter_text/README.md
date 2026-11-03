# 고정 X 텍스트 검사기

`twitter-text-parser==3.0.0` wheel의 순수 Python 포트다. 버전·원본 SHA256은 `PROVENANCE.json`에 기록했다. 전역 설치나 의존성 다운로드는 실행하지 않는다.

로컬 변경은 패키지 상대 import, NFC만 적용하는 계산(원문 반환은 별도), 공식 `twemoji-parser==11.0.2` 정규식 사용이다. 원본 JS 정규식과 생성 Python 상수의 SHA256은 `TWEMOJI_PROVENANCE.json`에 있다. Python 인덱스와 공식 UTF-16 인덱스를 명시적으로 환산한다. 런타임 리소스 파일 읽기, 네트워크, subprocess, 환경 변수 접근은 없다.

공식 `twitter/twitter-text` conformance의 가중 길이 44개와 URL·TLD 1,682개를 저장한 JSON으로 오프라인 대조한다. 공식 소스 commit과 원본 자료 SHA256은 `tests/fixtures/x-twitter-text/PROVENANCE.json`에 기록했다. 현재 X 서비스의 수락을 관측하는 검사나 유료·장문 게시물 지원을 의미하지 않는다.

Python 포트는 MIT(`LICENSE`), 원래 twitter-text는 Apache2(`LICENSE.twitter-text`), twemoji 정규식은 MIT(`LICENSE.twemoji`)다.
