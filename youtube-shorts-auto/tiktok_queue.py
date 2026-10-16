"""학과 숏츠를 유튜브에 올리고 30분 뒤 틱톡(@smuds2025)에 올린다(launchd com.smuds.tiktok.queue, 15분마다).

담기: 학과 유튜브 채널에 숏츠가 올라갈 때 add() 가 대기열에 넣는다. 게시 시각 = 유튜브 공개 + 30분.
  - youtube_upload.upload (수·토 뉴스, 속보, 수동 업로드) — 학과 채널·공개일 때만
  - publish_career.py (화 퀴즈·진로)
  - /Volumes/USB256/shorts-disaster/tools/publish.py (재난 숏츠 — 예약 공개 시각 + 30분, AI 아바타 표시)
  개인 GeoAI 채널 숏츠도 담는다(2026-10-12 사용자 요청). 제휴(쿠팡) 고지가 있는 영상은 빼고 담는다.

올리기(main): 게시 시각이 지난 것 중 가장 오래된 1편. 틱톡끼리는 3시간 이상 띄운다(같은 날
여러 편이 몰리면 서로 노출을 나눠 갖는다 — 화요일은 재난 숏츠·퀴즈가 겹친다). 14일 넘은 것은 버린다.

설명(make_caption): 틱톡 전용 — 질문형 첫 줄 + 내용 한 줄 + 댓글 유도 + 해시태그 5개, 주소 없음
(틱톡 설명의 링크는 눌리지 않는다). 위치는 '충북제천'. AI 아바타 영상은 'AI 생성 콘텐츠' 표시.

  python tiktok_queue.py          # 실제 게시(스케줄이 부른다)
  python tiktok_queue.py --plan   # 지금 무엇을 올릴지, 설명은 어떻게 나오는지만 본다
"""
import datetime as dt
import json
import os
import re
import sys

from common import BASE_DIR, load_config, log

QUEUE = os.path.join(BASE_DIR, "posts", "tiktok_queue.json")
MAX_AGE_DAYS = 14
MAX_TRIES = 5          # 틱톡 화면이 간헐적으로 늦게 떠 3번으로는 멀쩡한 영상도 멈췄다(10/15)
DELAY_MIN = 30          # 유튜브 공개 뒤 틱톡까지
GAP_HOURS = 3           # 틱톡 게시 사이 최소 간격(밀린 영상 기준)
GAP_FRESH_HOURS = 1     # 새 영상끼리는 1시간 — 화요일 GeoAI(08:10)·재난 숏츠(08:30)가 붙는다
HOURS = (7, 23)         # 이 시간대에만 올린다(간격 때문에 새벽으로 밀리지 않게)

CAPTION_SYSTEM = """너는 세명대학교 재난안전학과 틱톡 계정의 캡션 작성자다.
주어진 영상 제목·설명만 근거로 쓴다. 없는 수치·장소·사실을 만들지 않는다. 짧을수록 좋다.

정확히 4줄만 출력한다. 다른 말은 쓰지 않는다.
1줄: 스크롤을 멈추게 하는 질문형 첫 줄. 30자 이내. 이모지는 최대 1개.
2줄: 영상에서 알 수 있는 것 한 문장. 40자 이내.
3줄: 댓글을 부르는 한 줄. 25자 이내, 👇로 끝낸다. 퀴즈면 "정답은 O? X? 댓글로 👇",
     그 밖에는 시청자 경험·지역을 묻는다(예: "우리 동네는 대비돼 있나요? 👇").
4줄: 해시태그 정확히 5개를 공백으로 구분. #재난안전학과 와, #제천 또는 #충북 중 하나를 반드시 넣는다.
링크·주소·"#Shorts"는 넣지 않는다.

예)
제목: [재난안전 O·X] 인공호흡 자신 없으면 CPR 하면 안 된다?
인공호흡 못 하면 CPR도 하지 말아야 할까요? 🫀
가슴압박만 해도 생명을 살릴 수 있어요.
정답은 O? X? 댓글로 👇
#심폐소생술 #CPR #응급처치 #재난안전학과 #충북"""


def _load():
    try:
        with open(QUEUE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(q):
    os.makedirs(os.path.dirname(QUEUE), exist_ok=True)
    tmp = QUEUE + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)
    os.replace(tmp, QUEUE)


