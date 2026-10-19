# Blogger 디자인 자산 (smuds2026.blogspot.com)

Blogger API v3 에는 테마·레이아웃 엔드포인트가 없다. 그래서 헤더 이미지와 CSS 는
여기서 만들어 두고, 블로그에 넣는 것은 사람이 한 번 한다.

디자인 기준은 학과 홈페이지(https://www.semyung.ac.kr/smds.do)다. 화면에서 직접
뽑은 색을 쓴다 — 남색 `#334A8E`(로고·제목), 금색 `#FFA500`(섹션 밑줄),
슬레이트 `#272C3C`(본문), 흰 바탕. 글꼴도 홈페이지와 같은 Noto Sans KR 계열이다.

## 헤더 이미지
- 원본: `smuds2026_header.png` (2400×420) — 홈페이지 상단바 구성(로고 · 구분선 ·
  학과명 · 영문 · 마스코트 · 아래 남색/금색 띠)
- CDN: https://cdn.jsdelivr.net/gh/Youngwoo-m/geoai-assets@main/smuds2026/header_20260920_1.jpg
- 다시 만들기: `naver-blog-auto/make_blogger_header.py`
- 넣는 곳: Blogger → 레이아웃 → 헤더 '수정' → 이미지 업로드 → '제목과 설명 대신'

## CSS
- `theme.css` 를 Blogger → 테마 → 맞춤설정 → 고급 → 'CSS 추가' 에 붙여넣는다.
- 담긴 것: 홈페이지 색·글꼴, 소제목 금색 밑줄, 글 목록 카드(상단 남색 라인),
  각진 라벨, 사이드바 위젯 제목 밑줄, 모바일 1열.
