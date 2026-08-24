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
- `"local"` (기본): setup 폴더의 `FONTS/` 에 있는 **KoPubWorld Dotum** 폰트로 직접 렌더.
  단어 중간 줄바꿈·한 글자 위도우를 CSS(word-break:keep-all + text-wrap:pretty)+JS 오토핏으로
  원천 차단. Gamma 크레딧 불필요.
  폰트 경로는 `local_render.font_dir` — **비워두면 `../FONTS` 를 자동으로 찾습니다.**
- `"gamma"`: Gamma REST API 로 AI 디자인 카드 생성(유료 크레딧). `gamma_api_key` 필요.

## 최초 1회 설정

1) **의존성 설치**
   ```
   cd ~/devAPP/AutoSNS/insta-cardnews
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
기본 매주 **수요일 08:30**(네이버 08:00 과 분리). 즉시 테스트:
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
