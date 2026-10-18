# ④ 제작 — Canva 카드뉴스 연결

승인된 콘텐츠의 인스타 변환본(카드 5~6장 문구)을 Canva 브랜드 템플릿에 채워 카드 이미지로 만들고,
그 이미지로 인스타를 자동 발행한다. (2026-10-18 설계)

## 확인한 것

- Canva CLI 2.14.1 설치(`/usr/local/lib/nodejs/node-v24.21.0-darwin-x64/bin/canva`, PATH 밖이라 전체 경로로 부른다)
- 로그인: youngwoo Na (팀 계정). 권한: `autofill`, `brand_template`, `design_generation`, `resize`, `export_png_transparency`, `background_removal`
- 브랜드 템플릿: **아직 없음** → 사람이 Canva 편집기에서 하나 만들어야 한다(아래 규격)
- autofill: 템플릿 ID + 필드별 값(글자 또는 업로드한 이미지). 분당 60회

## 흐름

```
③ 승인된 콘텐츠 (인스타 변환본: 카드 5~6장 "제목 / 본문", 캡션, 해시태그)
   │ 1. 카드 문구를 필드로 나눔 (C1_TITLE, C1_BODY … C6_BODY)
   │ 2. 디오라마 이미지가 있으면 Canva 자산으로 업로드 → COVER_IMAGE
   ▼
Canva autofill (브랜드 템플릿 1개, 6쪽)  → 새 디자인
   │ 3. PNG 로 내보내기(쪽마다 1장)
   ▼
data/media/YYYY/MM/<콘텐츠ID>/card_01.png …
   │ 4. 콘솔 ③ 검토 화면에 카드 미리보기 (사람이 확인)
   ▼
⑥ 인스타 자동 발행: post_instagram.post_carousel({images, caption})
```

카드 문구에 들어가지 않는 글자(제목이 너무 김 등)는 1단계에서 길이를 재고, 넘치면 초안 단계로 되돌린다.

## 템플릿 규격 (사람이 Canva 에서 만들 것)

> 2026-10-18: 템플릿은 종류별 8개(T1~T8)로 나눴다 — `docs/Canva_템플릿_추천.md`. 아래 규격은 **T1 생활안전 수칙 카드**다. 확인 명령은 `python3 app/makers/canva_cards.py check T1_safety_cards`.

| 항목 | 값 |
|---|---|
| 크기 | 1080 × 1350 (인스타 세로 4:5) |
| 쪽 | 6쪽: 1 표지, 2~5 본문, 6 마무리 |
| 글꼴 | 제목·쪽 번호 **Pretendard Bold**, 본문 **KoPub 돋움 Bold** (CLAUDE.md, `FONTS/`). 굵기 대신 크기·색으로 위계 |
| 필드 이름 | 표지 `C1_TITLE`, `C1_BODY`, 이미지 `COVER_IMAGE` / 본문 `C2_TITLE`·`C2_BODY` … `C5_TITLE`·`C5_BODY` / 마무리 `C6_TITLE`, `C6_BODY` / 모든 쪽 `HANDLE`(계정 이름) |
| 글자 한도 | 제목 22자, 본문 60자 안팎(템플릿 상자 크기에 맞춰 정한 뒤 알려 주면 1단계 검사에 반영) |
| 이미지 | 표지 이미지 칸만. 그림 안에 글자 없음(AI 이미지 한글 깨짐), 사고·부상 장면 없음 |
| 계정별 | 학과용·개인용 템플릿을 따로 두면 계정마다 색·로고를 다르게 쓸 수 있다 |

필드 이름은 Canva 편집기 → 앱 → **데이터 자동 입력(Data autofill)** 에서 상자마다 붙인다. 다 만들면 **브랜드 템플릿으로 게시**한다.

## 구현 순서

1. `app/makers/canva_cards.py`: 문구 나누기 → (이미지 업로드) → autofill → 작업 기다리기 → PNG 내보내기 → 내려받기 — **완료 2026-10-18**. 템플릿만 남음: 게시 후 `config/canva.json` 의 `templates` 에 ID 를 넣고 `python3 app/makers/canva_cards.py check T1_safety_cards` 로 필드 확인
2. 콘솔: ③ 검토 화면에 [카드 만들기] 버튼과 카드 미리보기, 콘텐츠에 `media.cards` 저장
3. ⑥ 어댑터: `(dept, instagram)` 자동 발행 연결(`post_instagram.post_carousel`, 크롬 프로필 잠금 `profile:insta`)
4. 시험: 템플릿 채우기 → 미리보기 → 인스타 점검(dry, 게시 직전 멈춤) → 사람 승인 뒤 첫 실제 발행

## 대비책

- 템플릿이 없거나 autofill 이 실패하면 지금처럼 Gamma 카드 생성기(`insta-cardnews/gamma_make.py`)를 쓴다.
- `design_generation`(Canva AI 디자인 생성)은 결과 모양이 매번 달라 정기 카드에는 쓰지 않는다.
