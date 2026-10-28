"""친구 요청 작업의 실행 전 점검 — 접수가 없으면 AI(claude)를 아예 부르지 않는다.

    python3 precheck_friend.py survey|civil|building|safety

engineer-question-worker/queue.py sync 로 Netlify 접수를 받아 오고(원래 작업의 첫 단계와 같다), 처리할 요청
(queued·processing·published)이 있는지 본다. 종료 코드: 0 = 할 일 있음(작업을 돌린다), 3 = 접수 없음(건너뛴다),
그 밖 = 확인 실패(건너뛰지 않고 작업을 돌려 에이전트가 판단하게 한다). 출력은 JSON 한 줄.
10-18~19 접수가 없어도 한 번에 약 $0.26(API 환산) 어치 한도를 쓰던 것을 줄이려고 만들었다(2026-10-19 비용 검토).
"""
import json
import subprocess
import sys
from pathlib import Path

Q = Path(__file__).resolve().parents[1] / "engineer-question-worker" / "queue.py"


def main():
    exam = sys.argv[1] if len(sys.argv) > 1 else ""
    if exam not in ("survey", "civil", "building", "safety"):
        print(json.dumps({"status": "error", "message": "사용법: precheck_friend.py survey|civil|building|safety"}, ensure_ascii=False))
        return 2
    p = subprocess.run([sys.executable, str(Q), "--exam", exam, "sync"], capture_output=True, text=True, timeout=180)
    try:
        d = json.loads(p.stdout)
        pending = d.get("pending") or []
    except ValueError:
        print(json.dumps({"status": "error", "message": ((p.stderr or p.stdout).strip() or "출력 없음")[-200:]}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "pending" if pending else "empty", "added": d.get("added", 0), "pending": len(pending)}, ensure_ascii=False))
    return 0 if pending else 3


if __name__ == "__main__":
    sys.exit(main())
