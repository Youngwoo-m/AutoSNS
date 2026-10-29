# 인스타그램 재난안전 카드뉴스 자동화

재난안전 뉴스(Google News RSS) → Claude로 카드 문구 생성 → **로컬 렌더러(KoPubWorld)**
로 카드(PNG) 생성 → **인스타그램 캐러셀**로 자동 게시. 매주 자동 실행(launchd).

기존 `naver-blog-auto` 와 **독립**된 프로젝트입니다(다른 크롬 프로필·스케줄·로그).

## 파이프라인

```
fetch_news.py         재난안전 뉴스 수집 (네이버 프로젝트와 동일 로직, API 키 불필요)
generate_cards.py     Claude API → 카드별 문구 + 캡션 + 해시태그 (사실성 원칙 유지)
render_cards_local.py  [기본] 로컬 HTML+헤드리스Chrome → KoPubWorld 카드 PNG
gamma_make.py         [옵션] Gamma REST API → 소셜 카드 PNG (config card_renderer="gamma")
post_instagram.py     Selenium → 인스타 웹 캐러셀 게시 (dry-run 안전장치)
run_weekly.py         위 단계를 묶은 주간 엔트리 (스케줄러가 호출, 실제 게시)
```

### 카드 렌더러 (config `card_renderer`)
- `"local"` (기본): setup 폴더의 `assets/FONTS/` 에 있는 **KoPubWorld Dotum** 폰트로 직접 렌더.
  단어 중간 줄바꿈·한 글자 위도우를 CSS(word-break:keep-all + text-wrap:pretty)+JS 오토핏으로
  원천 차단. Gamma 크레딧 불필요.
  폰트 경로는 `local_render.font_dir` — **비워두면 `../FONTS` 를 자동으로 찾습니다.**
- `"gamma"`: Gamma REST API 로 AI 디자인 카드 생성(유료 크레딧). `gamma_api_key` 필요.

## 릴 영상 제작 지침 (2026-10-28 정리)

- **흐름**: `make_reel.py` 가 먼저 Remotion(`remotion_reel.py` → `remotion-shorts/src/insta-reel`)으로 렌더하고, 실패하면 예전 ffmpeg 합성으로 돌아간다. 카드 등장·진행 점·끝 화면·디오라마 편집은 Remotion 이 한다(2026-10-23).
- **입력**: 카드 PNG + 배경음악(`reel.audio_file`, 기본 `assets/bgm.mp3`, 저작권 자유 음원만. 없으면 중단). ffmpeg 폴백은 1080x1920, 카드 가운데·위아래 브랜드색, 카드당 `reel.seconds_per_card`(기본 3.5초).
- **디오라마**(CLAUDE.md 영상 지침): 영상마다 2~3장이 원칙이나 크레딧을 쓰므로 기본은 끈다. `reel.diorama.paths` 에 기존 그림 0~3개를 주면 크레딧을 쓰지 않고, 새로 만들려면 `reel.diorama.scenes`(영어 장면 설명)와 `generate=true` 를 둘 다 켠다. 그림이 들어가면 화면 아래에 AI 생성 그림 고지가 붙는다. 그림 안에 글자 금지, 사고 순간·부상자 같은 고통스러운 장면 금지(대비·대응·구조 장면), 미니어처·틸트시프트 질감을 분명히 한다. 더치 앵글은 대응·구조 장면에만 쓴다.
- **배경 실사**(`reel_broll.py`, 2026-09-29): 카드 위아래 각 490px 띠에만 Pexels → Pixabay 영상을 깐다(카드 940px 은 가리지 않음). 사고·피해 장면은 쓰지 않고 상황 장면(빗길, 숲 연기, 눈길)만 고르며, 카드 아래 띠에 "배경: 자료 화면"을 표기한다. 키가 없거나 받기에 실패하면 단색 배경.
- **글꼴**: 제목·보조 Pretendard Bold, 카드 본문 KoPub 돋움 Bold. 바꿀 때는 `shared/fonts.py` 의 DISPLAY 한 줄만 고친다.

## 최초 1회 설정

1) **의존성 설치**
   ```
   cd ~/devAPP/AutoSNS/channels/insta-cardnews
   /usr/local/opt/python@3.12/bin/python3.12 -m venv .venv
   ./.venv/bin/python -m pip install -r requirements.txt
   ```

2) **API 키 입력** — `config.json`
   - `anthropic_api_key`: (네이버 프로젝트 키를 그대로 넣어 둠)
   - `gamma_api_key`: **Gamma 유료 플랜**에서 발급. https://gamma.app → 설정/API.
     (Generate API 는 유료 기능이며 카드 1세트 생성 시 크레딧이 차감됩니다.)

3) **인스타 로그인(쿠키 저장)**
   ```
   ./.venv/bin/python login_setup_insta.py
   ```
   열린 창에서 직접 로그인 → 피드가 보이면 터미널에서 Enter. 세션이 프로필에 저장됩니다.
   (세션 만료 시 다시 실행. 게시용 계정은 봇 차단을 줄이려면 **앱에서 한 번 로그인된**
   동일 계정을 권장.)

## 수동 테스트 (안전: 항상 dry-run = 게시 안 함)

```
./.venv/bin/python generate_cards.py        # 문구 생성 → posts/<stamp>.json/.txt
./.venv/bin/python gamma_make.py            # 카드 PNG 생성 → posts/cards_<stamp>/
./.venv/bin/python post_instagram.py        # '공유하기' 직전까지만 진행(dry-run)
```
`logs/` 의 단계별 스크린샷(`caption_screen`, `before_share`)으로 카드·캡션을 확인하세요.
인스타 DOM 이 바뀌어 버튼을 못 찾으면, 스크린샷을 보고 `post_instagram.py` 상단의
라벨 후보(`CREATE_LABELS`, `NEXT_LABELS`, `SHARE_LABELS` 등)를 조정하면 됩니다.

## 주간 자동 게시 등록

```
bash setup_schedule.sh
```
기본 매주 **수·토 19:30**(2026-10-21 저녁 시간대로 조정; 이전 08:30). 즉시 테스트:
`launchctl kickstart -p gui/$UID/com.smuds.instacards.weekly`

## ⚠️ 안전장치 (중요)

- **수동 실행은 절대 게시되지 않습니다.** `post_instagram.py` 를 직접 돌리면 항상 dry-run.
- **실제 게시는 `run_weekly.py`(스케줄)에서만** `dry_run=False` 로 일어납니다.
  (네이버 프로젝트에서 dry_run=false 로 테스트하다 실수 발행했던 사고를 막기 위한 설계)
- 스케줄 실행 시각에 맥이 켜져 있고 인스타 로그인 세션이 살아 있어야 동작합니다.

## 주의

- 인스타그램 웹 자동화는 메타 ToS 상 권장 방식이 아니며 DOM 변경·봇 탐지로 깨질 수 있습니다.
  주 1회 저빈도 + 실제 로그인 프로필로 위험을 낮췄지만, 계정 제재 가능성은 0이 아닙니다.
  더 안정적인 운영이 필요하면 추후 인스타그램 Graph API(비즈니스 계정) 방식으로 전환 가능.
- 비용: Claude(문구) 수 센트 + Gamma 크레딧(카드 1세트). 둘 다 종량.
```
