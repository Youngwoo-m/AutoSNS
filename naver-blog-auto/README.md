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

## GeoAI 블로그 하루 2편 자동 발행 (geoaina.blogspot.com)

학과 블로그(smusafety)와 별개로, **GeoAI·생성형AI 전용 블로그**에 매일 2편을 올린다
(아침 07:40 — 영상까지 / 저녁 18:00 — 글만).
구글 계정이 달라 **토큰을 따로 쓴다**(`token_blogger_geoai.json`).

| 파일 | 역할 |
|------|------|
| `geoai_auth_setup.py` | **최초 1회** — 블로그 소유 계정으로 인증(쓰기 권한까지 확인) |
| `geoai_blogger.py` | GeoAI 블로그 발행 계층(토큰·중복확인·라벨 상한·오늘 발행 여부) |
| `geoai_series.py` | 시리즈 66편 — GeoAI 43편(`GEO_TOPICS`) · 생성형 AI 사용법 14편(`GENAI_TOPICS`) · 안전한국훈련 문서 실무 9편(`SAFETYDOC_TOPICS`). 본문은 Claude 가 작성 |
| `geoai_daily.py` | 1편 결정·발행(화요일=주간 뉴스 브리핑, 나머지=시리즈 1편) + 카드뉴스·영상 합성 |
| `geoai_banner.py` | 글 머리에 넣을 가로 3:1 배너 PNG(헤드리스 Chrome, Gamma 크레딧 없음) |
| `geoai_steps.py` | 본문 '따라하기' 단계를 그린 도식 PNG(배너와 같은 방식) |
| `geoai_cards.py` | 글 내용을 Gamma 카드뉴스 PNG 여러 장으로(`media_style: cards` 일 때) |
| `geoai_assets.py` | 카드 PNG 를 공개 GitHub 저장소에 올려 CDN 주소로(Blogger 는 이미지 업로드 미지원) |
| `geoai_script.py` | 글 → 40초 이내 쇼츠 대본(화면 제목·화면 문구·나레이션) |
| `run_geoai.sh` | 아침 07:40 launchd 래퍼 — 영상까지 함께(인자 거부, 실행 즉시 실제 발행) |
| `run_geoai_evening.sh` | 저녁 18:00 launchd 래퍼 — `--no-video`(글만) |
| `setup_geoai_schedule.sh` | 아침·저녁 두 작업 launchd 등록 |

### 카드뉴스와 영상
- **이미지**(`geoai.media_style`):
  · `banner`(기본) — 가로 3:1 배너 1장을 글 맨 위에 넣는다. 카드뉴스(16:9 여러 장)는
    글에서 차지하는 자리가 너무 커서 기본값을 배너로 바꿨다. 직접 그리므로 크레딧이 없다.
  · `cards` — Gamma 카드뉴스 `geoai.cards.count` 장(표지 → 핵심 → 블로그 안내).
    첫 장은 글 맨 위, 나머지는 본문 아래 '카드뉴스로 한눈에' 섹션에.
  · `none` — 이미지 없이 글만. 원본이 장당 4~5MB 라 폭 1400px JPEG 로 줄여 올린다.
- **영상**: **매일 쇼츠 1편**을 올린다(`geoai.daily_video`). 평소에는 카드 영상
  (카드 프레임 + 무료 edge-tts, 추가 비용 없음)이고, `geoai.video_weekdays`(화요일)
  에만 HeyGen 아바타 아나운서 영상이다. 길이는
  **40초 이내**로 짧게 간다(`geoai.video_max_chars`, 말속도 1.05 기준 290자 ≈ 40초).
  모델이 길이 지시를 넘기면 문장 단위로 잘라 상한을 맞춘다.
  대본에는 나레이션과 함께 화면에 띄울 문구(`lines`)와 화면 제목이 들어간다 —
  카드 영상은 그 문구를 그대로 프레임에 그린다. 나머지 날은
  영상 없이 카드뉴스만 붙인다 — 아바타 영상은 크레딧이 들고, 매일 올리면 새 채널이
  스팸처럼 보이기도 한다. 글 내용을 대본으로 바꿔
  HeyGen AI 아나운서 영상을 만들고, 개인 채널 **@geoai-safety** 에 올린 뒤 글에 임베드한다.
  제작·업로드는 `youtube-shorts-auto/geoai_video.py`(별도 venv)에서 돈다.
