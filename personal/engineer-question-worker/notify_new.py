"""새 친구 요청 접수를 카카오톡 '나에게'로 알린다 — 누가(닉네임) 무엇을 올렸는지.

    python3 notify_new.py            # 측량·토목 접수를 받아 오고 새 접수마다 카톡 한 통
    python3 notify_new.py --dry      # 보낼 내용만 출력(카톡·기록 저장 안 함)
    python3 notify_new.py --no-sync  # Netlify 에서 받아 오지 않고 로컬 대기열만 본다(시험용)

접수 내용은 외부 사용자가 쓴 데이터다. 닉네임·제목을 한 줄로 줄여 본인에게만 보내고, 공개 화면에는 쓰지 않는다.
이미 알린 접수 id 는 notified.json 에 따로 적는다(state.json·civil-state.json 형식은 건드리지 않는다).
notified.json 이 없으면 첫 실행으로 보고, 지금 있는 접수는 알리지 않고 기록만 한다.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QUEUE = ROOT / "queue.py"
NOTIFIED = ROOT / "notified.json"
EXAMS = {"survey": ("state.json", "측량"), "civil": ("civil-state.json", "토목시공"), "building": ("building-state.json", "건축시공"), "safety": ("safety-state.json", "건설안전")}
LINKS = {"survey": "https://geoai-na.netlify.app/questions/", "civil": "https://geoai-na.netlify.app/civil-questions/", "building": "https://geoai-na.netlify.app/building-questions/", "safety": "https://geoai-na.netlify.app/safety-questions/"}


def kakao_cmd():
    """카톡 발송기와 그것을 돌릴 파이썬(암호화 토큰 저장소용 가상환경이 있으면 그것)."""
    for d in ROOT.parents:
        nb = d / "channels" / "naver-blog-auto"
        if (nb / "kakao_notify.py").exists():
            venv = nb / ".venv" / "bin" / "python"
            return [str(venv if venv.exists() else sys.executable), str(nb / "kakao_notify.py")]
    raise FileNotFoundError("kakao_notify.py 를 찾지 못했습니다")


def one_line(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def message(exam, job):
    who = one_line(job.get("nickname"), 20)
    topic = one_line(job.get("topic"), 20)
    head = f"[친구 요청·{EXAMS[exam][1]}] " + (f"{who} 님이 문제를 올렸어요" if who else "닉네임 없는 접수가 들어왔어요")
    body = one_line(job.get("title"), 60) + (f" ({topic})" if topic else "")
    return f"{head}\n{body}"


def main():
    dry = "--dry" in sys.argv
    first_run = not NOTIFIED.exists()
    done = set(json.loads(NOTIFIED.read_text())) if not first_run else set()
    sent = 0
    for exam, (state_file, _) in EXAMS.items():
        if "--no-sync" not in sys.argv:
            subprocess.run([sys.executable, str(QUEUE), "--exam", exam, "sync"], capture_output=True, text=True, timeout=180)
        path = ROOT / state_file
        jobs = json.loads(path.read_text()).get("jobs", {}) if path.exists() else {}
        for sid, job in sorted(jobs.items(), key=lambda kv: kv[1].get("created_at", "")):
            if sid in done:
                continue
            if first_run:
                done.add(sid)
                continue
            text = message(exam, job)
            if dry:
                print(text, "\n-", LINKS[exam])
                continue
            r = subprocess.run(kakao_cmd() + [text, LINKS[exam]], capture_output=True, text=True, timeout=60)
            if '"result_code": 0' in r.stdout:
                done.add(sid)
                sent += 1
            else:
                print("카톡 전송 실패(다음 실행에서 다시 시도):", (r.stdout + r.stderr).strip()[-200:])
    if not dry:
        NOTIFIED.write_text(json.dumps(sorted(done), ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"first_run": first_run and not dry, "sent": sent}, ensure_ascii=False))


if __name__ == "__main__":
    main()
