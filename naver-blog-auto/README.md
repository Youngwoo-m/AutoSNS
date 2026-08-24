# 네이버 블로그 주간 자동 포스팅

매주 수요일 08:00에 **Claude가 글을 생성**하고 **네이버 블로그에 자동 발행**합니다.

## 구조
| 파일 | 역할 |
|------|------|
| `config.json` | 설정 (API 키, 네이버 아이디, 주제 등) — 직접 채움 |
| `generate_content.py` | Claude API로 이번 주 글 생성 (`posts/`에 저장) |
| `login_setup.py` | **최초 1회** 직접 로그인해 Chrome 프로필(쿠키) 저장 |
| `publish_naver.py` | 저장된 프로필로 스마트에디터에 발행 |
| `run_weekly.py` | 생성+발행 일괄 실행 (스케줄러가 호출) |
| `setup_schedule.sh` | 매주 수 08:00 launchd 등록 |

## 설치 & 설정 (한 번만)

0. **의존성 설치** (Homebrew Python 3.12 필요: `brew install python@3.12`)
   ```bash
   cd ~/devAPP/AutoSNS/naver-blog-auto
   /usr/local/opt/python@3.12/bin/python3.12 -m venv .venv
   ./.venv/bin/python -m pip install -r requirements.txt
   ```

1. **설정 파일 만들기** — `config.example.json`을 `config.json`으로 복사 후 값 채우기
   - `anthropic_api_key`: https://console.anthropic.com 에서 발급
   - `naver_id`: 네이버 아이디
   - `blog.topic`: 블로그 주제(니치) ← **꼭 입력**
   - `blog.tags`: 매번 붙일 고정 태그

2. **최초 로그인 (쿠키 저장)**
   ```bash
   cd ~/devAPP/AutoSNS/naver-blog-auto
   ./.venv/bin/python login_setup.py
   ```
   브라우저가 뜨면 직접 로그인(2단계 인증 포함) → 터미널에서 Enter.
   → 비밀번호는 저장되지 않고 쿠키만 `chrome-profile/`에 보관됩니다.

3. **글 생성만 테스트**
   ```bash
   ./.venv/bin/python generate_content.py
   ```

4. **발행 테스트 (안전모드)** — `config.json`의 `publish.dry_run`이 `true`면
   발행 직전에 멈추고 화면/스크린샷으로 확인만 합니다.
   ```bash
   ./.venv/bin/python publish_naver.py
   ```
   문제 없으면 `dry_run`을 `false`로 바꾸세요.

5. **스케줄 등록** 
   ```bash
   bash setup_schedule.sh
   ```
   즉시 테스트: `launchctl kickstart -p gui/$UID/com.smuds.naverblog.weekly`

## 주의 / 한계
- 네이버는 공식 글쓰기 API가 없어 **브라우저 자동화** 방식입니다. 에디터 구조가
  바뀌면 셀렉터(`publish_naver.py`의 CSS/XPath)를 수정해야 할 수 있습니다.
  실패 시 `logs/`에 스크린샷이 남으니 참고하세요.
- 과도한 자동화는 네이버 정책 위반/계정 제재 위험이 있습니다. 주 1회 수준은
  위험이 낮지만 100% 보장은 아닙니다. **첫 몇 주는 결과를 직접 확인**하세요.
- 쿠키가 만료되면 `login_setup.py`를 다시 실행하세요.
- 스케줄 작업은 '맥이 켜져 있고 로그인된 상태'에서 실행됩니다.

## 로그
- 실행 로그: `logs/YYYY-MM.log`
- 디버그 스크린샷: `logs/*.png`
- 생성된 글 보관: `posts/`
