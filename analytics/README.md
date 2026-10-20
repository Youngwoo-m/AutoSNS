# analytics — 채널별 콘텐츠 활동 집계·리포트

유튜브·인스타그램·네이버 블로그·학과 홈페이지에 올린 콘텐츠를 모아 유형별
(영상·숏츠·이미지·카드뉴스·게시글)로 집계하고, 주간·월간 리포트를 메일로 보낸다.
**전부 읽기 전용이다.** 어떤 채널에도 게시하지 않는다.

## 구성

| 파일 | 역할 | 실행 인터프리터 |
|---|---|---|
| `collect_youtube.py` | 업로드 목록·길이·조회수·구독자 | `channels/youtube-shorts-auto/.venv` |
| `collect_instagram.py` | 게시물·팔로워 (저장된 크롬 세션) | `channels/insta-cardnews/.venv` |
| `collect_web.py` | 블로그·홈페이지 공개 목록 | 시스템 `python3` |
| `build_report.py` | 주간 리포트 HTML + 스냅샷 | 시스템 `python3` |
| `build_monthly.py` | 월간 분석 HTML·md·xlsx | `analytics/.venv` |
| `send_mail.py` | SMTP 발송(첨부 지원) | 시스템 `python3` |

수집기는 서로 import 하지 않는다. 필요한 라이브러리가 달라 인터프리터를 나눠 쓰고,
결과는 `snapshots/parts/*.json` 으로만 주고받는다.

## 실행

```
./run_weekly_report.sh [기준일]                 # 지난 7일
./run_monthly_report.sh [기준일] [대상월]        # 지난 달 (매월 1일 기준)
```

`SMUDS_REPORT_DRYRUN=1` 을 주면 수집·생성만 하고 메일은 보내지 않는다.

## 메일 설정

`mail_config.example.json` 을 `mail_config.json` 으로 복사한 뒤 앱 비밀번호를 넣는다.

```
python3 set_mail_password.py     # 화면에 안 보이게 입력, 셸 기록에도 안 남음
```

앱 비밀번호는 https://myaccount.google.com/apppasswords 에서 발급한다(2단계 인증 필요).
로그인 비밀번호는 구글이 막는다. `mail_config.json` 은 저장소에 올라가지 않는다.

## 정기 실행 (launchd)

발행 잡들과 같은 방식으로 돈다. Claude Code 를 열어두지 않아도 실행된다.

| 잡 | 시각 | plist |
|---|---|---|
| `com.smuds.report.weekly` | 매주 월요일 08:00 | `~/Library/LaunchAgents/com.smuds.report.weekly.plist` |
| `com.smuds.report.monthly` | 매월 1일 08:00 | `~/Library/LaunchAgents/com.smuds.report.monthly.plist` |

```
launchctl load   ~/Library/LaunchAgents/com.smuds.report.weekly.plist
launchctl unload ~/Library/LaunchAgents/com.smuds.report.weekly.plist
launchctl list | grep smuds.report
```

로그는 `logs/launchd.weekly.out.log`, `logs/launchd.monthly.out.log` 와
월별 `logs/YYYY-MM.log` 에 쌓인다.

## 알아둘 것

- 인스타 수집은 발행에 쓰는 크롬 로그인 세션을 그대로 쓴다. 세션이 풀리면 그 채널만
  건너뛰고 리포트에 사실을 표시한다. 로그인은 사람이 직접 해야 한다.
- 홈페이지 게시판은 상단 고정 공지가 모든 페이지에 다시 나온다. `nttId` 로 중복을
  걸러야 건수가 페이지 수만큼 부풀지 않는다.
- 월간 한글 보고서는 `~/.claude/skills/hwpx-skill` 의 `md2hwpx.py` 를 쓴다. 스킬이
  없거나 변환이 실패하면 그 첨부만 빠지고 메일은 나간다.
- 월간 리포트의 해석·제안 문구는 규칙 기반이다(`build_monthly.py` 의 `analyze`).
  사람이 없는 시간에 돌아도 결과가 흔들리지 않아야 해서 매번 새로 짓지 않는다.
