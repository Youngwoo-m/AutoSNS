# 계정 경로 이행 전 정적 보고서

이 도구는 경로 제안과 미완료 전제조건을 출력한다. 운영 파일 이동, 기존 consumer 교체, alias 제거, 환경 재생성 기능은 없다. 보고서의 `physical_migration_ready`는 항상 `false`다. T10~T12 플래그를 입력해도 실제 이행 가능 상태로 바꾸지 않는다.

`R(source_root)`은 명시 운영 원본 루트, `W(workspace_root)`는 관리 저장소, `code_root`는 이번 도구의 코드 루트다. 모두 절대경로로 지정한다. W는 R 및 code_root와 서로 포함되면 안 된다. R과 code_root가 같은 checkout인 경우는 허용한다. W를 생략해도 보고서는 생성되며, 관리 저장소 미지정을 미완료 항목으로 남긴다. 기존 관리 ContentStore 경로는 변경하지 않는다.

`resolve_layout(account_id, root)`는 파일 접근 없이 계정의 `config_root`, `content_root`, `media_root`, `history_root`와 제안 경로를 계산한다. 계정은 `dept` 또는 `personal`을 명시해야 한다. 빈 값·미등록 값·상대 루트·상위 탈출을 거부하고 개인 기본값을 두지 않는다. root를 명시하면 현재 작업 디렉터리가 달라져도 결과는 같다.

개인 GeoAI 코드의 제안 목적지는 `R/personal/blog-auto`, `R/personal/shorts-auto`다. 현재 존재하는 저장소나 폴더 전체의 이동 지시가 아니다. 원래 ID와 원래 상대경로를 보존하며 이동된 경로로 legacy 식별자를 재발급하지 않는다. 운영 원장은 `W/operations.sqlite3` 하나를 공용으로 유지한다. 공용 코드·자산, 비밀값 저장소, 기존 .venv, 로그인 프로필은 이동에서 제외한다.

다음 예시는 운영 R의 허용 코드만 읽고 결과를 `/private/tmp`에 새 파일로 만든다. Python의 자동 `__pycache__` 쓰기도 막도록 `PYTHONDONTWRITEBYTECODE=1` 또는 `python3 -B`를 사용한다. 출력 파일은 미리 존재하면 안 되며 상위 디렉터리는 이미 있어야 한다.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m common.tools.audit_account_paths \
  --root /Volumes/USB256/devAPP/AutoSNS \
  --code-root /Users/youngwoo/.codex/worktrees/account-automation-design/AutoSNS \
  --output /private/tmp/account-paths-report.json
```

`--workspace-root /명시/관리저장소`를 추가하면 W와의 겹침도 검사한다. 출력 위치는 R/W/code_root 내부를 거부한다. 경로 구성요소의 symlink를 거부하고, `dir_fd`·`O_NOFOLLOW`·배타적 생성으로 코드 파일의 링크 열람과 출력 덮어쓰기를 제한한다. macOS의 `/tmp`처럼 상위 경로가 링크인 경우 `/private/tmp` 형태의 실제 경로를 지정한다.

`CODE_ALLOWLIST`의 Python·shell 코드만 크기를 제한해 읽는다. 디렉터리를 재귀 탐색하지 않고 운영 모듈을 import하지 않는다. config·token·cookie·profile·.venv의 내용은 읽지 않는다. 코드 내용 자체나 환경변수 값은 출력하지 않는다. 결과에는 코드 해시·mtime, 고정 경로 문자열 참조의 줄 번호, 환경변수 이름과 환경의 기호 참조만 남긴다. 환경 manifest의 caller는 `dept/project/job.py`, `run.sh`처럼 저장소 상대 `.py`/`.sh` 경로 형식만 허용한다. 중첩 객체·리스트·환경변수 대입 문자열·상위 탈출·절대경로는 제외한다. `interpreter`와 `cwd`는 정적 후보이며, profile/credential 참조 역시 실제 환경을 검사한 인증 근거가 아니다. 알 수 없는 참조는 `null`, 모든 환경은 `static_unverified`다.

alias 목록은 명시 allowlist에 한정해 `lstat`와 `readlink`로 링크 문자열과 구성요소를 관찰한다. 중첩 링크는 메타데이터로만 해석하고 링크를 따라 디렉터리를 재귀 탐색하지 않는다. 결과의 `resolved`, `not_alias`, `dangling`, `external`, `cycle`, `resolution_limit`을 구별한다. 같은 링크를 다시 만나더라도 남은 경로가 다르면 순환으로 판정하지 않는다. 링크 위치와 남은 경로가 같은 해석 상태를 반복할 때만 `cycle`이며, 40회 해석 상한 도달은 별도의 `resolution_limit`이다. 외부 경로는 존재 여부를 조회하지 않는다. 현재 정적 결과의 caller 0은 전체 caller 부재를 뜻하지 않는다. `can_remove_alias`는 caller 0과 전체 caller 관측 완료 및 별도 관측 확인을 모두 갖춰야만 true다. 도구가 이 확인 필드를 승인 상태로 채우지는 않는다.

`direct_relations`는 허용 코드 안에서 확인한 직접 정적 관계다. Python의 `import module`·`from module import ...`는 해당 모듈의 허용 코드 경로로 연결한다. shell은 `cd "$(dirname "$0")"` 또는 BASH_SOURCE의 동일 형태 뒤에 오는 명시 Python/shell 파일 실행과 절대 파일 실행을 지원한다. 실행 파일 basename만 있어도 cwd가 확인되면 연결한다. 동적 cwd·`-m`/`-c`·동적 entrypoint 등 지원하지 않는 형태는 실행해서 해석하지 않는다. 단순 경로 문자열 포함은 `path_literal_references`로 남겨 직접 caller 관계와 구별한다.

파일의 `alias`는 관측한 alias 목적지가 해당 파일을 가리키는 메타데이터 관계다. alias를 통한 직접 실행·import는 관계의 `via_alias`와 alias의 `callers`로도 연결한다. 파일의 `environment_ref`는 자기 정적 환경 후보와 관측한 caller 환경을 연결하며, 환경 manifest의 `callers`는 파일의 직접 caller 관측을 공유한다. 각 migration 행의 `callers_observation`, `alias_observation`, `environment_ref_observation`을 함께 해석한다. `partial`은 관계를 일부 관측했다는 뜻이고, `observed_zero_in_scope`는 지원하는 정적 문법·명시 allowlist에서 관측한 관계가 0이라는 뜻이다. `unknown`은 동적 cwd나 미해석 코드 등의 이유로 관계를 확인하지 못했다는 뜻이다. 모든 상태의 `complete`는 false이며, 목록 `[]` 자체로 전체 caller·alias·환경의 부재를 뜻하지 않는다.

이동 전에는 wrapper·launchd·지시문·console·자동화 caller의 전체 목록과 환경별 interpreter/cwd/credential/profile의 검증을 완료해야 한다. T10 실행 규칙, T11 adapter 계약, T12 제작 계약의 승인·검증 근거도 별도 확인 대상이다. 기존 wrapper의 axlock 잠금 진입점을 유지하고, 원본 운영 ID·경로·이력의 보존을 검증한 뒤 후속 이행을 별도로 결정한다.

검증 명령은 다음과 같다. 작은 fixture에서 secret 읽기·subprocess·network 호출을 차단하고 파일집합/hash/mtime 불변, 경로/alias/출력 경계를 검증한다.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.operations.test_migration -v
```