- 아바타는 GeoAI 전용(`editions.geoai.heygen.talking_photo_id`, 명패 없는 데스크)을 쓰고,
  책상에 '재난안전과 GeoAI' 명패를 그려 넣는다(`heygen.dept`). 학과 채널 아바타는 그대로다.
- 카드·영상이 실패해도 글은 그대로 발행된다(있으면 더 좋은 것이지 발행 조건이 아니다).
- `--dry` 는 HeyGen 을 호출하지 않는다(크레딧이 나가므로 대본만 보여준다).

### 유튜브 게시물(커뮤니티)
그날 글을 채널 '게시물' 탭에도 올린다 — 제목 + 한 줄 요약 + 글 링크 + 쇼츠 링크 + 배너.
배너는 게시물용으로 **2:1** 로 다시 그린다(유튜브가 2:5~5:2 만 받아 3:1 은 거부된다).
쇼츠 주소를 함께 넣으면 영상 카드까지 펼쳐진다.

화면 자동화에서 걸렸던 것들(2026-09-17):
- 같은 aria-label 의 **0×0 사본**이 먼저 잡혀 좌표 클릭이 빗나간다 → 크기가 있는 것만 고른다
- 작성기는 접혀 있어 `#placeholder-area` 를 눌러야 펼쳐지고, 그 클릭은 CDP 로 보낸
  진짜 마우스 이벤트여야 한다
- 이미지 파일은 검색창의 '이미지로 검색' input 이 아니라 `ytd-backstage-*` 안의
  input 에 넣어야 한다
- 이미지를 붙이면 편집 대화상자가 좌표 클릭을 가로채므로 '게시'는 JS 클릭으로 누른다
  (대화상자의 X 는 이미지를 지운다)
YouTube Data API 에는 게시물 작성 기능이 없어 **로그인 프로필을 쓴 브라우저 자동화**다
(네이버 발행과 같은 방식·같은 약점 — 화면이 바뀌면 셀렉터를 고쳐야 한다).

```bash
cd ~/devAPP/AutoSNS/youtube-shorts-auto
./.venv/bin/python geoai_community_login.py     # 최초 1회: 채널 계정으로 직접 로그인
echo '{"title":"글 제목","url":"https://...","video_url":"https://youtu.be/..."}' \
  | ./.venv/bin/python geoai_community.py        # --go 를 붙여야 실제 게시
```
설정은 `youtube-shorts-auto/config.json` 의 `editions.geoai.community_post`
(`enabled`·`handle`·`headless`·`tail`). 실패하면 `logs/community_*.png` 에 화면이 남고,
블로그·영상 발행에는 영향을 주지 않는다.

### 카테고리
Blogger 에는 카테고리가 없고 **라벨**이 그 역할을 한다. 주제 태그는 글마다 달라서
그대로 두면 라벨 목록이 카테고리가 아니라 태그 구름이 된다(글 5편에 라벨 45종이던
때가 있다). 그래서 **글마다 반드시 하나씩 붙는 카테고리 라벨**을 따로 둔다.

| 카테고리 | 편수 |
|---|---|
| GeoAI 개념 | 13 |
| GIS 도구 | 17 |
| 재난 현장 활용 | 13 |
| 생성형AI 사용법 | 14 |
| 안전한국훈련 실무 | 9 |

- 분류는 `geoai_series.category_of()` — slug 로 정한다. 계열(`FAMILIES`)과 따로 두는
  이유는 GeoAI 계열 42편을 한 칸에 넣으면 카테고리 하나에 글이 몰리기 때문이다.
- 카테고리 라벨은 지역 태그와 함께 **끝까지 지키는 자리**에 들어간다
  (`merge_labels(..., pinned=[카테고리])`). 길이 상한에 밀려 잘리면 그 글이 카테고리
  메뉴에서 사라지므로 개수·길이 어느 쪽으로도 잘리지 않아야 한다.
- **화면에 메뉴로 띄우는 것은 API 로 안 된다** — Blogger API 에는 레이아웃·테마
  리소스가 없다(`blogs·posts·pages·comments·users` 뿐). Blogger 화면에서
  **레이아웃 > 가젯 추가 > 라벨** 을 넣고, 표시할 라벨로 위 5개만 고르면 된다.
