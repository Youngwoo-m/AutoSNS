"""학과 소개 영상을 X 에 하루 1편씩 올린다(launchd com.smuds.xpromo.daily, 매일 12:30).

대기열: posts/x_promo/queue.json — [{no, youtube_id, date, video, text, posted}]
  예정일(date)이 오늘이거나 지난 것 중 아직 안 올린 첫 편을 올리고 posted 에 결과를 적는다.
  오늘 이미 한 편 올렸으면 아무것도 하지 않는다(launchd 가 밀린 실행을 몰아 돌려도 하루 1편).
  다 올리면 조용히 끝난다 — 새 편을 넣으려면 대기열에 항목을 더하면 된다.

영상은 우리 채널의 공개 영상을 yt-dlp 로 받은 것(2026-10-06, 7편). 한꺼번에 올리면
X 에서 덜 퍼지고 스팸처럼 보여 하루 1편으로 나눴다. x.enabled 가 꺼져 있으면 건너뛴다.

  python x_promo.py          # 실제 게시(스케줄이 부른다)
  python x_promo.py --plan   # 오늘 무엇을 올릴지만 본다
"""
import datetime as dt
import json
import os
import sys

from common import BASE_DIR, load_config, log

QUEUE = os.path.join(BASE_DIR, "posts", "x_promo", "queue.json")


def _load():
    with open(QUEUE, encoding="utf-8") as f:
        return json.load(f)


def _save(q):
    tmp = QUEUE + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)
    os.replace(tmp, QUEUE)


def pick(q, today=None):
    today = (today or dt.date.today()).isoformat()
    if any((e.get("posted") or {}).get("at", "")[:10] == today for e in q):
        return None, "오늘 이미 한 편 올렸음"
    for e in sorted(q, key=lambda e: (e["date"], e["no"])):
        if not e.get("posted") and e["date"] <= today:
            return e, ""
    left = [e for e in q if not e.get("posted")]
    return None, (f"오늘 몫 없음(남은 {len(left)}편, 다음 {min(e['date'] for e in left)})" if left
                  else "대기열을 모두 올렸음")


def main(argv):
    if not os.path.exists(QUEUE):
        log("X 학과 소개: 대기열 없음")
        return 0
    q = _load()
    ep, why = pick(q)
    if "--plan" in argv:
        print(f"오늘 올릴 편: {ep['no']}번 {ep['text'][:40]}" if ep else f"올릴 편 없음 — {why}")
        return 0
    if not ep:
        log(f"X 학과 소개: {why}")
        return 0
    if not (load_config().get("x") or {}).get("enabled", False):
        log("X 학과 소개: x.enabled 꺼짐 — 건너뜀")
        return 0
    from x_post import post_video
    video = ep["video"] if os.path.isabs(ep["video"]) else os.path.join(BASE_DIR, ep["video"])
    log(f"===== X 학과 소개 {ep['no']}/{len(q)}편 게시 시작 =====")
    r = post_video(ep["text"], video, dry_run=False)
    if r.get("status") == "published":
        ep["posted"] = {"url": r.get("url", ""), "id": r.get("id", ""),
                        "at": dt.datetime.now().isoformat(timespec="seconds")}
        _save(q)
        log(f"===== X 학과 소개 {ep['no']}편 완료: {r.get('url', '')} =====")
        return 0
    log(f"===== X 학과 소개 {ep['no']}편 실패(다음 실행에서 다시): {r.get('error', r)} =====")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
