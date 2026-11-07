# 학과 계정 교차 발행 (매일 21시)

(2026-11-06 신규. 사용자 지시: 개인 기술사·GeoAI·안전한국훈련 콘텐츠를 학과 계정에도 싣는다. 원본은 개인 계정에 그대로 두고(복사), 학과 Blogger 와 학과 유튜브에 싣는다. 중복 콘텐츠 불이익을 피하려고 전문 복사가 아니라 **요약 + 원문 링크**로 싣는다. 실행 수단은 공통 규칙이 우선)

## 대상 — 오늘(한국 날짜) 개인 계정에 공개된 것만

| 원본 작업 | 어디서 찾나 | 학과 Blogger | 학과 유튜브 |
|---|---|---|---|
| survey-daily · civil-daily · building-daily · safety-daily | `state/<작업>.jsonl` 의 오늘 `status: "published"` 줄(urls) | 요약 글 1편 | 그날 숏츠가 있으면 재업로드 |
| survey-shorts | `state/survey-shorts.jsonl` 의 오늘 줄(video_id, related_blog_url) | — | 재업로드 |
| geoai.daily · geoai.evening (geoai_daily.py, 상태 파일 없음) | `published_history.py --channel blogger-personal,youtube-personal --days 1` | 요약 글 1편 | 그날 GeoAI 숏츠가 있으면 재업로드 |
| safekorea | `state/safekorea.jsonl` 의 오늘 줄(티스토리 URL) | 요약 글 1편 | — (영상 소개 글이라 영상 없음) |

- `friend`·`nordic`·`engineer-backlog-recovery` 는 대상이 아니다.
- 개인 원본 URL 이 공개 접근(200)되는 것만 싣는다. 열리지 않으면 그 건은 건너뛰고 상태에 남긴다.
- 원본이 아직 공개 전(예약)이거나 오늘 원본 작업이 실패했으면 싣지 않는다 — 과거 글을 소급해서 싣지 않는다(실패 재시도는 아래 '다시 할 때'만).

## 중복 확인 — 매 건 먼저

1. `state/dept-crosspost.jsonl` 에서 같은 `source_url`(글) 또는 `source_video_id`(숏츠)를 찾는다. 해당 채널이 이미 `published`/`duplicate` 면 그 채널은 다시 하지 않는다.
2. `python3 shared/published_history.py --channel blogger-dept,youtube-dept --query <제목 핵심어> --days 14` 로 학과 채널에 같은 제목이 있는지 본다.
3. 발행기 자체도 같은 제목이면 `duplicate` 를 돌려준다. duplicate 는 성공으로 기록하고 다시 올리지 않는다.

## 학과 Blogger 요약 글 (smuds2026.blogspot.com)

- 원본을 열어 읽고 **새로 쓴 요약**을 만든다. 원문 문장·표·그림을 그대로 옮기지 않는다(문장 단위 복사 금지). 분량 400~700자, 원본의 1/3 이하.
- 구성: ① 이 글이 다루는 문제(시험명·회차·교시·문항 또는 GeoAI·훈련 주제) 한 문단 ② 핵심 요점 3~4개(짧은 문단 또는 목록) ③ 학과 학생에게 왜 쓸모 있는지 한두 문장 ④ 원문 안내.
- 원문 링크는 **맨 위와 맨 아래 두 곳**에 넣는다:
  - 맨 위: `<p>이 글은 <a href="원문URL" rel="canonical">재난안전과 GeoAI 블로그의 원문</a>을 요약한 것입니다.</p>`
  - 맨 아래: `<p><a href="원문URL">▶ 전체 답안·그림·PDF는 원문에서 보기</a></p>`
  - Blogger 는 글마다 `<head>` 의 canonical 을 바꿀 수 없으므로 본문 링크의 `rel="canonical"` 과 '요약' 명시로 원본을 분명히 한다.
- 제목: 원본 제목을 그대로 쓰지 않는다. `[요약] ` 을 앞에 붙이고 필요하면 다듬는다(학과 블로그 중복 확인에 같은 제목이 걸리지 않게 하되 내용은 같은 문제임을 알 수 있게).
- 라벨: 첫 라벨 하나만 쓴다(학과 블로그는 라벨 = 카테고리 메뉴) — 기술사 글은 `기술사 공부`, GeoAI 는 `GeoAI`, 안전한국훈련은 `안전한국훈련`.
- 그림을 넣는다면 원본 글의 공개 https 그림 주소만(로컬 경로 금지). 넣지 않아도 된다.
- 기술사 글은 원본의 기출 표기(회차·교시·문항)를 그대로 적고, 원본에 없는 내용을 덧붙이지 않는다. 학습용 예시 표시가 원본에 있으면 요약에도 남긴다.
- 문체는 각 원본 작업 지시문의 문체 요청(전문 필자가 설명하듯, 상투어 금지)을 따른다.
- 발행:
  ```
  cd dept/naver-blog-auto && ./.venv/bin/python dept_blogger_post.py --html work/dept-crosspost/<날짜>-<원본키>.html --title "[요약] …" --labels "기술사 공부" --go --job dept-crosspost
  ```
  `quota:blogger-dept` 잠금을 스스로 잡는다. 학과 블로그는 하루 교차 발행 한도(기본 3편, config `blogger.crosspost_daily_limit`)가 있다 — 한도에 걸리면 남은 건은 `failed`(reason: daily_limit)로 남기고 내일 '다시 할 때'로 넘긴다. 순서는 기술사 하루 한 문제 → GeoAI → 안전한국훈련.
