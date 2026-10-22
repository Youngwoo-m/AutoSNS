"""발행이 끝난 편의 Voicebox 음성 파일을 공개일 7일 뒤에 지운다(launchd: 매일 05:20).

  python3 cleanup.py           # 실제 삭제
  python3 cleanup.py --dry     # 지울 것만 보여 주기
지우는 것:
  1) 편 폴더의 voice/*.wav (나레이션 녹음, USB)
  2) Voicebox 앱 안의 생성 기록과 음성 파일(맥 내장 디스크) — 그 편 나레이션과 같은 문장으로 만든 것 전부
     (발음 검사로 여러 번 만든 것 포함). 실패한 생성 기록도 함께 정리.
지우지 않는 것: common/ 의 인트로·아웃트로 음성, 아직 7일이 안 된 편, 업로드하지 않은 편(견본 등), 완성 영상.
편마다 결과를 <편>/cleanup.json 에 남겨 같은 편을 다시 지우지 않는다.
"""
import datetime as dt, glob, json, os, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
ROOT, VB = CFG["root"], CFG["voicebox"]["url"]
KST = dt.timezone(dt.timedelta(hours=9))
KEEP_DAYS = 7


def log(m):
    print(f"[{dt.datetime.now(KST):%m-%d %H:%M}] {m}", flush=True)


def _api(method, path):
    r = urllib.request.Request(VB + path, method=method)
    with urllib.request.urlopen(r, timeout=30) as f:
        return json.loads(f.read() or b"{}")


def due_episodes():
    today = dt.datetime.now(KST).date()
    for d in sorted(glob.glob(os.path.join(ROOT, "20??-??-??_*"))):
        if not os.path.exists(os.path.join(d, "upload.json")) or os.path.exists(os.path.join(d, "cleanup.json")):
            continue
        pub = dt.date.fromisoformat(os.path.basename(d)[:10])
        if today >= pub + dt.timedelta(days=KEEP_DAYS):
            yield d


def history():
    items, off = [], 0
    while True:
        page = _api("GET", f"/history?limit=100&offset={off}")
        items += page.get("items", [])
        off += 100
        if off >= page.get("total", 0) or not page.get("items"):
            return items


def protected_texts():
    """아직 지우면 안 되는 문장 — 7일이 안 된 편·업로드 전 편의 나레이션, 인트로·아웃트로."""
    keep = {CFG["intro_text"].strip(), CFG["outro_text"].strip()}
    due = {os.path.basename(d) for d in due_episodes()}
    for d in glob.glob(os.path.join(ROOT, "*", "script.json")):
        ep = os.path.basename(os.path.dirname(d))
        if ep in due or os.path.exists(os.path.join(os.path.dirname(d), "cleanup.json")):
            continue
        for s in json.load(open(d, encoding="utf-8")).get("scenes", []):
            keep.update(t.strip() for t in (s.get("narration"), s.get("tts_text")) if t)
    return keep


def old_leftovers(hist):
    """7일이 지난 생성 기록 중 지켜야 할 문장이 아닌 것(예전 대본으로 만든 것, 발음 재시도 등)."""
    keep, cut = protected_texts(), dt.datetime.now(KST).replace(tzinfo=None) - dt.timedelta(days=KEEP_DAYS)
    out = []
    for h in hist:
        try:
            made = dt.datetime.fromisoformat(h["created_at"]) + dt.timedelta(hours=9)   # 기록은 UTC
        except Exception:
            continue
        if made < cut and (h.get("text") or "").strip() not in keep:
            out.append(h)
    return out


def main(dry):
    eps = list(due_episodes())
    try:
        all_hist = history()
    except Exception as e:
        log(f"Voicebox 서버에 연결 못 함 — 앱 안 기록은 다음에 정리: {e}"); all_hist = None
    left = old_leftovers(all_hist) if all_hist is not None else []
    if left:
        log(f"예전 대본·재시도 생성 기록(7일 지남) {len(left)}개")
        if not dry:
            for h in left:
                try:
                    _api("DELETE", f"/history/{h['id']}")
                except Exception as e:
                    log(f"  기록 삭제 실패 {h['id']}: {e}")
    if not eps:
        log("지울 편 없음(공개 7일이 지난 편이 없거나 이미 정리함)"); return
    texts, wavs = set(), []
    for d in eps:
        sc = json.load(open(os.path.join(d, "script.json"), encoding="utf-8"))
        for s in sc["scenes"]:
            texts.update(t.strip() for t in (s.get("narration"), s.get("tts_text")) if t)
        wavs += glob.glob(os.path.join(d, "voice", "*.wav"))
    hist = None if all_hist is None else [h for h in all_hist if (h.get("text") or "").strip() in texts
                                          and h not in left]
    log(f"대상 편 {len(eps)}개: {', '.join(os.path.basename(d) for d in eps)}")
    log(f"  USB 나레이션 파일 {len(wavs)}개, Voicebox 생성 기록 {len(hist) if hist is not None else '?'}개")
    if dry:
        return
    for w in wavs:
        os.remove(w)
    removed = 0
    for h in hist or []:
        try:
            _api("DELETE", f"/history/{h['id']}"); removed += 1
        except Exception as e:
            log(f"  기록 삭제 실패 {h['id']}: {e}")
    if hist is not None:
        try:
            _api("DELETE", "/history/failed")
        except Exception:
            pass
    for d in eps:
        if hist is None:                  # 앱 쪽을 못 지웠으면 기록을 남기지 않아 다음 날 다시 시도
            continue
        json.dump({"cleaned_at": dt.datetime.now(KST).isoformat(), "voice_files": len(wavs), "voicebox_history": removed},
                  open(os.path.join(d, "cleanup.json"), "w"), indent=1)
    log(f"정리 완료: 나레이션 파일 {len(wavs)}개, Voicebox 기록 {removed}개 삭제")


if __name__ == "__main__":
    main("--dry" in sys.argv)
