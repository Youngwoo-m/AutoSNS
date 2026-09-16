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

---

## GeoAI 블로그 하루 1편 자동 발행 (geoaina.blogspot.com)

학과 블로그(smusafety)와 별개로, **GeoAI·생성형AI 전용 블로그**에 매일 1편을 올린다.
구글 계정이 달라 **토큰을 따로 쓴다**(`token_blogger_geoai.json`).

| 파일 | 역할 |
|------|------|
| `geoai_auth_setup.py` | **최초 1회** — 블로그 소유 계정으로 인증(쓰기 권한까지 확인) |
| `geoai_blogger.py` | GeoAI 블로그 발행 계층(토큰·중복확인·라벨 상한·오늘 발행 여부) |
| `geoai_series.py` | 개념 시리즈 32편 — GeoAI 26편(`GEO_TOPICS`)과 생성형 AI 사용법 6편(`GENAI_TOPICS`)을 번갈아 발행. 본문은 Claude 가 작성 |
| `geoai_daily.py` | 하루 1편 결정·발행(화요일=주간 뉴스 브리핑, 나머지=시리즈 1편) + 카드뉴스·영상 합성 |
| `geoai_cards.py` | 글 내용을 Gamma 카드뉴스 PNG 여러 장으로 |
| `geoai_assets.py` | 카드 PNG 를 공개 GitHub 저장소에 올려 CDN 주소로(Blogger 는 이미지 업로드 미지원) |
| `geoai_script.py` | 글 → 60~80초 뉴스브리핑 영상 대본(장면별 나레이션) |
| `run_geoai.sh` | launchd 래퍼(인자 거부 — 실행 즉시 실제 발행) |
| `setup_geoai_schedule.sh` | 매일 07:40 launchd 등록 |

### 카드뉴스와 영상
- **카드뉴스**: 모든 글에 Gamma 카드 3장(`geoai.cards.count`)을 만들어 첫 장은 글 맨 위,
  나머지는 본문 아래 '카드뉴스로 한눈에' 섹션에 넣는다. 구성은 표지 → 핵심 → 블로그
  안내이고, 장수를 줄여도 표지·마무리 자리는 먼저 확보한다. 원본이 장당 4~5MB 라 폭 1400px JPEG 로 줄여 올린다.
- **영상**: `geoai.video_weekdays`(화요일 브리핑, **주 1회**)에만 만들고, 길이는
  **40초 이내**로 짧게 간다(`geoai.video_max_chars`, 말속도 1.05 기준 290자 ≈ 40초).
  모델이 길이 지시를 넘기면 문장 단위로 잘라 상한을 맞춘다. 나머지 날은
  영상 없이 카드뉴스만 붙인다 — 아바타 영상은 크레딧이 들고, 매일 올리면 새 채널이
  스팸처럼 보이기도 한다. 글 내용을 대본으로 바꿔
  HeyGen AI 아나운서 영상을 만들고, 개인 채널 **@geoai-na** 에 올린 뒤 글에 임베드한다.
  제작·업로드는 `youtube-shorts-auto/geoai_video.py`(별도 venv)에서 돈다.
- 아바타는 GeoAI 전용(`editions.geoai.heygen.talking_photo_id`, 명패 없는 데스크)을 쓰고,
  책상에 'GeoAI와 생성형AI' 명패를 그려 넣는다(`heygen.dept`). 학과 채널 아바타는 그대로다.
- 카드·영상이 실패해도 글은 그대로 발행된다(있으면 더 좋은 것이지 발행 조건이 아니다).
- `--dry` 는 HeyGen 을 호출하지 않는다(크레딧이 나가므로 대본만 보여준다).

### 설정 (`config.json`)
- `geoai.blog_id` / `geoai.url` — 대상 블로그
- `geoai.brief_weekday` — 뉴스 브리핑 요일(0=월, 기본 1=화)
- `geoai.local_tags` — 항상 붙는 지역·브랜드 라벨(15개 상한 안에서 자리 보장)
- `editions.geoai` — 브리핑용 뉴스 질의·태그·제목(기존 에디션과 같은 방식)
- `geoai.cards` — 카드뉴스 장수·비율·테마(`enabled: false` 면 끔)
- `geoai.assets` — 이미지 저장소(`SMUDS-m/geoai-assets`, 공개)와 축소 폭
- `geoai.video_weekdays` / `video_privacy` — 영상 만드는 요일(0=월)과 공개 범위
- 유튜브 쪽 문구는 `youtube-shorts-auto/config.json` 의 `editions.geoai`
  (제목 접두사·설명 꼬리말·AI 고지문·킥커·캐릭터 끄기)

### 처음 한 번
```bash
cd ~/devAPP/AutoSNS/naver-blog-auto
./.venv/bin/python geoai_auth_setup.py     # 브라우저에서 geoaina 소유 계정으로 로그인
./.venv/bin/python geoai_blogger.py        # 연결·쓰기 권한 확인(발행 안 함)
cd ../youtube-shorts-auto && ./.venv/bin/python geoai_youtube_auth.py   # @geoai-na 채널 인증
cd ../naver-blog-auto
bash setup_geoai_schedule.sh               # 매일 07:40 등록
```

### 확인 방법(발행 없이)
```bash
./.venv/bin/python geoai_daily.py --plan    # 오늘 무엇을 올릴지
./.venv/bin/python geoai_series.py --plan   # 시리즈 진행 상황(완료/대기)
./.venv/bin/python geoai_daily.py --dry     # 글까지 만들어 보고 발행은 안 함
```

### 주의
- Blogger 는 하루에 글을 몰아 올리면 403(남용 차단)을 낸다. 그래서 **하루 1편**이고,
  블로그에 오늘 날짜 글이 이미 있으면 그날은 아무것도 하지 않는다.
- 시리즈 진행 상황은 `geoai_state.json` + 블로그의 실제 제목 목록 둘 다로 판단한다.
  (상태 파일이 없어져도 같은 글이 두 번 나가지 않는다)
- 주제가 떨어지면 `geoai_series.py` 의 `GEO_TOPICS` / `GENAI_TOPICS` 에 더 넣으면 된다.
  발행 순서는 `_interleave()` 가 두 계열을 번갈아 배치해 만든다(한쪽이 먼저 떨어지면
  나머지가 이어진다). 회차 번호는 계열 안에서 세므로 순서를 바꿔도 흔들리지 않는다.