def add(video, title, description="", hashtags=(), ai_generated=False, not_before=None, source="", backfill=False, notice=""):
    """대기열에 한 편 넣는다. 어떤 경우에도 예외를 올리지 않는다(발행 흐름을 막지 않게)."""
    try:
        if not ((load_config().get("tiktok_web") or {}).get("daily", True)):
            return False
        video = os.path.abspath(video or "")
        if not os.path.exists(video):
            return False
        q = _load()
        if any(e["video"] == video for e in q):
            return False
        from tiktok_web import already_posted
        if already_posted(video):
            return False
        q.append({"video": video, "title": (title or "").strip(), "description": (description or "")[:600],
                  "hashtags": [t for t in (hashtags or []) if t and t.lower() != "shorts"],
                  "ai_generated": bool(ai_generated),
                  "not_before": ((dt.datetime.fromisoformat(not_before) if not_before else dt.datetime.now())
                                 + dt.timedelta(minutes=DELAY_MIN)).isoformat(timespec="seconds"),
                  "source": source, "backfill": bool(backfill), "notice": (notice or "").strip(),
                  "added": dt.datetime.now().isoformat(timespec="seconds"),
                  "posted": None, "tries": 0})
        _save(q)
        log(f"틱톡 대기열에 추가: {os.path.basename(video)} — {title[:40]}")
        return True
    except Exception as e:  # noqa: BLE001
        log(f"틱톡 대기열 추가 실패(발행은 정상): {type(e).__name__}: {str(e)[:100]}")
        return False


CROSS_LINE = "📌 유튜브·블로그 등 전 채널 모음 👉 url.kr/gitdat"


def _fallback_caption(e):
    title = re.sub(r"\s*\|.*$", "", re.sub(r"\s*#Shorts\b", "", e["title"], flags=re.I)).strip()
    first = re.split(r"(?<=[.!?。])\s+", (e.get("description") or "").strip())[0][:45]
    tags = [t for t in e.get("hashtags", []) if t not in ("세명대학교", "재난안전학과")][:3]
    tags += ["재난안전학과", "제천"]
    cta = "정답은 O? X? 댓글로 👇" if ("O·X" in e["title"] or "OX" in e["title"]) else "여러분 생각은 어떤가요? 👇"
    return "\n".join(x for x in [title[:40], first, cta, " ".join("#" + t for t in tags[:5])] if x)


def make_caption(e, cfg=None):
    cfg = cfg or load_config()
    text = ""
    try:
        sys.path.insert(0, os.path.dirname(BASE_DIR))
        from shared.llm import client
        msg = client(cfg).messages.create(
            model=cfg.get("model", "claude-sonnet-4-6"), max_tokens=200, system=CAPTION_SYSTEM,
            messages=[{"role": "user", "content": f"제목: {e['title']}\n설명: {e.get('description','')[:400]}\n"
                                                  f"참고 태그: {', '.join(e.get('hashtags', [])[:10])}"}])
        lines = [ln.strip() for ln in msg.content[0].text.strip().splitlines() if ln.strip()]
        if (len(lines) == 4 and len(lines[0]) <= 40 and 4 <= lines[3].count("#") <= 6
                and "http" not in " ".join(lines)):
            text = "\n".join(lines)
    except Exception as ex:  # noqa: BLE001
        log(f"틱톡 설명 생성 실패 → 기본 형식: {type(ex).__name__}")
    text = text or _fallback_caption(e)
    if e.get("notice"):                    # 제휴 고지 등 반드시 실릴 문구 — 해시태그 바로 위
        lines = text.split("\n")
        lines.insert(len(lines) - 1, e["notice"])
        text = "\n".join(lines)
    if e.get("ai_generated"):
        lines = text.split("\n")
        lines.insert(len(lines) - 1, "※ 진행자 모습과 목소리는 AI로 합성한 아바타입니다.")
        text = "\n".join(lines)
    # 채널 간 상호 언급. 틱톡 캡션의 주소는 클릭되지 않으므로 외우기 쉬운 단축주소로 적는다.
    if CROSS_LINE and CROSS_LINE not in text:
        lines = text.split("\n")
        lines.insert(len(lines) - 1, CROSS_LINE)
        text = "\n".join(lines)
    return text


