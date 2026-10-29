# AutoSNS — 에이전트 공통 규칙

이 저장소에서 일하는 모든 에이전트(Codex 자동화, Claude 세션 등)가 지킨다. 사용자에게 보이는 글은 한국어로 쓴다.

## 크롬 프로필·발행 작업은 잠금을 거친다 (2026-10-18)

같은 크롬 프로필을 두 작업이 동시에 열면 로그인이 풀리거나 글이 섞인다(10-17 티스토리 충돌, 10-18 네이버 자동저장 섞임).
크롬 프로필을 여는 작업, 블로그·SNS 에 글을 올리는 작업은 반드시 `shared/axlock.py` 를 거쳐 실행한다.

```bash
python3 shared/axlock.py run --job <작업이름> --res profile:<프로필> -- <명령> …
```

계정별 로그인 브라우저 2개로 합쳤다(2026-10-28 사용자 지정). 자원 이름은 그대로 쓰고, 같은 계정 프로필은 잠금 하나로 묶인다.

| 프로필 이름 | 실제 폴더 |
|---|---|
| `profile:naver` `profile:insta` `profile:tiktok` `profile:youtube-dept` `profile:insta-manual` | `~/.autosns-login/dept` (학과) |
| `profile:safeworking` `profile:tistory` `profile:youtube-personal` | `~/.autosns-login/personal` (개인) |

옛 `chrome-profile*` 폴더는 위 폴더를 가리키는 심볼릭 링크다. 원본 세션은 같은 자리의 `*.bak-20261028` 에 있다(되돌리려면 링크를 지우고 이름을 되돌린다).
**바탕화면 `로그인-학과.app`·`로그인-개인.app` 으로 연 브라우저가 열려 있는 동안은 같은 폴더를 쓰는 자동 작업이 기다리다 건너뛴다.** 로그인이 끝나면 그 브라우저를 닫는다.

- 다른 작업이 쓰는 중이면 비기를 기다린다(기본 40분). 작업이 끝나면 크롬을 닫는다.
- **비상 정지** 중(`ax-console/data/STOP.json` 이 있음)에는 발행 작업을 시작하지 않는다. 상태: `python3 shared/axlock.py status`
- launchd 자동 작업의 `run_*.sh` 는 맨 앞 한 줄로 이미 이 규칙을 따른다. 그 줄을 지우지 않는다.
- 실행 현황·비상 정지는 AX 발행 콘솔(http://127.0.0.1:8700 '자동 작업' 탭)에서도 본다.
