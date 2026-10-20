---
name: sns-publish-post
description: AutoSNS 에서 주제·링크를 받아 학과 채널(네이버 블로그·블로거·티스토리·유튜브·인스타·스레드·X)에 글이나 영상을 써서 발행할 때 따르는 절차. "블로그 글 써서 발행", "블로거에 올려줘", "숏츠로 만들어 게시" 같은 요청에 쓴다.
---

# 학과 채널에 글·영상 발행하기

## 채널 이름(사용자가 부르는 말 → 실제 대상)
- **블로그** = 네이버 블로그 studs23 — `channels/naver-blog-auto/publish_naver.py` 의 `publish(data)`. 구조형 data: `title, category, summary, intro, news_blocks[{heading, paragraph, image, keep_image, source{title,link}, video_url, video_label}], faq, outro, tags, no_images`.
- **블로거** = 학과 Blogger smuds2026 — `post_blogger.py`. 그림은 `geoai_assets.upload` 로 CDN 에 올려 `<img>`, 영상은 `<iframe>`. CTA 는 `post_blogger.build_html({"intro": ""}, cfg)`.
- **GeoAI 블로그** = geoaina.blogspot.com, **티스토리** = na-geoai.tistory.com(요약 + 원문 '전체 글 보기' 링크만, `tistory_crosspost.summary_html`).
- **유튜브** = 학과 @smds2023(token.json), 개인 GeoAI @geoai-safety(token_youtube_geoai.json, `SMUDS_EDITION=geoai`).
- **인스타·스레드·X** = 학과 계정(@smu_ds_official, @smuds_official) 뿐이다.

채널이 모호하면(블로그/블로거/GeoAI) 먼저 묻는다.

## 지킬 것
- 사실은 확인한 출처(공식 발표·기사)로만 쓴다. 법령·기준 수치는 원문 또는 정부 보도자료로 교차 확인하고 출처 링크를 본문에 남긴다.
- 이미지 속 글자: 제목 Pretendard Black, 보조 Pretendard Bold(`shared.fonts.display_css`), 자막·카드 본문 KoPub 돋움 Bold(`shared.fonts.kopub_bold_css`). AI 가 한글을 그리게 하지 않는다. 헤드리스 렌더는 `Emulation.setDeviceMetricsOverride` 로 크기를 고정한다(창 크기만 주면 높이가 모자란다).
- 쿠팡 파트너스 등 제휴가 걸린 내용은 고지문을 넣고, 학과 해시태그(#세명대학교 #재난안전학과)는 붙이지 않는다. 스레드는 `threads_post.compose(..., notice=고지문)` 로 넣는다.
- 네이버 카테고리는 실제 목록 이름 그대로 쓴다: `https://m.blog.naver.com/api/blogs/studs23/category-list`.
- Blogger 는 하루 2편 상한(`post_blogger._posted_today`). 수동 글 때문에 저녁 자동 글이 밀리면 사용자에게 알린다.
- X 는 링크 글이 13배 비싸 링크를 넣지 않고 영상을 첨부한다.
- 크롬을 쓰는 예약 작업과 시각이 겹치지 않게 한다(18:50 티스토리, 19:00 네이버, 20:00 유튜브 등).
- 사용자에게 보이는 모든 글은 한국어로 쓴다.

## 영상 제작 (2026-10-15)
- 편집은 Remotion 스킬로 한다(remotion-best-practices 먼저). ffmpeg 는 소스 준비에만.
- 영상마다 디오라마 이미지 2~3장(아이소메트릭 미니어처, 그림 안 글자 없음, 글자는 편집에서 얹음). 자세한 기준은 AutoSNS/CLAUDE.md.

## 순서
1. 출처를 조사하고 사실 목록을 정리한다.
2. 인포그래픽·화면 캡처를 만들고 렌더 결과를 직접 열어 확인한다.
3. 네이버는 `publish(data, dry_run=True)` 를 먼저 돌려 `logs/*after_typing*`, `*top_preview*`, `*publish_layer*` 스크린샷을 본다. 본문 확인(`_verify_document`)이 빠진 내용을 알리면 발행하지 않는다.
4. 실제 발행한다.
5. 검증한다: 네이버는 글 목록 API(`m.blog.naver.com/api/blogs/studs23/post-list`)에서 제목·카테고리, Blogger 는 공개 주소의 그림·영상 수. '발행 완료(추정)' 로그만으로 끝났다고 하지 않는다.

## 멈추고 물을 때
- 대상 채널이 모호할 때
- 학과 공식 계정에 제휴·광고성 콘텐츠를 올릴 때
- 이미 발행된 글을 지우거나 덮어써야 할 때

## 보고
발행 주소, 카테고리·태그, 들어간 그림·영상 수, 확인한 출처를 한국어로 보고한다. 검증하지 못한 항목은 그렇다고 적는다.