- 라벨 가젯은 **하나만** 둔다. 가젯 제목은 아무것도 걸러내지 않으므로, 카테고리마다
  가젯을 만들면 같은 목록이 그 수만큼 반복된다(2026-09-20 에 가젯 6개가 각각 라벨
  41종을 보여 사이드바에 링크가 246개였다). 거르는 것은 가젯 안의
  **표시 > 선택한 라벨** 뿐이다.
- **새 카테고리의 첫 글이 나가면 그 라벨을 가젯에 직접 체크해야 한다.** '선택한 라벨'은
  고정 목록이라 자동으로 늘지 않고, 글이 하나도 없는 라벨은 아예 목록에 뜨지도 않아
  미리 체크해 둘 수도 없다. 그래서 `geoai_daily.py` 가 발행할 때
  `geoai_blogger.has_label()` 로 그 카테고리의 첫 글인지 보고, 첫 글이면 로그와
  **카톡 알림에 '가젯에 체크하세요'** 를 덧붙인다.
- 체크는 가젯 창의 '저장'과 레이아웃 화면 오른쪽 위 **'정렬 저장'** 까지 눌러야 반영된다.
  앞만 누르면 화면은 바뀐 듯 보여도 블로그에는 그대로다.
- 가젯에는 카테고리 5종 외에 **`재난관리` 한 종이 더 체크돼 있다**(2026-09-21, 사용자가
  의도해서 넣음). 카테고리 라벨이 아니라 여러 카테고리에 걸쳐 붙는 주제 태그이므로,
  이 항목만은 눌렀을 때 카테고리 분류와 다른 묶음이 나온다. 목록을 정리할 때
  실수로 들어간 것으로 보고 빼지 말 것.

### 본문 구성(따라하기·프롬프트)
글마다 아래 두 칸이 들어간다 — 개념 설명만으로는 따라 할 수 없다는 요청에서 나왔다.

- **🖥️ 화면에서 따라하기** — 도구를 쓰는 4~6단계. 메뉴 이름을 그대로 적는다
  (`레이어 > 레이어 추가 > 벡터 레이어`). 같은 값으로 `geoai_steps.py` 가 도식 PNG 를
  그려 목록 위에 넣는다. 이건 **직접 그린 도식**이지 실제 화면이 아니다 — 프로그램
  화면을 자동으로 캡처하려면 그 프로그램을 띄워 조작해야 한다. 진짜 화면을 넣으려면
  아래 '화면 캡처'를 쓴다.
- **✍️ 그대로 복사해 쓰는 프롬프트** — 복사해 바로 쓰는 프롬프트 1~2개를 상자에
  넣는다. 채워 넣을 자리는 `[기관명]` 처럼 대괄호로 표시한다.
- 두 칸의 품질 규칙은 `COMMON_HINT`(모든 글) + `FAMILY_HINT`(계열별)에 있다.
- 도식이나 업로드가 실패해도 글은 그대로 나간다(목록만 글자로 남는다).

### 화면 캡처(사람이 찍어 둔 실제 화면)
직접 찍은 프로그램 화면을 `shots/<slug>/` 에 두면 도식 대신 그것이 들어간다.
자세한 규칙은 `shots/README.md`.

| 파일 | 들어가는 자리 |
|------|--------------|
| `cover.png` | 단계 목록 맨 위 — 도식을 대신한다 |
| `01 레이어 추가.png` | 숫자 뒤 글자가 그림 설명이자 **단계를 찾는 낱말**이 된다 |
| `02.png` | 설명 없이 2단계 밑에만 |

| 파일 | 역할 |
|------|------|
| `geoai_shots.py` | `shots/` 를 읽어 CDN 에 올린다. `list` 로 무엇이 준비됐는지 본다 |
| `geoai_shots_apply.py` | **이미 나간 글**의 따라하기 칸에 캡처를 끼워 넣는다 |