- 발행 뒤 공개 URL 을 열어(200) 제목과 원문 링크 두 개가 보이는지 확인한다.

## 학과 유튜브 숏츠 재업로드

- 그날 개인 채널(@geoai-safety)에 **공개된** 숏츠만. `geoai_short_post.py check --video-id ID` 로 `privacy: public` 을 확인한다. 아직 예약 상태면 이번 실행에서는 건너뛴다.
- 영상 파일은 원본 작업이 남긴 mp4 를 쓴다(작업 폴더·premade 폴더의 `short.mp4`). 파일을 찾지 못하면 다시 만들지 않고 `failed`(reason: no_file)로 남긴다. 다운로드해서 다시 올리지 않는다.
- 영상은 손대지 않는다(다시 인코딩·자르기 금지). 20.0초 초과·가로 영상은 발행기가 거부한다.
- 제목: 원본 제목 그대로(학과 채널에는 같은 제목이 없으므로 중복 아님). 100자 이내, `#Shorts` 유지.
- 설명 **첫 줄**: `원문 해설: <원본 블로그 글 URL>` — 숏츠 상태의 `related_blog_url`, 없으면 같은 날 같은 주제 글. 확인된 공개 URL 이 없으면 원본 숏츠 URL(`https://www.youtube.com/shorts/<원본 id>`)을 쓴다. 그 아래는 원본 설명을 옮기고 맨 끝에 `세명대학교 재난안전학과 채널에 함께 싣습니다.` 한 줄. AI 합성 고지가 원본에 있으면 그대로 남기고 `--synthetic` 을 준다.
- 업로드(지금 공개, 예약 없음):
  ```
  cd dept/youtube-shorts-auto && ./.venv/bin/python dept_short_post.py upload --video <short.mp4> --title "… #Shorts" --description-file work/dept-crosspost/<날짜>-<키>-설명.txt --tags "…" --synthetic --go --job dept-crosspost
  ```
  `profile:youtube-dept` 잠금을 스스로 잡는다. 결과의 video_id 를 기록한다.
- 운영자 댓글: 공개 확인 뒤 `dept_short_post.py comment --video-id <새 id> --text "원문 해설: <URL>" --go --job dept-crosspost`. 이미 있으면 duplicate.

## 다시 할 때 (실패한 채널만)

- 실행마다 먼저 지난 3일치 `state/dept-crosspost.jsonl` 에서 `failed` 채널이 있는 건을 찾는다. 원본이 여전히 공개돼 있으면 **실패한 채널만** 다시 한다. 성공한 채널은 다시 하지 않는다.
- 같은 건이 3번 실패하면 더 시도하지 않고 사용자 조치로 알린다(예: 토큰 재인증).
- 인증 실패(토큰 없음·403·채널 불일치)는 그날 남은 같은 채널 건을 모두 멈추고 한 번만 알린다. 학과 Blogger 403 이면 `--token dept`/config 토큰 중 어느 쪽을 썼는지 상태에 남긴다.

## 기록

`state/dept-crosspost.jsonl` 에 **원본 1건당 한 줄**:
`{"at": "시각", "status": "published|partial|skipped|failed|dry", "title": 원본 제목, "source_job": "civil-daily", "source_url": …, "source_video_id": …, "channels": {"blogger-dept": {"status": "published|duplicate|failed|skipped", "url": …, "title": …, "reason": …}, "youtube-dept": {"status": …, "video_id": …, "url": …, "comment_id": …, "reason": …}}, "urls": {"blogger-dept": …, "youtube-dept": …}, "attempt": 1, "note": …}`
- `urls` 는 `published_history.py` 가 읽는 칸이라 성공한 학과 URL 을 넣는다.
- 오늘 대상이 하나도 없으면 `{"status": "skipped", "note": "오늘 개인 계정 공개 글 없음"}` 한 줄만.

## 알림

새로 실린 학과 URL 과 실패·필요한 사용자 조치만 3줄 이내로 알린다. 변화가 없으면 "변화 없음".
