"""캡션이 빈 채로 올라간 인스타 게시물에 캡션을 채워 넣는다.

2026-09 에 공유 화면에선 캡션이 들어가 있었는데 게시물엔 빈 채로 올라간 릴이 8건
나왔다. 게시 직후 보완 단계(post_instagram._fix_caption_after_publish)가 편집을
시도했지만 저장되지 않았다. 여기서는 일요일 점검(ig_caption_boost)에서 140건 보강에
성공한 편집 경로를 쓰고, 빈 편집기가 입력을 놓치지 않도록 앞뒤로 실제 키 입력을 넣는다.

지키는 것:
  - 캡션이 이미 있는 게시물은 건드리지 않는다(직접 쓴 내용을 덮지 않기 위해).
  - '완료'는 편집칸 내용이 의도한 문자열과 일치할 때만 누른다. 어긋나면 '취소'.
  - 저장은 편집창을 다시 열어 확인한다.
  - 기본은 dry-run. 편집 간 25~60초 쉬고, '차단' 문구가 보이면 즉시 멈춘다.

사용: python ig_caption_restore.py captions.json            # dry-run(대상 상태만 확인)
      python ig_caption_restore.py captions.json --go [코드 ...]  # 실제 편집(코드 지정 시 그것만)
captions.json = {"게시물코드": "넣을 캡션", ...}
"""
import json
import random
import sys
import time

from common import load_config, log
from ig_caption_boost import _blocked, _click_text, _norm, _open_editor
from post_instagram import _fill_empty_caption, build_driver, shot


def restore_one(d, code, caption, go):
    """반환: restored | has_caption | dry | mismatch | not_saved | error | blocked"""
    box = _open_editor(d, code)
    if box is None:
        return "error"
    if box.text.strip():
        _click_text(d, ["취소", "Cancel"])
        return "has_caption"
    if not go:
        _click_text(d, ["취소", "Cancel"])
        return "dry"
    _fill_empty_caption(d, box, caption)
    if _norm(box.text) != _norm(caption):
        shot(d, f"restore_mismatch_{code}")
        _click_text(d, ["취소", "Cancel"])
        return "mismatch"
    if not _click_text(d, ["완료", "Done"]):
        _click_text(d, ["취소", "Cancel"])
        return "error"
    time.sleep(random.uniform(5.0, 7.0))
    if _blocked(d):
        return "blocked"
    box2 = _open_editor(d, code)
    if box2 is None:
        return "error"
    ok = _norm(box2.text) == _norm(caption)
    if not ok:
        shot(d, f"restore_not_saved_{code}")
    _click_text(d, ["취소", "Cancel"])
    return "restored" if ok else "not_saved"


def main(argv):
    path = argv[0]
    go = "--go" in argv
    only = [a for a in argv[1:] if not a.startswith("--")]
    caps = json.load(open(path, encoding="utf-8"))
    codes = only or list(caps)
    ig = load_config().get("instagram", {})
    d = build_driver(headless=False)
    results = {}
    try:
        for n, code in enumerate(codes):
            res = restore_one(d, code, caps[code], go)
            results[code] = res
            log(f"캡션 복원 {'' if go else '[DRY] '}{code}: {res}")
            if res == "blocked":
                shot(d, "restore_blocked")
                log("⚠ 인스타 제한 감지 → 즉시 중단")
                break
            if res in ("not_saved", "mismatch") and go:
                log("⚠ 저장이 확인되지 않아 나머지는 멈춥니다(같은 방식이면 또 실패할 수 있다)")
                break
            if n < len(codes) - 1:
                time.sleep(random.uniform(25, 60) if go else random.uniform(4, 8))
    finally:
        d.quit()
    print(json.dumps(results, ensure_ascii=False))
    return results


if __name__ == "__main__":
    main(sys.argv[1:])
