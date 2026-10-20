"""사건 즉시 발행 트리거.

큰 재난이 '지금' 터졌으면 주간 스케줄을 기다리지 않고 유튜브 Shorts 를 즉시 발행한다.
(애널리틱스상 이 채널은 검색 유입 55% → '사건 당일'에 올려야 검색 트래픽을 잡는다.)

판단 로직:
  1) 최근 N시간 기사만 본다.
  2) 같은 사건을 다룬 기사가 여러 개(=여러 언론사 보도 = 큰 사건)이고,
     심각도 키워드(특보/경보/대피/사망/실종/붕괴/규모 등)가 있으면 '발행할 사건'으로 본다.
  3) 이미 그 사건으로 발행했거나(중복), 쿨다운/주간 상한에 걸리면 발행하지 않는다.

안전장치:
  - 유튜브 전용(공식 API). 네이버/인스타는 브라우저 자동화라 잦은 발행 시 계정 정지
    위험이 있어 트리거에서 제외한다(주 1회 유지).
  - 쿨다운(min_hours_between)과 주간 상한(max_per_week)으로 도배를 막는다.
  - --dry 로 실행하면 '발행할지 말지'만 판단해 로그로 알려주고 실제 발행은 안 한다.

launchd 로 몇 시간마다 이 스크립트를 돌린다(setup_trigger_schedule.sh).
"""
import io
import json
import re
import os
import sys
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher

from common import BASE_DIR, load_config, log
from fetch_news import fetch_recent_raw, _norm_title

STATE_PATH = os.path.join(BASE_DIR, "trigger_state.json")

# 심각도 키워드(있으면 '큰 사건' 가점). 재난 상황의 위중함을 나타내는 말.
DEFAULT_SEVERITY = [
    "특보", "경보", "위기경보", "대피", "사망", "실종", "붕괴", "고립", "매몰",
    "특별재난지역", "규모", "실종자", "인명피해", "침수", "산사태", "대형", "총력",
    "긴급", "비상", "통제",
]


def _load_state():
    if os.path.exists(STATE_PATH):
        try:
            return json.load(io.open(STATE_PATH, encoding="utf-8"))
        except Exception:
            pass
    return {"last_trigger": None, "posted": []}  # posted: [{sig, ts}]


def _save_state(state):
    io.open(STATE_PATH, "w", encoding="utf-8").write(
        json.dumps(state, ensure_ascii=False, indent=2))


def _cluster(items, threshold):
    """유사 제목끼리 묶어 [{rep, size, newest, severity}] 로 만든다(큰 순)."""
    clusters = []  # each: {"norm": str, "items": [...]}
    for it in items:
        nt = _norm_title(it.get("title", ""))
        for c in clusters:
            if SequenceMatcher(None, nt, c["norm"]).ratio() >= threshold:
                c["items"].append(it)
                break
        else:
            clusters.append({"norm": nt, "items": [it]})
    return clusters


# 재난 '사건'이 아니라 예방·행정·홍보 기사임을 드러내는 말. 이런 말이 든 제목은
# 심각도 키워드가 있어도 사건으로 치지 않는다('산사태 예방 사방사업 완료' 같은 보도자료).
# 2026-09-01~09-28 트리거 발행 6건 중 실제 재난은 1건(영광 특별재난지역)뿐이었고,
# 나머지 5건이 펀드 운용사 선정·안전한국훈련·어린이 안전체험교육·AI 도입 예산·
# 사방사업 완료였다. 보도자료는 여러 언론이 받아써 기사 수 기준도 쉽게 넘는다.
DEFAULT_NON_EVENT = [
    "예방", "대비", "사방사업", "사업 완료", "사업완료", "정비", "점검", "훈련",
    "교육", "체험", "캠페인", "협약", "MOU", "선정", "공모", "표창", "수상",
    "설명회", "간담회", "워크숍", "세미나", "포럼", "도입", "조성", "구축",
    "위탁운용", "운용사", "펀드", "예산",
]


def _is_non_event(title, non_event_words):
    return any(w in title for w in non_event_words)


def _has_severity(title, severity_words, non_event_words=()):
    """심각도 키워드가 있고, 예방·행정 문맥이 아닐 때만 True."""
    if non_event_words and _is_non_event(title, non_event_words):
        return False
    return any(w in title for w in severity_words)