- 아직 안 나간 글은 아무것도 안 해도 된다 — 발행할 때 알아서 들어간다.
- **자리는 번호가 아니라 파일 이름의 낱말로 정한다** — `…좌표계 표시.png` 는 '좌표계
  확인' 단계를 찾아간다. 따라하기 단계는 발행할 때 생성되므로 번호만으로는 글이 다시
  만들어질 때 어긋난다. 낱말로 못 찾은 파일만 번호를 쓰고, 번호 없는 파일도 받는다.
  맞춰 보는 규칙은 `geoai_shots.match_steps()`(점수가 높은 쌍부터 자리를 잡는다).
- 따라하기 단계 글은 발행 시점에 정해지므로 **보통은 글이 나온 뒤에** 무엇을 찍을지
  알게 된다. 그때 `geoai_shots_apply.py <slug>` 로 어느 자리에 붙을지 먼저 보고,
  `--go` 를 붙여 그 글의 따라하기 칸만 고친다(본문·제목·라벨·주소는 그대로).
  같은 단계에 다시 돌리면 갈아 끼운다.
- 캡처 수가 모자라도 된다 — 있는 번호만 들어가고 나머지 단계는 글자만 남는다.
  올리다 일부만 성공하면 번호가 밀 수 있어 그 글에는 캡처를 넣지 않는다.
- `shots/` 는 손으로 만든 자산이라 `.gitignore` 의 `*.png` 예외로 두어 git 이 남긴다.
- 캡처는 공개 저장소(`geoai-assets`)로 올라간다 — 개인정보·내부자료가 화면에 없는지
  보고 찍는다.

### Blogger 쪽 설정 — 저장소에 없는 것들
아래는 모두 Blogger 화면에서만 바꿀 수 있고(API 에 리소스가 없다) 저장소에 흔적이
남지 않는다. 2026-09-20 에 애드센스 준비로 점검하며 고친 것을 남긴다.
**셋 다 '사용 설정은 켜져 있는데 값이 비어 있는' 상태였다** — 켜져만 있으면 된 줄
알기 쉬우니 값까지 확인해야 한다.

| 설정 | 자리 | 값 |
|------|------|-----|
| 맞춤 robots.txt | 설정 > 크롤러 및 색인 생성 | `Mediapartners-Google`(애드센스 크롤러) 허용 + `Sitemap:` 한 줄. **비어 있으면 Blogger 기본값까지 사라진다** |
| 검색 설명 | 설정 > 메타 태그 | 한 문장. **마침표·쉼표를 넣으면 '입력이 잘못되었습니다'로 거부된다**(구두점 없이 쓴다) |
| 모바일 테마 | 테마 > (▾) > 모바일 설정 | **'모바일'**. '데스크톱'이면 테마의 `data:blog.isMobile` 분기를 타지 못해 휴대폰에서도 `width=1100` 이 나가 글자가 읽히지 않는다 |

필수 페이지 3종(소개 · 개인정보처리방침 · 연락처)은 `pages` API 로 만들 수 있지만,
**상단 메뉴에 띄우려면 레이아웃 > 페이지 가젯에 항목을 손으로 넣어야 한다**(라벨
가젯과 같다 — 페이지를 공개하는 것만으로는 메뉴에 나오지 않는다).

### 블로그 겉모습(Blogger 설정 — 저장소가 아니라 Blogger 에 저장된다)
- **머리글 이미지**: `make_blog_header.py` 로 만든 배너를 공개 저장소에 올리고,
  레이아웃 > 머리글 구성 > **이미지 URL 입력** 에 그 주소를 넣는다(이미지 위치는
  '제목 및 설명 대신 이미지 표시' — 그림 안에 제목이 이미 있다).
  현재 주소: `https://cdn.jsdelivr.net/gh/SMUDS-m/geoai-assets@main/brand/header_1.jpg`
- **카드형 디자인**: 테마 > 맞춤설정 > 고급 > **CSS 추가** 에 `blog_theme.css` 내용을
  넣는다(글 목록을 흰 카드로, 사이드바 위젯도 카드로, 날짜 헤더 숨김).
  Blogger API 로는 테마를 못 바꿔 브라우저로 직접 넣어야 하고, 이 파일은 그 사본이다.

