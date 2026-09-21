# 유튜브 Shorts 재난안전 자동 발행

재난안전 뉴스(Google News RSS) → Claude로 Shorts 대본 생성 → **세로(9:16) 카드 프레임**
+ **한국어 TTS(edge-tts) 나레이션** → **mp4 합성** → **YouTube Data API v3** 로 Shorts 자동 발행.
매주 자동 실행(launchd).

기존 `naver-blog-auto`, `insta-cardnews` 와 **독립**된 프로젝트입니다(다른 스케줄·로그·인증).

## 파이프라인

```
fetch_news.py          재난안전 뉴스 수집 (다른 프로젝트와 동일 로직, API 키 불필요)
generate_script.py     Claude API → 장면별 [자막 + 나레이션 + 출처번호] + 제목/설명/해시태그
fetch_images.py        뉴스 원본 기사 이미지(og:image) 수집 → 장면별 매칭 (best-effort)
render_frames.py       로컬 HTML+헤드리스Chrome → 1080x1920 세로 카드 PNG (가운데 정렬, 하단 사진)
tts.py                 edge-tts → 장면별 한국어 mp3 (무료, 키 불필요) + 길이 측정
make_video.py          프레임+음성 → 세로 mp4 (imageio-ffmpeg 번들 ffmpeg 사용)
youtube_upload.py      YouTube Data API v3 → Shorts 업로드 (기본 dry-run 안전장치)
tiktok_upload.py       TikTok Content Posting API → 같은 mp4 게시 (기본 dry-run)
run_weekly.py          위 단계를 묶은 주간 엔트리 (스케줄러가 호출, 유튜브+틱톡 실제 발행)
```

각 뉴스 장면은 대본 단계에서 근거 기사 번호([출처]N)를 함께 내보내고, fetch_images 가 그 기사의
대표 이미지를 받아 render_frames 가 해당 장면 하단에 넣는다 → **장면 내용과 사진이 일치**한다.
(이미지 추출은 Google News 리다이렉트를 실제 URL로 디코딩 후 og:image 를 받는 best-effort 방식.
실패하면 그 장면은 사진 없이 렌더되어 자동화는 그대로 진행된다.)

## 최초 1회 설정

### 1) 의존성 설치
```
cd ~/devAPP/AutoSNS/youtube-shorts-auto
/usr/local/opt/python@3.12/bin/python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```
(시스템 ffmpeg 은 필요 없습니다. imageio-ffmpeg 가 ffmpeg 바이너리를 함께 받습니다.)

### 2) API 키 입력 — `config.json`
- `anthropic_api_key`: (다른 프로젝트 키를 그대로 넣어 둠)
- 그 외 뉴스/음성/영상 옵션은 기본값으로 동작합니다.

### 3) 유튜브 업로드 권한 발급 (Google Cloud, 최초 1회)
YouTube 는 아이디/비밀번호가 아니라 **OAuth 토큰**으로 업로드합니다. 아래를 1회 수행:

1. https://console.cloud.google.com → 프로젝트 생성
2. 'API 및 서비스' → 'YouTube Data API v3' **사용 설정**
3. 'OAuth 동의 화면' 구성: 사용자 유형 **외부**, 앱 이름 입력,
   **테스트 사용자**에 업로드 계정 `semyungds@gmail.com` 추가
4. '사용자 인증 정보' → 'OAuth 클라이언트 ID 만들기' → 유형 **데스크톱 앱** →
   생성 후 **JSON 다운로드**
5. 그 JSON 을 이 폴더에 **`client_secret.json`** 이라는 이름으로 저장
6. 로그인/토큰 저장 실행:
   ```
   ./.venv/bin/python youtube_login_setup.py
   ```
   브라우저가 열리면 `semyungds@gmail.com` 으로 로그인/동의 → `token.json` 저장 완료.
   (이후 토큰은 자동 갱신되어 보통 다시 안 해도 됩니다.)

### 4) 틱톡 업로드 권한 발급 (TikTok for Developers, 최초 1회)
틱톡도 아이디/비밀번호가 아니라 **OAuth 토큰**으로 업로드하며, **공개 게시는 앱 심사(audit)**
가 필요합니다(심사 전에는 본인만 보기 SELF_ONLY 로만 게시 = 샌드박스).

1. https://developers.tiktok.com → 로그인 → 'Manage apps' → 앱 생성
2. 앱에 **Login Kit** + **Content Posting API** 제품 추가
3. Content Posting API 에서 **Direct Post** 사용 설정. 공개 게시하려면 심사 신청/통과 필요
4. **Redirect URI** 에 `https://smuds.netlify.app/callback.html` 등록
   (config.tiktok.redirect_uri 와 동일. 틱톡 Web 플랫폼은 https 만 받으므로 localhost 는 못 쓴다)