def _mostly_non_event(items, non_event_words):
    """클러스터 제목의 절반 이상이 예방·행정 문맥이면 사건이 아닌 보도자료로 본다.

    기사 수만으로 발동하는 경로(strong_cluster)도 이걸로 거른다 — 9월 오발동 5건 중
    3건(펀드 운용사 선정·안전체험교육·AI 도입 예산)이 이 경로로 들어왔다."""
    if not items or not non_event_words:
        return False
    n = sum(1 for i in items if _is_non_event(i.get("title", ""), non_event_words))
    return n * 2 >= len(items)


def decide(cfg):
    """발행할 사건을 고르거나 None. (사유 문자열도 함께 반환)"""
    tcfg = cfg.get("trigger", {})
    within_hours = tcfg.get("within_hours", 18)

    min_cluster = tcfg.get("min_cluster", 4)          # 몇 개 언론사면 '큰 사건'
    # 이만큼 크면 심각도 없어도 발행. 0 이면 끈다(심각도 키워드가 있는 사건만 발동).
    # 2026-09-29 끔: 9월 이후 이 경로로 잡힌 4건이 모두 재난이 아니었다 — 펀드 운용사
    # 선정, 안전체험교육 확대, AI 도입 예산, 재난안전상황실 운영 체계 전환.
    strong_cluster = tcfg.get("strong_cluster", 0)
    threshold = cfg.get("news", {}).get("dedup_similarity", 0.6)
    severity_words = tcfg.get("severity_keywords", DEFAULT_SEVERITY)
    non_event_words = tcfg.get("non_event_keywords", DEFAULT_NON_EVENT)

    raw = fetch_recent_raw(within_days=2)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    recent = [it for it in raw if it["published"] >= cutoff]
    if not recent:
        return None, f"최근 {within_hours}시간 내 기사 없음"

    clusters = _cluster(recent, threshold)
    clusters.sort(key=lambda c: len(c["items"]), reverse=True)

    skipped = []
    for c in clusters:
        size = len(c["items"])
        rep = c["items"][0]  # 최신 대표 기사
        if size >= min_cluster and _mostly_non_event(c["items"], non_event_words):
            skipped.append(f"'{_norm_title(rep['title'])[:20]}'({size}건)")
            continue          # 예방·행정 보도자료 — 기사 수와 무관하게 사건 아님
        sev = any(_has_severity(i.get("title", ""), severity_words, non_event_words)
                  for i in c["items"])
        big_enough = (size >= min_cluster and sev) or (strong_cluster > 0 and size >= strong_cluster)
        if big_enough:
            sig = _norm_title(rep["title"])[:40]
            return ({"sig": sig, "label": rep["title"][:40], "source": "news",
                     "rep": rep, "size": size, "severity": sev,
                     "items": c["items"][:3], "all_items": c["items"][:15]},
                    f"사건 감지: '{_norm_title(rep['title'])[:24]}' "
                    f"기사 {size}건, 심각도 {'있음' if sev else '없음'}")
    top = next((c for c in clusters
                if not (len(c["items"]) >= min_cluster
                        and _mostly_non_event(c["items"], non_event_words))), None)
    note = f" · 보도자료로 보고 제외: {', '.join(skipped[:3])}" if skipped else ""
    if not top:
        return None, f"발행할 만큼 큰 사건 없음 (클러스터 없음{note})"

    size = len(top["items"])
    sev = any(_has_severity(i.get("title", ""), severity_words, non_event_words)
              for i in top["items"])
    if size < min_cluster:
        why = f"기사 부족 {size}<{min_cluster}건"
    elif not sev:
        # 기사 수는 충족했지만 심각도 키워드가 없다.
        why = (f"심각도 키워드 없음(기사 {size}건 — 심각도 없는 발동은 꺼 둠)" if strong_cluster <= 0
               else f"심각도 키워드 없음, 기사 {size}<{strong_cluster}건(무심각도 기준)")
    else:
        why = f"기사 {size}건, 심각도 있음"
    detail = f"최대 클러스터 '{_norm_title(top['items'][0]['title'])[:24]}' — {why}{note}"
    return None, f"발행할 만큼 큰 사건 없음 ({detail})"


def _nums(t):
    """제목 속 숫자(연도 제외). '규모 9.9'·'8분' 같은 숫자는 같은 사건을 가리키는 강한 단서다."""
    return {n for n in re.findall(r"\d+", t) if not re.fullmatch(r"(19|20)\d\d", n)}


def _same_event(new_titles, old_titles):
    """같은 사건인가. 10/16 17:00 과 10/17 08:00 에 '규모 9.9 지진속보 8분 만에 취소'를
    언론사마다 다른 제목('열도 난리' / '강진 긴급속보 발령')으로 받아 유사도 0.62 → 두 번 발행했다.
    유사도 0.7 이상이거나, 0.5 이상이면서 연도 아닌 숫자를 함께 가지면 같은 사건으로 본다."""
    for a in new_titles:
        for b in old_titles:
            if not a or not b:
                continue
            r = SequenceMatcher(None, a, b).ratio()
            if r >= 0.7 or (r >= 0.5 and _nums(a) & _nums(b)):
                return True
    return False


