"""재난안전 상식 O/X 퀴즈 숏폼 렌더러.

quiz_data.json(검증 통과 10문항)을 읽어 한 문항당 3장면 숏폼을 만든다.
  1) 훅: 문제 제시(O/X 고민)
  2) 정답: ⭕/❌ + 핵심 요약(자막) + 근거(나레이션)
  3) CTA: 팔로우 유도
정답·근거는 행안부·소방청·질병관리청 등 공식 지침 검증본(quiz_data.json)을 그대로 사용.

사용법:
  python quiz_make.py           # 10문항 전부 렌더
  python quiz_make.py 5         # 5번 문항만
  python quiz_make.py 1 5 9     # 1,5,9번만
"""
import json
import os
import sys

from render_frames import make_frames
from tts import make_tts
from make_video import make_video
from common import BASE_DIR, log

BG = "assets/firefly"
DATA_PATH = os.path.join(BASE_DIR, "quiz_data.json")


def _bg(key):
    return f"{BG}/{key}.png"


def render_one(q):
    stamp = f"TIKTOK_QUIZ{q['no']:02d}"
    data = {
        "stamp": stamp,
        "header_text": "세명대 재난안전 O·X",
        "max_seconds": 45,
        "title": f"[재난안전 O/X] {q['hook']}",
        "scenes": [
            {"heading": q["hook"],
             "lines": [q["statement"], "⭕ 일까 ❌ 일까?"],
             "narration": f"{q['statement']}. 과연 맞을까요, 틀릴까요?",
             "bg_image": _bg(q["bg_key"])},
            {"heading": "정답은",
             "answer": q["answer"],          # 큰 색상 O/X 마크(render_frames)
             "lines": q["takeaway"],
             "narration": q["explanation"],
             "bg_image": _bg(q["bg_key"])},
            {"heading": "다음 문제 갈까요?",
             "lines": ["팔로우하고", "재난안전 상식 정복"],
             "narration": "맞히셨나요? 팔로우하면 다음 문제도 놓치지 않아요.",
             "bg_image": _bg("07_cta")},
        ],
        "source_images": {},
    }
    # 실사 B롤(Pexels): 문항에 검색어가 있으면 1·2장면 배경으로 쓴다. 마무리(3장면)는
    # 일러스트 그대로 — 시리즈 끝맺음을 같은 화면으로 통일한다. 받기에 실패하면 그 장면만
    # 자동 매칭(일러스트)으로 돌아간다(렌더가 멈추지 않게).
    if q.get("pexels"):
        from pexels_broll import fetch
        data["broll"] = {}
        for i, query in enumerate(q["pexels"], start=1):
            try:
                data["broll"][str(i)] = fetch(query)["path"]
            except Exception as e:
                log(f"Pexels B롤 실패({query}) → 일러스트로: {type(e).__name__}: {str(e)[:80]}")
    log(f"===== {stamp} 렌더: {q['topic']} (정답 {q['answer']}) =====")
    make_frames(data)
    make_tts(data)
    make_video(data)
    log(f"완성: {data.get('video')} ({data.get('video_seconds')}s)")
    print("VIDEO:", data.get("video"), "|", data.get("video_seconds"), "s")
    return data.get("video")


def main(argv):
    quizzes = json.load(open(DATA_PATH, encoding="utf-8"))
    want = {int(a) for a in argv} if argv else None
    for q in quizzes:
        if want and q["no"] not in want:
            continue
        render_one(q)


if __name__ == "__main__":
    main(sys.argv[1:])
