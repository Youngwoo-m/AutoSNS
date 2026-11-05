# 측량·토목 기술사 과거~오늘 읽기 대조

기준: 2026-10-31 KST. 운영 원본 읽기, 공개 GET만 수행. 원고/기록/queue/프로필/계정/발행 변경0. 보고 및 공개 조회 결과만 /private/tmp 저장. API·모델·크레딧 사용0.

## 판정

- **즉시 재발행할 누락 블로그 원고는 확인되지 않음.** 측량1~22일차, 토목1~14일차가 공개 목록에서 연속. 과거달력상 결행을 일차 공백으로 바꾸어 새 회차를 임의 생성하지 않음.
- 측량22일차(/198)와 토목14일차(/199)는 10/30 사용량 실패 후 오늘10/31 공개된 회차. 오늘 회차를 새로 생성/중복게시하면 안 됨. 다음 회차는 각각23/15지만 완성·독립검토된 미발행 원고는 이번 범위에서 발견되지 않음.
- **과거 측량5일차 영상은 미완료 후보가 남음.** 기존 장편은 현행 사용자 지침상 복구 업로드 금지. 숏츠는 별도 아래 현행 자산 활용후 검산/출처/중복확인 필수.

## 공개 이력 실대조

1. https://geoai-na.netlify.app/questions/published.json: 26항목 = daily1~22(누락없음)+친구요청4.
2. https://geoai-na.netlify.app/civil-questions/published.json: daily1~14 전부.
3. 두 목록의 티스토리40개 URL을 이번에 전부 GET: **40/40 HTTP200, 40/40 HTML에 PDF 링크/첨부표시**. PDF 바이트 전량해시/모든 이미지 품질을 새로 검사한 것은 아님.
4. 티스토리 최신RSS /198 22일차 10/31 06:06:06, /199 14일차 10/31 08:13:05 일치.
5. Blogger 공개 feed max-results500: 총141개 공개글, 토목1~14 전부 존재. 일부채널만 실패한 토목 정기 회차 없음.
6. 캐시가 아닌 이번 공개조회 결과: /private/tmp/engineer-audit-{survey-list,civil-list,blogger,tistory}.json 및 engineer-audit-public-pages.json.

## 오래된 상태의 거짓 누락 주의

작성상태.json만 보면 다음이 partial/private/comment false이나 JSONL 후속 기록에서 이미 복구됨. 재발행/댓글중복 금지.

| 항목 | 최신 복구 증거 |
|---|---|
| 측량20일차 네이버 | survey-daily.jsonl 10/28 20:03 crosspost_naver, /184 → https://blog.naver.com/safeworking/224456995887 공개확인 |
| 토목12일차 네이버 | civil-daily.jsonl 10/28 20:03 crosspost_naver, /186 → https://blog.naver.com/safeworking/224456997528 공개확인 |
| 측량12일차 댓글 | 10/21 08:25 note에 전날 누락 댓글 UgzqbouFeQA3_j2oPrR4AaABAg verified 명시 |
| 측량14~21일차 댓글 | 각날08시 JSONL public/comment_verified true. 별도 작성상태 private/false는 오전06시 스냅샷 |
| 측량22일차 댓글 | 10/31 08:07 public, comment UgzRbCIaYt9-QQdqfzF4AaABAg, verified true |
| 측량11일차 영상 | 원R9mf8kmlXiQ는 사용자 지시삭제, C1vGYCFgcYs 교체완료. 옛ID로 재업로드 금지 |

네이버 교차발행 의무는 공통규칙10/21부터. 그 이전의1~3토목 등에 네이버URL 없다는 이유로 소급미완료 단정하지 않음. 현 네이버공개 40개 전체본문을 이번에 직접확인하지는 않았음.

## 친구 요청

- 원본 GeoAI_NA/engineer-question-worker/state.json jobs4개 모두done. ignored 제외. civil-state.json jobs0.
- survey-friend/civil-friend JSONL 10/30까지 접수없음skip. 현재 로컬 미완료0.
- 원격 Netlify 신규접수 sync는 대기열쓰기가 발생하므로 본 읽기감사에서는 실행하지 않음. 부모가 실제복구 작업에서 필요시 정식queue sync 수행해야 오늘 신규접수까지 확정 가능.

## 측량5일차 영상 미완료 후보

원본 경로: /Volumes/USB256/기술사/05일차_최소제곱조정/영상/
- 영상상태.json: generating, long_video_id/short_video_id null. youtube-result 없음.
- video.mp4 305.92초, 숏츠/short.mp4 35.52초. decode검증만 있고 visual_qa/audio_qa 완료없음.
- 블로그 https://na-geoai.tistory.com/42 는 이미공개, PDF존재. 블로그 재발행금지.
- upload_day05.py/upload_day05_short.py는 직접API insert+구식token경로. 현공통규칙의 geoai_short_post.py 전용경로/잠금/중복/20초 기준을 우회하므로 실행금지.
- survey-daily.md 2026-10-17 변경은 미공개긴영상 제작재개/복구업로드를 명시금지. 이305초장편은 복구범위에서 제외해 보존.

### 현행 재사용 후보 (새 유료그림 불필요)

/Volumes/USB256/devAPP/AutoSNS/GeoAI_NA/engineer-video-output/premade/2026-10-29-survey-am/
- short.mp4(meta15.04초), props.json(Remotion3장면), d1.png/d2.png/d3.png(디오라마3장), voice.wav, 대본.txt, title.txt, description.txt, tags.txt, 장면메모.txt 존재.
- used.txt 없음. 최상위주제 최소제곱법, prev폴더가10/29에쓴정확도·정밀도.
- 명시재사용근거: survey-daily.md 마지막의 “2026-10-29 미리 만든 숏츠 우선”, 같은폴더장면메모의 “그림은 기존d1~d3.png 재사용”. 기존공개블로그원고·출처·그림재사용도 survey-daily 허용.
- 내용: 같은거리다수관측→잔차제곱합최소→정밀도와경중률. 기출128-1-10(2022) 표기. /42는창작연습문제이므로블로그와기출표기를 혼동시키지 않도록 출처독립확인·설명필요. related_blog_url 비어있음.
- calc/source-review 완료파일 발견되지않음. 사용전독립검산/출처검토·렌더/실길이·자막확인필수. 단순35초영상trim은금지.

### 중복·예정 조사

- 공개채널검색 https://www.youtube.com/channel/UCbHDlxMFIackeJRwW2iTYew/search?query=최소제곱 결과는13일차오차전파1건, 정확한5일차최소제곱영상없음.
- 공용 published_history.py의 _youtube(개인채널RSS→fallback공개shorts/videos+oEmbed) 38개와 _local 236개조회: 최소제곱/가중치/정확한5일차 영상일치없음. 문자열5일차는15일차/토목5일차가부분일치했을뿐.
- channels/youtube-shorts-auto/publish_schedule.json 및 title_history.json에 최소제곱/5일차/가중치 예약없음.
- 공개조회는 **비공개·예약을증명못함**. 업로드직전기존공식발행기의대상채널/최신중복검사필수. 이번결과로절대적중복없음을단정하지않음.
- 상세: /private/tmp/engineer-audit-youtube-day5-search.json, /private/tmp/engineer-audit-history-minleastsquares.json.

측량6~9일차 영상별 영상상태.json은 done, long/short ID 및 공개·재생·연결검증존재. 기존공개30~40초영상을현행20초기준으로소급편집/재업로드하지않음.