def _gate(event, cfg, state):
    """쿨다운/주간상한/중복 통과 여부. (ok, 사유)"""
    tcfg = cfg.get("trigger", {})
    now = datetime.now(timezone.utc)
    sig = event["sig"]

    # 중복: 최근 dedup_days 내 같은 사건이면 재발행 안 함.
    dedup_days = tcfg.get("dedup_days", 3)
    titles = [sig] + [_norm_title(i.get("title", "")) for i in event.get("all_items", event.get("items", []))]
    for p in state.get("posted", []):
        ts = datetime.fromisoformat(p["ts"])
        if now - ts < timedelta(days=dedup_days) and _same_event(titles, [p["sig"]] + p.get("titles", [])):
            return False, f"이미 발행한 사건(중복): '{sig[:24]}' ≈ '{p['sig'][:24]}'"

    # 쿨다운
    last = state.get("last_trigger")
    min_hours = tcfg.get("min_hours_between", 12)
    if last:
        if now - datetime.fromisoformat(last) < timedelta(hours=min_hours):
            return False, f"쿨다운 중(최소 {min_hours}시간 간격)"

    # 주간 상한
    max_week = tcfg.get("max_per_week", 3)
    wk_ago = now - timedelta(days=7)
    recent_posts = [p for p in state.get("posted", [])
                    if datetime.fromisoformat(p["ts"]) >= wk_ago]
    if len(recent_posts) >= max_week:
        return False, f"주간 상한 도달({max_week}건/주)"

    return True, "통과"


def main(dry=False):
    cfg = load_config()
    if not cfg.get("trigger", {}).get("enabled", False):
        log("트리거 비활성(config.trigger.enabled=false). 종료.")
        return 0

    event, reason = decide(cfg)
    log(f"[트리거] {reason}")
    if not event:
        return 0

    state = _load_state()
    ok, gate_reason = _gate(event, cfg, state)
    if not ok:
        log(f"[트리거] 발행 보류 — {gate_reason}")
        return 0

    if dry:
        log("[트리거] (--dry) 조건 충족 → 실제로는 발행 안 함.")
        return 0

    # 실제 발행: 주간 파이프라인의 유튜브 부분만 실행
    log("[트리거] 조건 충족 → 유튜브 Shorts 즉시 발행 시작")
    from generate_script import generate
    from fetch_images import fetch_images
    from render_frames import make_frames
    from tts import make_tts
    from make_video import make_video
    from youtube_upload import upload

    data = generate(lead=event.get("items") or [event["rep"]])   # 영상이 이 사건으로 시작하게
    fetch_images(data)
    make_frames(data)
    make_tts(data)
    make_video(data)
    privacy = cfg.get("youtube", {}).get("privacy", "public")
    r = upload(data, dry_run=False, privacy=privacy)
    log(f"[트리거] 유튜브: {r.get('status')} {r.get('url','')}")

    # 스레드에도 같이 올린다(부가 채널 — 실패해도 유튜브 발행은 그대로).
    try:
        from threads_post import compose, crosspost
        crosspost(compose(data.get("title", "재난안전 속보"),
                          (data.get("scenes") or [{}])[0].get("narration", ""),
                          r.get("url", ""), data.get("hashtags") or []))
    except Exception as e:
        log(f"[트리거] 쓰레드 건너뜀(유튜브는 정상): {type(e).__name__}")
    try:                                   # X — 영상 첨부(부가 채널)
        from x_post import crosspost as x_crosspost
        from run_weekly import _threads_summary
        xr = x_crosspost(data, summary=_threads_summary(data))
        if xr.get("status") != "disabled":
            log(f"[트리거] X: {xr.get('status')} {xr.get('url', '')}")
    except Exception as e:
        log(f"[트리거] X 건너뜀(유튜브는 정상): {type(e).__name__}")

    # 상태 기록
    now = datetime.now(timezone.utc).isoformat()
    state["last_trigger"] = now
    state.setdefault("posted", []).append({
        "sig": event["sig"], "ts": now,
        "titles": [_norm_title(i.get("title", ""))[:40] for i in event.get("all_items", [])][:15]})
    state["posted"] = state["posted"][-30:]
    _save_state(state)
    log("[트리거] 상태 저장 완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main(dry="--dry" in sys.argv))
