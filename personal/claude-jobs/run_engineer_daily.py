"""건축·안전 정기 작업: 기존 AX 잠금과 Claude 구독으로 실행한다."""
import argparse
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
JOBS = ("building-daily", "safety-daily")
CLAUDE = "/usr/local/bin/claude"
BLOCKED_ENV = ("ANTHROPIC_", "CLAUDE_CODE_USE_", "AWS_", "GOOGLE_", "AZURE_")
RULES = """
# 이번 실행에서 우선하는 사용자 제한
- 개인 계정의 Claude Max 구독만 사용한다. API 키·학교 게이트웨이·외부 유료 모델·이미지 크레딧을 사용하지 않는다.
- shared/llm.py 라우터, Anthropic/OpenAI SDK, 게이트웨이 생성기와 유료 fallback을 호출하지 않는다. 생성·편집·독립 Agent 검토는 현재 Claude 구독 안에서만 한다. 구독 한도/인증 실패 시 자료를 보존하고 실패로 기록하며 우회하지 않는다.
- 기존 이미지·로컬 도식·PDF 도구만 사용한다. 새 유료 이미지·영상·음성을 만들지 않는다.
- 공개·예약·불명확 중복을 먼저 확인한다. 직전 회차가 한 채널만 발행됐다면 그 채널은 재발행하지 않고 누락 채널 복구를 먼저 한다. 이미 오늘 완료한 회차가 있으면 새 회차를 만들지 않는다.
- 원고·PDF만 준비된 미발행 회차가 있으면 다음 일차를 새로 생성하지 않는다. 보존된 원고·검산·출처 검토와 현재 파일을 확인해 해당 회차의 검증·발행부터 마무리한다.
- 개인 Blogger 상한과 기존 제외 규칙을 발행 직전 quota:blogger-personal 잠금 안에서 확인한다. 상한·제외 대상을 임의로 바꾸거나 --force로 우회하지 않는다. 한쪽만 성공하면 partial과 채널별 URL을 보존한다.
- 개인 Blogger 발행에는 personal/claude-jobs/publish_engineer_blogger.py --job <현재작업> --html <공개자산원고> --title <제목> --labels <태그> --dry/--go 를 사용한다. 이 도구가 예약·비공개 중복과 일일 상한을 잠금 안에서 확인한다. 이 도구가 blocked이면 raw API나 다른 발행기로 우회하지 않는다.
- 모든 프로필·발행은 원본 shared/axlock.py와 기존 발행기를 사용한다. 사용자가 연 브라우저를 닫지 않는다. STOP 중에는 발행하지 않는다.
- 배포는 기존 함수까지 보존하는 deploy_full 경로만 사용한다. 실제 검산·독립 source-reviewer·PDF 전 페이지·공개 제목/첨부 확인 전에는 완료로 기록하지 않는다.
- 숏츠·카카오톡·친구 요청은 이번 정기 작업 범위에 넣지 않는다. 개인정보·키·쿠키는 출력하지 않는다.
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("job", choices=JOBS)
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args()
    job = next(j for j in json.loads((HERE / "jobs.json").read_text())["jobs"] if j["key"] == args.job)
    label = "claude." + args.job
    command = [CLAUDE, "-p", "--model", job["model"], "--permission-mode", "bypassPermissions",
               "--setting-sources", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
               "--no-session-persistence", "--no-chrome", "--add-dir", "/Volumes/USB256/기술사"]
    if args.plan:
        print(json.dumps({"job": label, "hours": job["hours"], "model": job["model"],
                          "command": command, "run_at_load": False, "paid_fallback": False}, ensure_ascii=False))
        return 0
    if os.environ.get("AX_LOCKED") != "1" or os.environ.get("AX_JOB") != label:
        os.execv(sys.executable, [sys.executable, str(ROOT / "shared/axlock.py"), "run", "--job", label,
                                 "--", sys.executable, str(Path(__file__).resolve()), args.job])
    env = {k: v for k, v in os.environ.items() if not k.startswith(BLOCKED_ENV)}
    env["PATH"] = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    env["TZ"] = "Asia/Seoul"
    logs = HERE / "logs"
    logs.mkdir(exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
    with (logs / (args.job + ".log")).open("a", encoding="utf-8") as log:
        log.write("\n===== " + stamp + " " + label + " 구독 전용 시작 =====\n")
        log.flush()
        auth = subprocess.run([CLAUDE, "auth", "status", "--json"], env=env, cwd="/private/tmp",
                              capture_output=True, text=True, timeout=30)
        try:
            status = json.loads(auth.stdout)
        except ValueError:
            status = {}
        if auth.returncode or not status.get("loggedIn") or status.get("authMethod") != "claude.ai" or status.get("subscriptionType") != "max":
            log.write("구독 인증 확인 실패 — 모델·발행 호출 없이 종료\n")
            return 78
        prompt = (HERE / "공통규칙.md").read_text() + "\n# 작업 지시문\n" + (HERE / "jobs" / (args.job + ".md")).read_text()
        prompt += "\n# 실행 정보\n작업: " + args.job + "\n시각: " + stamp + "\n실제 정기 실행\n" + RULES
        try:
            result = subprocess.run(command, input=prompt, text=True, env=env, cwd=ROOT,
                                    stdout=log, stderr=subprocess.STDOUT, timeout=10800)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
        log.write("\n===== 종료 코드 " + str(code) + "; 유료 fallback 없음 =====\n")
        return code


if __name__ == "__main__":
    sys.exit(main())