def pick(q, now=None):
    now = now or dt.datetime.now()
    if not (HOURS[0] <= now.hour < HOURS[1]):
        return None, f"게시 시간대({HOURS[0]}~{HOURS[1]}시) 밖"
    last = max(((e.get("posted") or {}).get("at", "") for e in q), default="")
    since = (now - dt.datetime.fromisoformat(last)) if last else dt.timedelta(days=99)
    if since < dt.timedelta(hours=GAP_FRESH_HOURS):
        return None, f"직전 게시({last[11:16]}) 뒤 {GAP_FRESH_HOURS}시간이 안 지남"
    cutoff = (now - dt.timedelta(days=MAX_AGE_DAYS)).isoformat()
    ready = [e for e in q if not e.get("posted") and not e.get("skipped") and e.get("tries", 0) < MAX_TRIES
             and e["added"] >= cutoff and (e.get("not_before") or "") <= now.isoformat()
             and os.path.exists(e["video"])]
    if not ready:
        left = [e for e in q if not e.get("posted")]
        return None, f"올릴 편 없음(대기 {len(left)}편)"
    # 새로 올라온 영상(유튜브 공개 30분 뒤)이 먼저, 밀린 영상(backfill)은 빈 시간에.
    # priority: 사용자가 바로 올리라고 한 영상(10/15 홍보 영상) — 밀린 새 영상보다 먼저.
    e = sorted(ready, key=lambda e: (e.get("backfill", False), not e.get("priority"), e["not_before"]))[0]
    if e.get("backfill") and since < dt.timedelta(hours=GAP_HOURS):
        return None, f"직전 게시({last[11:16]}) 뒤 {GAP_HOURS}시간이 안 지나 밀린 영상은 쉼"
    if e.get("backfill"):
        soon = (now + dt.timedelta(hours=GAP_HOURS)).isoformat()
        if any(not x.get("posted") and not x.get("backfill") and now.isoformat() < x["not_before"] <= soon
               for x in q):
            return None, f"{GAP_HOURS}시간 안에 새 영상이 올라갈 차례 — 밀린 영상은 쉼"
    return e, ""


def main(argv):
    q = _load()
    e, why = pick(q)
    if "--plan" in argv:
        if not e:
            print(f"올릴 편 없음 — {why}")
            return 0
        print(f"오늘 올릴 편: {os.path.basename(e['video'])} ({e['source']})\n---\n{make_caption(e)}")
        return 0
    if not e:
        log(f"틱톡 하루 1편: {why}")
        return 0
    if not ((load_config().get("tiktok_web") or {}).get("daily", True)):
        log("틱톡 하루 1편: tiktok_web.daily 꺼짐 — 건너뜀")
        return 0
    from tiktok_web import upload
    caption = make_caption(e)
    log(f"===== 틱톡 게시: {os.path.basename(e['video'])} =====")
    try:
        r = upload(e["video"], caption, post=True, ai_generated=e.get("ai_generated", False))
    except BaseException as ex:  # noqa: BLE001
        # 크롬·연결 문제는 영상 탓이 아니다 — 시도 횟수에 넣지 않는다(10/12~15 크롬이 멈춰
        # 대기열 전체가 3회 실패로 멈췄다). 화면·게시 단계 실패만 센다.
        infra = type(ex).__name__ in ("SessionNotCreatedException", "WebDriverException",
                                      "ConnectionRefusedError", "MaxRetryError") \
            or "Chrome 디버깅 포트" in str(ex) or "Chrome 재시작함" in str(ex)
        if not infra:
            e["tries"] = e.get("tries", 0) + 1
            _save(q)
        why = "크롬 연결" if infra else f"{e.get('tries', 0)}/{MAX_TRIES}"
        log(f"===== 틱톡 게시 실패({why}, 다음 실행에서 다시): {type(ex).__name__}: {str(ex)[:150]} =====")
        return 1
    e["posted"] = {"at": dt.datetime.now().isoformat(timespec="seconds"), "caption": caption,
                   "status": r.get("status")}
    _save(q)
    log(f"===== 틱톡 게시 완료: {e['title'][:40]} =====")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
