# AutoSNS — 에이전트 공통 규칙

이 저장소에서 일하는 모든 에이전트(Codex 자동화, Claude 세션 등)가 지킨다. 사용자에게 보이는 글은 한국어로 쓴다.

## 크롬 프로필·발행 작업은 잠금을 거친다 (2026-10-18)

같은 크롬 프로필을 두 작업이 동시에 열면 로그인이 풀리거나 글이 섞인다(10-17 티스토리 충돌, 10-18 네이버 자동저장 섞임).
크롬 프로필을 여는 작업, 블로그·SNS 에 글을 올리는 작업은 반드시 `shared/axlock.py` 를 거쳐 실행한다.

```bash
python3 shared/axlock.py run --job <작업이름> --res profile:<프로필> -- <명령> …
```

| 프로필 이름 | 폴더 |
|---|---|
| `profile:naver` | dept/naver-blog-auto/chrome-profile |
| `profile:safeworking` | dept/naver-blog-auto/chrome-profile-safeworking (개인 네이버 블로그) |
| `profile:tistory` | personal/naver-blog-auto/chrome-profile-tistory |
| `profile:insta` | dept/insta-cardnews/chrome-profile-insta (인스타·스레드) |
| `profile:tiktok` | dept/youtube-shorts-auto/chrome-profile-tiktok |
| `profile:youtube-personal` / `profile:youtube-dept` | dept/youtube-shorts-auto/chrome-profile-youtube(-dept) |

- 다른 작업이 쓰는 중이면 비기를 기다린다(기본 40분). 작업이 끝나면 크롬을 닫는다.
- **비상 정지** 중(`ax-console/data/STOP.json` 이 있음)에는 발행 작업을 시작하지 않는다. 상태: `python3 shared/axlock.py status`
- launchd 자동 작업의 `run_*.sh` 는 맨 앞 한 줄로 이미 이 규칙을 따른다. 그 줄을 지우지 않는다.
- 실행 현황·비상 정지는 AX 발행 콘솔(http://127.0.0.1:8700 '자동 작업' 탭)에서도 본다.
