"""카드뉴스 릴의 카드 위아래 띠에 깔 주제 맞춤 실사 배경(Pexels → Pixabay)과 '자료 화면' 표기.

카드뉴스는 실제 지역 사건을 다루므로 배경 영상을 그 사건 현장으로 오해할 수 있다.
그래서 (1) 사고·피해 장면이 아닌 상황 장면만 고르고(빗길, 숲 연기, 눈길 등),
(2) 카드 아래 띠에 '배경: 자료 화면'을 표기한다(2026-09-29 결정).
카드(940px) 자체는 가리지 않는다 — 실사는 위아래 각 490px 띠에만 보인다.

키: config.json 의 pexels.api_key / pixabay.api_key. 키가 없거나 받기에 실패하면 None → 단색 배경으로.
"""
import os
import sys

import imageio_ffmpeg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared import stock_video as _sv  # noqa: E402

from common import BASE_DIR, POSTS_DIR, load_config, log  # noqa: E402

OUT_DIR = os.path.join(POSTS_DIR, "broll_pexels")
FONT = os.path.join(os.path.dirname(BASE_DIR), "FONTS", "KoPubWorld Dotum_Pro Bold.otf")  # 이미지 글자는 Bold(사용자 지정)

TOPIC_QUERIES, DEFAULT_QUERY = _sv.TOPIC_QUERIES, _sv.DEFAULT_QUERY
MAX_CLIPS = 3          # 릴 하나에 쓸 배경 클립 수(서로 다른 촬영자)
CUT_SEC = 7.0          # 이 간격으로 배경 클립을 바꾼다(카드 2장 = 7초)

# 실사를 못 구하면 유튜브 쪽이 만든 일러스트 B롤(make_broll.py)로 채운다(2026-09-29 결정 —
# AI 영상 생성 대신). 사실적인 가짜 재난 장면이 아니라 오해 위험이 없어 '자료 화면' 표기도 뺀다.
ILLUST_DIR = os.path.join(os.path.dirname(BASE_DIR), "youtube-shorts-auto", "posts", "broll")
ILLUST_FOR = {"heavy rain street": "flood", "forest fire smoke": "wildfire",
              "city buildings aerial": "quake", "snow winter street": "snow",
              "hot summer sun city": "heat", "drone flying sky": "satellite",
              "city lights night timelapse": "satellite"}


def pick_query(data):
    """제목 → 카드 문구 순으로 주제 검색어를 고른다(shared.stock_video.pick_query)."""
    return _sv.pick_query([data.get("title") or "",
                           " ".join(str(c) for c in (data.get("cards") or []))])


def fetch_bg(data):
    """이 카드뉴스에 맞는 배경 클립(가공본) 정보. 실패하면 None."""
    keys = _sv.keys_from(load_config())
    query = pick_query(data)
    if not any(keys.values()):
        return illust_bg(query)
    try:
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        # 카드 사이사이에 배경 영상을 전체 화면으로 보여 주므로(2026-10-01) 어둡게·흐리게
        # 가공하지 않는다 — 크기(1080x1920)만 맞춘 사본. 카드는 불투명이라 글자는 그대로 읽힌다.
        clean = {"fx": "null", "suffix": "_clean"}
        first = _sv.fetch(query, keys, OUT_DIR, ffmpeg=ff, log=log, **clean)
        # 7초(카드 2장)마다 배경을 다른 촬영자의 클립으로 바꾼다 — 한 클립을 28초 돌리면
        # 화면이 늘어진다. 같은 촬영자의 연속 영상은 컷을 바꿔도 같은 화면처럼 보여 피한다.
        clips, bys = [first["path"]], {first.get("by")}
        for k in range(1, 6):
            if len(clips) >= MAX_CLIPS:
                break
            try:
                c = _sv.fetch(query, keys, OUT_DIR, pick=k, ffmpeg=ff, log=log, **clean)
            except Exception:
                break
            if c["path"] in clips:
                break
            if c.get("by") not in bys:
                clips.append(c["path"])
                bys.add(c.get("by"))
        first["clips"] = clips
        return first
    except Exception as e:
        log(f"릴 실사 배경 실패({query}) → 일러스트 B롤: {type(e).__name__}: {str(e)[:80]}")
        return illust_bg(query)


def illust_bg(query):
    """주제에 맞는 일러스트 B롤. 없으면 None(→ 단색)."""
    path = os.path.join(ILLUST_DIR, f"{ILLUST_FOR.get(query, 'dawn')}.mp4")
    if not os.path.exists(path):
        return None
    return {"source": "illust", "query": query, "id": os.path.basename(path), "path": path,
            "by": "SMUDS", "url": "", "label": False}


def label_png(work_dir, text="배경: 자료 화면"):
    """카드 아래 왼쪽에 얹을 반투명 라벨 PNG.

    카드 바로 위에 '자료 화면'만 붙였더니 카드 자체가 자료 화면이라는 뜻으로 읽혔다.
    배경 영상을 가리키는 말로 쓰고 카드 아래 띠에 둔다."""
    from PIL import Image, ImageDraw, ImageFont
    path = os.path.join(work_dir, "label_stock.png")
    font = ImageFont.truetype(FONT, 30) if os.path.exists(FONT) else ImageFont.load_default()
    pad_x, pad_y = 18, 9
    tw, th = font.getbbox(text)[2:]
    img = Image.new("RGBA", (tw + pad_x * 2, th + pad_y * 2 + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=10, fill=(0, 0, 0, 150))
    d.text((pad_x, pad_y), text, font=font, fill=(255, 255, 255, 235))
    img.save(path)
    return path


def bg_sequence(clips, dur, work_dir, ffmpeg, cut=CUT_SEC):
    """clips 를 cut 초씩 돌려 dur 초짜리 배경 영상 하나로 이어 붙인다. 클립이 하나면 그대로."""
    import math
    import subprocess
    if len(clips) < 2:
        return clips[0]
    n = math.ceil(dur / cut)
    parts = []
    for j in range(n):
        clip = clips[j % len(clips)]
        start = (j // len(clips)) * cut           # 같은 클립이 다시 나오면 다음 구간부터
        out = os.path.join(work_dir, f"bg_{j:02d}.mp4")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-stream_loop", "-1", "-ss", f"{start:.2f}",
                        "-i", clip, "-t", f"{cut:.2f}", "-an",
                        "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
                        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", out], check=True)
        parts.append(out)
    lst = os.path.join(work_dir, "bg_list.txt")
    with open(lst, "w", encoding="utf-8") as f:
        f.writelines(f"file '{p}'\n" for p in parts)
    seq = os.path.join(work_dir, "bg_seq.mp4")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c", "copy", seq], check=True)
    return seq