### 설정 (`config.json`)
- `geoai.blog_id` / `geoai.url` — 대상 블로그
- `geoai.brief_weekday` — 뉴스 브리핑 요일(0=월, 기본 1=화)
- `geoai.local_tags` — 항상 붙는 지역·브랜드 라벨(15개 상한 안에서 자리 보장)
- `editions.geoai` — 브리핑용 뉴스 질의·태그·제목(기존 에디션과 같은 방식)
- `geoai.media_style` — `banner`(기본) / `cards` / `none`
- `geoai.banner` — 배너 문구(브랜드·킥커)
- `geoai.cards` — 카드뉴스 장수·비율·테마(`media_style: cards` 일 때)
- `geoai.assets` — 이미지 저장소(`SMUDS-m/geoai-assets`, 공개)와 축소 폭
- `geoai.daily_video` — 매일 카드 쇼츠 올리기(기본 true)
- `geoai.video_weekdays` / `video_privacy` — 아바타 영상 요일(0=월)과 공개 범위
- 카드 영상의 상단·하단 문구는 `youtube-shorts-auto/config.json` 의
  `editions.geoai.video.header_text` / `footer_text`
- 유튜브 쪽 문구는 `youtube-shorts-auto/config.json` 의 `editions.geoai`
  (제목 접두사·설명 꼬리말·AI 고지문·킥커·캐릭터 끄기)

### 처음 한 번
```bash
cd ~/devAPP/AutoSNS/naver-blog-auto
./.venv/bin/python geoai_auth_setup.py     # 브라우저에서 geoaina 소유 계정으로 로그인
./.venv/bin/python geoai_blogger.py        # 연결·쓰기 권한 확인(발행 안 함)
cd ../youtube-shorts-auto && ./.venv/bin/python geoai_youtube_auth.py   # @geoai-safety 채널 인증
cd ../naver-blog-auto
bash setup_geoai_schedule.sh               # 아침 07:40 · 저녁 18:00 등록
```

### 확인 방법(발행 없이)
```bash
./.venv/bin/python geoai_daily.py --plan    # 오늘 무엇을 올릴지
./.venv/bin/python geoai_series.py --plan   # 시리즈 진행 상황(완료/대기)
./.venv/bin/python geoai_daily.py --dry     # 글까지 만들어 보고 발행은 안 함
```

### 주의
- **하루 2편**이다 — 아침 07:40(영상 포함)과 저녁 18:00(글만). 상한은
  `config.json` 의 `geoai.posts_per_day`(현재 2)로 정하고, 오늘 이미 그만큼
  올라가 있으면 그 실행은 아무것도 하지 않는다(밀린 실행이 몰려도 안전하다).
  Blogger 는 글을 몰아 올리면 403(남용 차단)을 내므로 **두 편 사이를 10시간 넘게**
  벌려 뒀다. 상한을 더 올리려면 간격도 함께 살펴야 한다.
- 저녁 편에 영상을 붙이지 않는 것은 새 채널에 쇼츠를 하루 2편씩 올리면 스팸처럼
  보이기 때문이다. 붙이려면 `run_geoai_evening.sh` 에서 `--no-video` 를 빼면 된다.
- 라벨은 개수(15개)뿐 아니라 **쉼표로 이은 전체 길이**에도 한계가 있다 — 넘기면
  400(invalid argument)이 난다. 실측으로 213바이트는 통과, 221바이트는 거부였다.
  `geoai_blogger.LABEL_BYTES_CAP`(200)으로 잘라 내며, 지역·브랜드 라벨은 남긴다.
- 시리즈 진행 상황은 `geoai_state.json` + 블로그의 실제 제목 목록 둘 다로 판단한다.
  (상태 파일이 없어져도 같은 글이 두 번 나가지 않는다)
- 주제가 떨어지면 `geoai_series.py` 의 계열 목록에 더 넣으면 된다 — 반드시 계열
  **끝에** 덧붙인다(중간에 끼우면 계열 회차 번호가 밀린다). 주제가 다 떨어지면
  발행하지 않고 '남은 주제가 없습니다' 만 로그에 남기고 조용히 끝난다.
  발행 순서는 `_publish_order()` 가 만든다 — 계열을 무작위로 섞되(고정 씨앗
  `SHUFFLE_SEED`) 계열 안 순서는 지킨다(기본계획서 → 실시계획서 → 시나리오처럼
  순서가 곧 내용인 편이 뒤집히지 않게). 씨앗을 바꾸면 배치가 통째로 달라진다.
  회차 번호는 계열 안에서 세므로 배치를 바꿔도 흔들리지 않는다.
