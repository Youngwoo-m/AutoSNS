"""발행 전에 디스크 여유를 확인한다. 부족하면 긴급 정리 → 다시 재고 → 카톡으로 알린다.

9/19 하루 동안 내장 디스크가 가득 차 인스타·GeoAI·네이버·유튜브 발행이 모두 멈췄다
(`No space left on device`, 로그조차 끝까지 못 씀). 매일 04:00 정리는 있었지만 낮 동안
다시 찼다. 그래서 발행 직전에 한 번 더 본다.

- 재는 곳: 내장 디스크(/ — 임시파일·캐시가 쌓이는 곳)와 프로젝트가 있는 볼륨.
- 기준: 2GB. 밑이면 이미 있는 정리 스크립트 두 개를 돌린다(재생성되는 캐시만 지움,
  사용 중인 크롬 프로필은 건너뜀).
- 정리 뒤에도 모자라면 카톡 알림(6시간에 한 번만)과 함께 종료 코드 1 — 발행은 그대로
  진행한다(여기서 막으면 여유가 조금 모자란 날에도 결방이 된다). 결과는 로그로 남는다.

표준 라이브러리만 쓴다 — 실행 래퍼에서 시스템 python3 로 부른다:
    python3 ../shared/diskguard.py <작업이름>
"""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))     # AutoSNS
MIN_GB = 2.0
CLEANERS = [
    os.path.join(ROOT, "maintenance", "prune_chrome_caches.sh"),       # 크롬 프로필 캐시(USB)
    os.path.expanduser("~/bin/mac_auto_cleanup.sh"),                   # 사용자 캐시 등(내장)
]
LOG = os.path.join(ROOT, "maintenance", "logs", "diskguard.log")
STATE = os.path.join(ROOT, "maintenance", "logs", "diskguard_state.json")
NOTIFY_EVERY = 6 * 3600


def _log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass                      # 디스크가 가득 차면 로그도 못 쓴다 — 화면 출력은 남는다


def free_gb():
    """{이름: 여유 GB}. 같은 볼륨이면 한 번만."""
    out, seen = {}, set()
    for name, path in (("내장", "/"), ("프로젝트", ROOT)):
        try:
            dev = os.stat(path).st_dev
        except OSError:
            continue
        if dev in seen:
            continue
        seen.add(dev)
        out[name] = shutil.disk_usage(path).free / 1024 ** 3
    return out


def _cleanup():
    for sh in CLEANERS:
        if os.path.exists(sh):
            try:
                subprocess.run(["/bin/bash", sh], timeout=600,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                _log(f"긴급 정리 실행: {os.path.basename(sh)}")
            except Exception as e:
                _log(f"긴급 정리 실패 {os.path.basename(sh)}: {type(e).__name__}")


def _notify(text):
    try:
        st = json.load(open(STATE)) if os.path.exists(STATE) else {}
    except Exception:
        st = {}
    if time.time() - st.get("last", 0) < NOTIFY_EVERY:
        return
    try:
        # 카톡 토큰은 암호화 저장소에 있고 그걸 열려면 cryptography 가 필요하다. 이 스크립트는
        # 시스템 파이썬(/usr/bin/python3)으로 돌아 그게 없으니 유튜브 venv 로 보낸다(2026-10-17).
        import subprocess
        yt = os.path.join(ROOT, "channels", "youtube-shorts-auto")
        subprocess.run([os.path.join(yt, ".venv", "bin", "python"), "kakao_notify.py", text],
                       cwd=yt, timeout=60, check=True, capture_output=True)
        with open(STATE, "w") as f:
            json.dump({"last": time.time()}, f)
    except Exception as e:
        _log(f"카톡 알림 실패: {type(e).__name__}")


def check(job=""):
    before = free_gb()
    low = {k: v for k, v in before.items() if v < MIN_GB}
    if not low:
        return 0
    _log(f"[{job}] 여유 부족 " + ", ".join(f"{k} {v:.1f}GB" for k, v in low.items())
         + f" (기준 {MIN_GB:.0f}GB) → 긴급 정리")
    _cleanup()
    after = free_gb()
    still = {k: v for k, v in after.items() if v < MIN_GB}
    summary = ", ".join(f"{k} {before[k]:.1f}→{after.get(k, 0):.1f}GB" for k in low)
    if not still:
        _log(f"[{job}] 정리 후 정상: {summary}")
        return 0
    _log(f"[{job}] 정리 후에도 부족: {summary} — 발행은 시도한다")
    _notify(f"[SMUDS 디스크 경고] {job} 발행 전 여유 부족\n{summary}\n"
            "정리 스크립트를 돌렸지만 모자랍니다. 큰 파일을 정리해 주세요.")
    return 1


if __name__ == "__main__":
    sys.exit(check(sys.argv[1] if len(sys.argv) > 1 else ""))
