# Blogger 디자인 자산 (smusafety.blogspot.com)

Blogger API v3 에는 테마·레이아웃 엔드포인트가 없다. 그래서 헤더 이미지와 CSS 는
여기서 만들어 두고, 블로그에 넣는 것은 사람이 한 번 한다.

## 헤더 이미지
- 원본: `smusafety_header.png` (2400×600)
- CDN: https://cdn.jsdelivr.net/gh/SMUDS-m/geoai-assets@main/smusafety/header_20260917_1.jpg
- 다시 만들기: `naver-blog-auto/make_blogger_header.py` (헤드리스 크롬으로 그린다)
- 넣는 곳: Blogger → 레이아웃 → 헤더 옆 '수정' → 이미지 업로드 →
  배치는 '제목과 설명 대신'(이미지에 이미 학과명이 들어 있다)

## 카드형 CSS
- `theme.css` 를 Blogger → 테마 → 맞춤설정 → 고급 → 'CSS 추가' 에 붙여넣는다.
- 테마 HTML 을 고치지 않으므로, 테마를 바꿔도 이 CSS 만 다시 붙이면 된다.
- 담긴 것: 돋움 계열 글꼴(Gothic A1 → 돋움/맑은고딕 폴백), 본문 17px·줄간격 1.85,
  소제목 왼쪽 빨간 바, 글 목록 카드화(그림자·호버), 라벨 알약 모양, 모바일 1열.
