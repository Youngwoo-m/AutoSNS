# AX 발행 콘솔

학과·개인 계정의 글쓰기, 영상 제작, 업로드, 예약 발행을 한 화면에서 다루는 로컬 콘솔.

| 폴더 | 내용 | git |
|---|---|---|
| `docs/` | 설계 문서 (`설계.md`) | 올림 |
| `design/` | 화면 시안 HTML | 올림 |
| `app/` | 콘솔 코드. 지금은 대시보드 생성기 `build_dashboard.py` 하나 | 올림 |
| `data/dashboard/` | 생성된 대시보드 `index.html` (발행할 때마다 다시 만들어짐) | 제외 |
| `data/content/` | 콘텐츠 원문·매체별 변환본 (`YYYY/MM/<콘텐츠ID>/`) | 제외 |
| `data/media/` | 디오라마 이미지·썸네일·렌더된 영상 (`YYYY/MM/<콘텐츠ID>/`) | 제외 |
| `data/runs/` | 발행 실행 기록·로그 (`YYYY-MM-DD.jsonl`) | 제외 |
| `data/analytics/` | 매체별 성과 수집 결과 | 제외 |

`data/` 는 실행할 때 생기는 산출물이라 git 에 올리지 않는다. 백업은 `backup_state.sh` 대상에 넣는다.

## 실행

```
python3 ax-console/app/server.py      # http://127.0.0.1:8700
```

- **계정 연결** (첫 화면): 학과·개인 구글 토큰(유튜브·블로거·서치콘솔) 상태와 실제 연결된 채널·블로그, 로그인 버튼(기존 인증 스크립트 실행)
- **작업**: 학과/개인 → 채널을 고르고 수행 내용 입력·수정, 실행 작업 선택, 예약 걸기, 지금 실행, 실행 기록 보기
- **예약 목록**: 콘솔 예약과 launchd 자동 작업을 앞으로 8일치 시간순으로 (계정·채널·출처로 거르기)
- **설정**: 계정 정보 수정, 비밀값 저장 여부, 플러그인 켜기/끄기, 커넥터, 설치된 스킬
- 서버는 launchd `com.smuds.axconsole` 로 로그인할 때 켜지고, 꺼지면 30초 안에 다시 켜진다.
  다시 시작: `launchctl kickstart -k gui/$(id -u)/com.smuds.axconsole` · 로그: `data/logs/server.*.log`
- 예약은 서버가 켜져 있을 때만 실행된다(USB가 빠져 있으면 서버도 못 켠다). `data/tasks.json` 에 작업, `data/runs/` 에 실행 기록이 쌓인다.