- 계열마다 본문 지침이 조금 다르다(`FAMILY_HINT`) — 실무 문서 편은 순서·프롬프트
  예시·사람이 확인할 항목·.hwpx 변환 단락을 반드시 넣게 한다.

---

## 학과 블로그 (smuds2026.blogspot.com)

GeoAI 블로그와 별개로, 세명대 재난안전학과 공식 블로그에도 글이 나간다.
읽는 사람이 다르다 — 학과에 관심 있는 고등학생·학부모와 재학생이다.

| 들어오는 길 | 언제 | 무엇을 |
|------|------|--------|
| `career_series.py` (`com.smuds.blogcareer.daily`) | 매일 08:30 | 시리즈 한 편 |
| `run_weekly.py` → `post_blogger.py` (`com.smuds.naverblog.weekly`) | 매일 19:00 | 요일별 뉴스 브리핑(네이버에 올린 글을 교차발행) |

하루 상한은 `blogger.daily_limit`(현재 2) 하나로 둘을 합산해 묶는다. 시리즈는
`blogger.career_per_run`(1)만 쓰고 나머지 한도는 저녁 브리핑 몫으로 남긴다.
한 번에 몰아 올리면 계정이 API 게시 제한을 먹는다(2026-09-16 에 4편째부터 403).

### 시리즈
`career_series.py` 의 `SERIES` 를 **순서대로** 소진한다. 앞 시리즈가 다 나가야
다음으로 넘어가고, 이미 올라간 제목은 건너뛰므로 매일 돌려도 중복되지 않는다.

- **진로 8편** — 본문이 파일에 박혀 있다(영상 대본 기반, 유튜브 영상을 끼운다)
- **자격증 16편** — 발행할 때 본문을 만든다(`cert_topics` + `cert_writer`).
  응시자격·시험과목·일정·수수료가 해마다 바뀌어 코드에 박으면 틀린 정보가 굳는다.
  `cert_writer.SYSTEM` 이 그런 항목을 단정하지 못하게 묶고 큐넷 확인을 권하게 한다.
  모델이 쓴 글이라 문단은 통째로 escape 한 뒤 `<b>` 만 되살린다(`_safe`).

주제를 더 넣을 때는 계열 **끝에** 덧붙인다 — 편수(`[n/N]`)는 목록 길이로 세므로
중간에 끼우면 이미 나간 글의 번호와 어긋난다.

### 설정 (`config.json` 의 `blogger.*`)
- `blogger.blog_id` / `blogger.url` — 대상 블로그. **옮길 때 같이 고쳐야 한다** —
  2026-09-18 에 옛 블로그 ID 가 남아 있어 403(권한 없음)으로 교차발행이 실패했다.
- `blogger.max_labels`(1) — 대표 라벨 하나만 단다. 주제 태그까지 섞으면 사이드바
  라벨 목록이 카테고리 구실을 못 한다.
- `blogger.links` — 글 끝 '채널 바로가기' 목록. **학과 자체 채널을 앞에** 두고
  (홈페이지·유튜브·인스타·네이버·쓰레드) 관련 사이트는 뒤에 붙인다.
  링크를 바꿔도 **이미 나간 글은 그대로**다. 글 끝 목록의 마지막 `</ul>` 앞에
  `<li>` 를 끼워 넣는 손질이 따로 필요하다 — 글마다 끝 형식이 조금씩 달라
  (`<hr><p>…` 가 있는 것과 없는 것) 블록을 통째로 갈아 끼우면 일부가 틀어진다.
- `config.json` 은 API 키가 들어 있어 git 이 제외한다 — 이 값들은 저장소에 없다.

### Blogger 쪽 설정
GeoAI 블로그와 달리 여기는 **Contempo 테마**라 반응형이 정상이고, 맞춤 robots.txt 를
끄고 Blogger 기본값을 쓰고 있다(기본값에 `Mediapartners-Google` 과 `Sitemap` 이 들어 있다).
검색 설명은 2026-09-21 에 켜고 채웠다. 필수 페이지 3종(소개·개인정보처리방침·문의)과
상단 메뉴, 카테고리 라벨 가젯도 갖춰져 있다.
