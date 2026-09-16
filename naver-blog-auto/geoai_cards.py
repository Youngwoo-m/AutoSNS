"""블로그 글 내용을 Gamma 카드뉴스(PNG 여러 장)로 만든다.

gamma_image.py 는 헤더 이미지 1장 전용이라, 여러 장을 순서대로 받아오는 부분만
여기서 따로 쓴다(요청·폴링·다운로드는 gamma_image 의 것을 그대로 재사용).

카드 구성: 표지(제목+날짜) → 핵심 3장(요약/소제목) → 마무리(어디서 더 보나).
글마다 크레딧이 차감되므로 장수는 config.geoai.cards.count 로 조절한다.
"""
import os
import re
import time
import zipfile
from datetime import datetime

from common import POSTS_DIR, load_config, log
from gamma_image import _download, _post, _status

DEFAULT_STYLE = (
    "한국어 정보 카드뉴스. 최우선 목표는 '한눈에 읽히는 고가독성'이다. "
    "카드 상단에 굵은 제목, 아래에 짧은 본문. 글자는 굵은 산세리프, 텍스트는 단색 "
    "불투명 패널 위에 올려 대비를 높인다. 위성·지도·데이터를 연상시키는 차분한 "
    "남색·청록 톤에 강조는 소량. 지도/위성/AI 를 뜻하는 단순한 플랫 아이콘 1개 정도. "
    "로고·엠블럼·영문 워드마크는 만들지 말고 제공된 한글 텍스트만 사용."
)


def _ccfg(cfg=None):
    return ((cfg or load_config()).get("geoai") or {}).get("cards") or {}


def _natural_key(name):
    """카드 순서가 1,2,10 처럼 섞이지 않게 숫자를 숫자로 비교한다."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _summary_lines(data):
    """요약을 줄 목록으로 정규화한다.

    시리즈 글은 리스트, 브리핑 글(generate_content)은 '· ' 로 시작하는 여러 줄 문자열이라
    그대로 순회하면 글자 단위로 쪼개진다."""
    s = data.get("summary") or []
    if isinstance(s, str):
        s = s.splitlines()
    return [re.sub(r"^[·\-•*]\s*", "", str(l)).strip() for l in s if str(l).strip()]


def _card_texts(data, cfg):
    """글 데이터 → 카드별 문구. 마커(---)로 나눠 Gamma 에 넘긴다.

    구성은 표지(제목+날짜) → 핵심(요약·소제목) → 마무리(블로그 안내) 순이고,
    장수(config.geoai.cards.count)가 줄어도 표지와 마무리 자리는 먼저 확보한다
    (요약으로 앞을 다 채우면 마무리 카드가 잘려 나간다)."""
    n = max(int(_ccfg(cfg).get("count", 5)), 1)
    date_kr = f"{datetime.now():%Y년 %m월 %d일}"
    title = re.sub(r"\s*\|\s*.*$", "", data.get("title", "")).strip()
    cover = f"{title}\n{date_kr}"
    closing = "전체 내용은 블로그에서\n재난안전과 GeoAI"
    if n == 1:
        return [cover]
    if n == 2:
        return [cover, closing]
    middle = []
    for s in _summary_lines(data)[:3]:
        if len(middle) >= n - 2:
            break
        middle.append(s)
    # 요약이 모자라면 소제목으로 채운다(시리즈 글·브리핑 모두 대응)
    heads = [h for h, _ in (data.get("sections") or [])] or \
            [b.get("heading", "") for b in (data.get("news_blocks") or [])]
    for h in heads:
        if len(middle) >= n - 2:
            break
        h = re.sub(r"^[^\w가-힣]+", "", h).strip()
        if h:
            middle.append(h)
    return [cover] + middle + [closing]


def make_cards(data, cfg=None):
    """카드 PNG 경로 목록을 돌려준다. 실패하면 예외(호출부에서 이미지 없이 진행)."""
    cfg = cfg or load_config()
    c = _ccfg(cfg)
    api_key = (cfg.get("gamma_api_key") or "").strip()
    if not api_key:
        raise RuntimeError("config.json 의 gamma_api_key 가 비어 있습니다.")
    cards = _card_texts(data, cfg)
    body = {
        "inputText": "\n---\n".join(cards),
        "format": "social",
        "exportAs": "png",
        "numCards": len(cards),
        "textMode": "preserve",
        "cardSplit": "inputTextBreaks",
        "cardOptions": {"dimensions": c.get("dimensions", "16x9")},
        "textOptions": {"language": "ko"},
        "additionalInstructions": c.get("style_instructions", DEFAULT_STYLE),
    }
    if c.get("theme_id"):
        body["themeId"] = c["theme_id"]

    log(f"Gamma 카드뉴스 생성 요청({len(cards)}장, {body['cardOptions']['dimensions']})")
    res = _post(api_key, body)
    gen_id = res.get("generationId")
    if not gen_id:
        raise RuntimeError(f"generationId 없음: {res}")
    export_url = None
    deadline = time.time() + 420
    while time.time() < deadline:
        time.sleep(8)
        st = _status(api_key, gen_id)
        if st.get("status") == "completed":
            export_url = st.get("exportUrl")
            cr = st.get("credits", {})
            log(f"Gamma 완료(크레딧 차감 {cr.get('deducted')}, 잔여 {cr.get('remaining')})")
            break
        if st.get("status") == "failed":
            raise RuntimeError(f"Gamma 생성 실패: {st.get('error')}")
    if not export_url:
        raise RuntimeError("Gamma 생성 시간 초과(7분)")

    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    raw = os.path.join(POSTS_DIR, f"{stamp}_geoai_cards.bin")
    _download(export_url, raw)
    with open(raw, "rb") as f:
        magic = f.read(4)
    if magic[:4] == b"\x89PNG":                 # 1장이면 PNG 가 그대로 온다
        one = os.path.join(POSTS_DIR, f"{stamp}_geoai_card.png")
        os.replace(raw, one)
        return [one]
    out_dir = os.path.join(POSTS_DIR, f"geoai_cards_{stamp}")
    os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(raw) as z:
        z.extractall(out_dir)
    pngs = [os.path.join(out_dir, n) for n in os.listdir(out_dir)
            if n.lower().endswith(".png")]
    if not pngs:
        raise RuntimeError("Gamma zip 에 PNG 없음")
    pngs.sort(key=lambda p: _natural_key(os.path.basename(p)))
    log(f"카드뉴스 {len(pngs)}장 생성: {out_dir}")
    return pngs


if __name__ == "__main__":
    import glob, json, sys
    path = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob(os.path.join(POSTS_DIR, "*.json")))[-1]
    d = json.load(open(path, encoding="utf-8"))
    print("카드 문구:", *_card_texts(d, load_config()), sep="\n  - ")
    if "--go" in sys.argv:
        print(make_cards(d))
