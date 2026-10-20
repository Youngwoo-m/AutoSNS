"""이미 렌더한 퀴즈 영상에 나레이션 자막을 덧입힌다(렌더 때 자막 기능이 없던 편).

posts/<stamp>.json 에 저장된 장면·음성 길이를 쓰고, 단어 타이밍은 같은 문장을 다시
합성해 받는다. 한 번 입힌 편은 json 에 captions_burned 를 남겨 두 번 입히지 않는다.

사용: python caption_backfill_quiz.py 1 2 3 …   (퀴즈 번호)
"""
import json
import os
import sys

from captions import burn
from common import POSTS_DIR, log


def backfill(no):
    stamp = f"TIKTOK_QUIZ{int(no):02d}"
    jp, vp = os.path.join(POSTS_DIR, f"{stamp}.json"), os.path.join(POSTS_DIR, f"short_{stamp}.mp4")
    if not (os.path.exists(jp) and os.path.exists(vp)):
        log(f"{stamp}: 파일 없음 — 건너뜀")
        return False
    d = json.load(open(jp, encoding="utf-8"))
    if d.get("captions_burned"):
        log(f"{stamp}: 이미 자막 있음 — 건너뜀")
        return False
    burn(vp, d, os.path.join(POSTS_DIR, f"video_{stamp}", "captions"))
    d["captions_burned"] = True
    json.dump(d, open(jp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return True


if __name__ == "__main__":
    n = sum(bool(backfill(x)) for x in sys.argv[1:])
    print(f"자막 덧입힘 {n}편")
