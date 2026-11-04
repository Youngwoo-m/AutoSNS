# 개인 티스토리 파일 합치기 (이동안 2단계) 계획

> 이 문서는 계획이다. 실행은 사용자가 시간대와 방식을 정한 뒤에 한다. 실제 발행·로그인·외부 호출은 하지 않는다.

**목표:** 티스토리 실행 파일의 원본을 `personal/naver-blog-auto/` 한 곳으로 모으고, `dept/naver-blog-auto/` 쪽은 같은 이름의 링크로 바꾼다. 로그인 프로필 폴더는 옮기지 않는다.

## 현황 (2026-11-04 점검)
- 같은 내용의 복사본이 두 곳에 있다: `tistory_crosspost/jobs/login/post/rewrite_urls.py`, `run_tistory.sh`, `setup_tistory_schedule.sh`.
- `tistory_patch.py` 는 personal 에만 있다. `common.py`·`config.example.json`·`requirements.txt` 는 `channels/naver-blog-auto/` 로 가는 링크다.
- launchd `com.smuds.tistory` 는 `dept/naver-blog-auto/run_tistory.sh` 를 부른다(WorkingDirectory 도 dept).
- `common/shared/axlock.py` 의 `_LINKS['tistory']` 는 `personal/naver-blog-auto/chrome-profile-tistory`, `ACCOUNT_OF['tistory']` 는 `personal` 로 이미 맞다.

## 지키는 것
- 실행 시각은 10:00~17:00. 06~09, 17~19, 23시 회차를 피한다.
- 시작 전 `python3 shared/axlock.py status` 로 잠금·STOP 확인. 크롬을 여는 시험은 `axlock.py run --res profile:tistory` 로만.
- `git add -A` 금지, 파일을 지정해 커밋. 단계마다 되돌릴 태그를 만든다. 푸시·병합은 승인 후.
- 학과 파일은 링크로 바뀌는 `dept/naver-blog-auto/tistory_*` 와 `run_tistory.sh`·`setup_tistory_schedule.sh` 만 건드리고, 학과 세션에 먼저 알린다.

## 작업
- [ ] **T1 사전 확인(읽기)**: 두 폴더의 대상 파일 `cmp` 재확인, `launchctl list | grep smuds.tistory` 로 상태 확인, `run_tistory.sh` 안의 상대·절대 경로 목록 작성.
- [ ] **T2 경로 수정 준비**: `personal/…/run_tistory.sh` 가 `common.py`·`.venv`·`config` 를 `dept` 기준으로 찾는지 확인하고, 필요한 경우에만 `cd`/`ROOT` 를 고친다. `--plan`/`--dry` 로 한 번 돌려 본다(발행 금지).
- [ ] **T3 plist 변경**: `~/Library/LaunchAgents/com.smuds.tistory.plist` 의 ProgramArguments·WorkingDirectory 를 `personal/naver-blog-auto` 로 바꾼 사본을 만들고, 사용자 승인 뒤 `launchctl bootout` → `bootstrap` 으로 재등록. 이전 plist 는 `.bak-20261104` 로 보관.
- [ ] **T4 dept 쪽 링크화**: 다음 회차가 정상으로 끝난 것을 확인한 뒤 `dept/naver-blog-auto/tistory_*`·`run_tistory.sh`·`setup_tistory_schedule.sh` 를 personal 로 가는 심볼릭 링크로 교체. `tistory_patch.py` 도 같은 방식으로 맞춘다.
- [ ] **T5 문서·잠금 문구**: `docs/개인계정_이동안.md` 현황과 `AGENTS.md`·`docs/폴더지도.md` 의 티스토리 경로를 갱신한다.
- [ ] **T6 확인**: 다음 정기 회차 로그, `axlock.py status`, Node·Python 시험 재실행.

## 되돌리기
plist `.bak` 복원 후 재등록, dept 링크를 원래 파일로 되돌리거나 단계 태그로 `git checkout`. 프로필 폴더는 건드리지 않으므로 로그인은 유지된다.

## 사용자 몫
- T3 재등록과 시간대 승인.
- 티스토리(카카오) 로그인이 풀려 있으면 직접 로그인.