5. 발급된 **Client key / Client secret** 을 `config.json` 의 `tiktok` 항목에 입력
6. (샌드박스 단계) 'Sandbox' → Target users 에 본인 틱톡 계정 추가
7. 키가 살아 있는지 먼저 확인(로그인 불필요, 1초):
   ```
   ./.venv/bin/python tiktok_login_setup.py --check
   ```
   샌드박스 키는 만료되면 여기서 `invalid_client` 가 난다. 이때는 포털에서 키를 다시 받아야 한다.
8. 로그인/토큰 저장:
   ```
   ./.venv/bin/python tiktok_login_setup.py            # 인증 URL 출력
   ./.venv/bin/python tiktok_login_setup.py --code <코드>
   ```
   콜백 페이지에 뜬 `code` 를 복사해 넘기면 `tiktok_token.json` 저장 완료.

심사 통과 후 `config.json` 의 `tiktok.privacy_level` 을 `PUBLIC_TO_EVERYONE` 으로 바꾸면
공개 발행됩니다. 심사 전에는 `SELF_ONLY` 로 두세요.

## 수동 테스트 (안전: 기본적으로 발행되지 않음)

```
./.venv/bin/python generate_script.py     # 대본 생성 → posts/<stamp>.json/.txt
./.venv/bin/python fetch_images.py        # 뉴스 원본 이미지 → posts/images_<stamp>/
./.venv/bin/python render_frames.py       # 세로 카드 PNG → posts/frames_<stamp>/
./.venv/bin/python tts.py                 # 나레이션 mp3 → posts/audio_<stamp>/
./.venv/bin/python make_video.py          # 세로 mp4 → posts/short_<stamp>.mp4
./.venv/bin/python youtube_upload.py      # dry-run: 업로드 안 함, 메타데이터만 출력
./.venv/bin/python tiktok_upload.py       # dry-run: 틱톡 게시 안 함, 준비상태만 출력
```

**틱톡 본인만보기(SELF_ONLY) 실제 게시 테스트:** `./.venv/bin/python tiktok_upload.py --selfonly`
`posts\short_<stamp>.mp4` 를 직접 재생해 영상을 확인하세요.

**실제 업로드를 비공개로 안전 테스트:**
```
./.venv/bin/python youtube_upload.py --private   # 비공개(private)로 실제 업로드
```
유튜브 스튜디오에서 결과를 확인한 뒤 좋으면 공개로 바꾸거나, 스케줄이 공개로 올리게 둡니다.

## 주간 자동 발행 등록
```
bash setup_schedule.sh
```
기본 매주 **수요일 09:00**(네이버 08:00 / 인스타 08:30 과 분리). 즉시 테스트:
`launchctl kickstart -p gui/$UID/com.smuds.ytshorts.weekly`

## ⚠️ 안전장치 (중요)
- **수동 실행(`youtube_upload.py`)은 기본 발행되지 않습니다.** 항상 dry-run(메타데이터만).
- **실제 공개 발행은 `run_weekly.py`(스케줄)에서만** `dry_run=False` 로 일어납니다.
  (naver/insta 프로젝트에서 실수 발행했던 사고를 막기 위한 설계)
- 스케줄 실행 시각에 맥이 켜져 있고 `token.json` 이 유효해야 동작합니다.

## 주요 설정 (config.json)
- `youtube.privacy`: 스케줄 발행 공개 범위(`public`/`unlisted`/`private`). 기본 `public`.
- `youtube.title_prefix`: 제목 앞에 붙는 말머리. 기본 `[SMU 재난안전뉴스]`.
- `youtube.homepage_url`: 설명란에 넣는 학과 홈페이지. 기본 `https://www.semyung.ac.kr/smds.do`.
- `news_images.enabled`/`news_images.max`: 뉴스 원본 이미지 사용 여부/최대 장수(기본 4).
- `youtube.category_id`: 기본 `25`(뉴스/정치).
- `tts.voice`: 한국어 음성. 여성 `ko-KR-SunHiNeural` / 남성 `ko-KR-InJoonNeural`.
- `tts.rate`: 말속도(예 `+6%`). `video.max_seconds`: Shorts 길이 상한(기본 75초, 초과분 장면 제외).
- `video.bgm_path`: 배경음악 mp3 경로(넣으면 낮은 볼륨으로 깔림). 비우면 나레이션만.

## 주의 / 비용
- YouTube Data API 업로드는 **하루 할당량**을 소비합니다(기본 1일 10,000 유닛,
  업로드 1건 ≈ 1,600 유닛 → 하루 여러 건 가능, 주 1회 운영엔 충분).
- edge-tts 는 무료지만 인터넷 연결이 필요합니다.
- 비용: Claude(대본) 수 센트 수준. TTS/ffmpeg/업로드는 무료.
- 사실성: 대본은 '수집된 실제 뉴스 목록' 밖의 구체 사실을 지어내지 않도록 프롬프트로 강제합니다.
```
