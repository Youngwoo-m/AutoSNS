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
FONT = os.path.join(os.path.dirname(BASE_DIR), "FONTS", "KoPubWorld Dotum_Pro Medium.otf")

# 제목·카드 문구에서 먼저 걸리는 것부터(앞쪽이 더 구체적). 사고·피해 장면이 나오지
# 않을 상황 장면으로만 검색한다.
TOPIC_QUERIES = [
    (("산불",), "forest fire smoke"),
    (("호우", "폭우", "집중호우", "침수", "홍수", "장마", "물폭탄"), "heavy rain street"),
    (("태풍", "강풍", "돌풍"), "storm wind trees"),
    (("폭설", "대설", "빙판", "한파", "동파"), "snow winter street"),
    (("폭염", "열사병", "온열", "무더위"), "hot summer sun city"),
    (("산사태", "토사", "토석류"), "mountain forest rain"),
    (("지진",), "city buildings aerial"),
    (("화재", "불길", "연기"), "fire smoke dark"),
    (("드론",), "drone flying sky"),
    (("AI", "인공지능", "CCTV", "스마트", "디지털"), "city lights night timelapse"),
    (("훈련", "소방", "구조대"), "fire truck city"),
    (("교통", "도로", "고속도로"), "highway traffic night"),
    (("추석", "명절", "전통시장", "축제"), "busy market street"),
]
DEFAULT_QUERY = "clouds sky timelapse"

# 실사를 못 구하면 유튜브 쪽이 만든 일러스트 B롤(make_broll.py)로 채운다(2026-09-29 결정 —
# AI 영상 생성 대신). 사실적인 가짜 재난 장면이 아니라 오해 위험이 없어 '자료 화면' 표기도 뺀다.
ILLUST_DIR = os.path.join(os.path.dirname(BASE_DIR), "youtube-shorts-auto", "posts", "broll")
ILLUST_FOR = {"heavy rain street": "flood", "forest fire smoke": "wildfire",
              "city buildings aerial": "quake", "snow winter street": "snow",
              "hot summer sun city": "heat", "drone flying sky": "satellite",
              "city lights night timelapse": "satellite"}


def pick_query(data):
    """제목에서 가장 먼저 나오는 말을 기준으로 고른다(제목 앞머리가 기사의 주어다).

    목록 순서로 고르면 '충북 드론 선제 출동 — AI가 산불·재난 골든타임'이 '산불'로
    잡혀 숲 연기가 깔렸다. 산불이 난 기사가 아닌데 산불 현장처럼 보인다."""
    title = data.get("title") or ""
    body = " ".join(str(c) for c in (data.get("cards") or []))
    for text in (title, body):
        hits = [(text.find(w), query) for words, query in TOPIC_QUERIES
                for w in words if w in text]
        if hits:
            return min(hits)[1]
    return DEFAULT_QUERY


def fetch_bg(data):
    """이 카드뉴스에 맞는 배경 클립(가공본) 정보. 실패하면 None."""
    keys = _sv.keys_from(load_config())
    query = pick_query(data)
    if not any(keys.values()):
        return illust_bg(query)
    try:
        return _sv.fetch(query, keys, OUT_DIR, ffmpeg=imageio_ffmpeg.get_ffmpeg_exe(), log=log)
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
