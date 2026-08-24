"""Gamma REST API 로 카드 문구를 '소셜 카드(이미지)'로 만들고 PNG 들을 받아온다.

흐름: POST /v1.0/generations (exportAs=png) → generationId →
GET /v1.0/generations/{id} 폴링 → status=completed 시 exportUrl(.zip) 다운로드 →
압축 해제 → 카드 순서대로 정렬된 PNG 경로 리스트 반환.

표준 라이브러리(urllib)만 사용해 추가 의존성을 두지 않는다.
Gamma Generate API 는 유료 플랜 + API 키가 필요하다. (config.gamma_api_key)
"""
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
import zipfile

from common import POSTS_DIR, load_config, log

# 재난안전 뉴스브리핑에 어울리는(진중·긴박·고대비) 테마 풀. random_theme=true 면 여기서 랜덤.
NEWS_THEME_POOL = [
    "default-light", "default-dark", "marine", "blues", "slate", "coal",
    "ash", "onyx", "gleam", "blue-steel", "consultant", "stratos",
    "nightsky", "founder", "rush", "pearl", "chimney-smoke", "howlite",
]


def _pick_theme(gcfg):
    """random_theme 이면 풀에서 랜덤 선택, 아니면 고정 theme_id."""
    if gcfg.get("random_theme"):
        pool = gcfg.get("theme_pool") or NEWS_THEME_POOL
        return random.choice(pool)
    return gcfg.get("theme_id", "")

API_BASE = "https://public-api.gamma.app/v1.0/generations"

# Cloudflare 가 기본 python-urllib UA 를 차단(error 1010)하므로 브라우저 UA 를 쓴다.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _post_generation(api_key, body):
    req = urllib.request.Request(
        API_BASE,
        data=json.dumps(body).encode("utf-8"),
        headers={"X-API-KEY": api_key, "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": UA},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"Gamma 생성 요청 실패(HTTP {e.code}): {detail}")


def _get_status(api_key, gen_id):
    req = urllib.request.Request(
        f"{API_BASE}/{gen_id}",
        headers={"X-API-KEY": api_key, "Accept": "application/json",
                 "User-Agent": UA},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _natural_key(name):
    """파일명 안의 숫자를 기준으로 자연 정렬(card1, card2, ... card10)."""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", name)]


def _download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def make_cards(data):
    """data(generate_cards 결과)로 카드 PNG 들을 만들어 경로 리스트를 반환한다."""
    cfg = load_config()
    api_key = cfg.get("gamma_api_key", "").strip()
    if not api_key or api_key.startswith("sk-gamma-...여기"):
        raise SystemExit(
            "config.json 의 gamma_api_key 가 비어 있습니다. "
            "Gamma 유료 플랜에서 발급한 API 키를 넣어주세요.")

    gcfg = cfg.get("gamma", {})
    cards = data["cards"]
    # 카드 경계를 '---' 로 명시 → Gamma 가 그대로 카드 분할(cardSplit=inputTextBreaks)
    input_text = "\n\n---\n\n".join(cards)

    card_options = {"dimensions": gcfg.get("dimensions", "1x1")}
    # 카드 하단 중앙 바닥글:
    #   "customImage" = 지정한 로고 URL(footer_logo_url) / "themeLogo" = 테마 로고 /
    #   "text" = 기관명 텍스트 / "none" = 없음
    footer_center = gcfg.get("footer_center", "text")
    size = gcfg.get("footer_logo_size", "md")
    if footer_center == "customImage" and gcfg.get("footer_logo_url"):
        card_options["headerFooter"] = {
            "bottomCenter": {"type": "image", "source": "custom",
                             "src": gcfg["footer_logo_url"], "size": size}
        }
    elif footer_center == "themeLogo":
        card_options["headerFooter"] = {
            "bottomCenter": {"type": "image", "source": "themeLogo", "size": size}
        }
    elif footer_center == "text":
        footer_text = gcfg.get("footer_text", "세명대학교 재난안전학과")
        if footer_text:
            card_options["headerFooter"] = {
                "bottomCenter": {"type": "text", "value": footer_text}
            }

    body = {
        "inputText": input_text,
        "format": "social",
        "exportAs": "png",
        "textMode": "preserve",          # 내 문구를 그대로 유지(사실성 보존)
        "cardSplit": "inputTextBreaks",  # '---' 기준으로 카드 분할
        "cardOptions": card_options,
        "textOptions": {"language": "ko"},
        "additionalInstructions": gcfg.get(
            "style_instructions",
            "한국 재난안전 공공정보 카드뉴스. 신뢰감 있는 남색/적색 톤, 큰 제목, "
            "또렷한 가독성, 카드마다 주제에 어울리는 아이콘. 차분하고 공신력 있게."),
    }
    theme = _pick_theme(gcfg)
    if theme:
        body["themeId"] = theme

    log(f"Gamma 카드 생성 요청({len(cards)}장, {body['cardOptions']['dimensions']}, "
        f"테마={theme or '기본'})...")
    res = _post_generation(api_key, body)
    gen_id = res.get("generationId")
    if res.get("warnings"):
        log(f"Gamma 경고: {res['warnings']}")
    if not gen_id:
        raise RuntimeError(f"generationId 없음: {res}")

    # 폴링 (최대 ~6분)
    export_url = gamma_url = None
    deadline = time.time() + 360
    while time.time() < deadline:
        time.sleep(8)
        st = _get_status(api_key, gen_id)
        status = st.get("status")
        if status == "completed":
            export_url = st.get("exportUrl")
            gamma_url = st.get("gammaUrl")
            credits = st.get("credits", {})
            log(f"Gamma 완료. gammaUrl={gamma_url} "
                f"(크레딧 차감 {credits.get('deducted')}, 잔여 {credits.get('remaining')})")
            break
        if status == "failed":
            raise RuntimeError(f"Gamma 생성 실패: {st.get('error')}")
        log(f"Gamma 생성 중... (status={status})")
    if not export_url:
        raise RuntimeError("Gamma 생성 시간 초과(6분). 잠시 후 다시 시도하세요.")

    # zip 다운로드 → 압축 해제
    stamp = data.get("stamp") or time.strftime("%Y%m%d_%H%M%S")
    zip_path = os.path.join(POSTS_DIR, f"{stamp}_cards.zip")
    out_dir = os.path.join(POSTS_DIR, f"cards_{stamp}")
    os.makedirs(out_dir, exist_ok=True)
    _download(export_url, zip_path)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(out_dir)

    pngs = [os.path.join(out_dir, n) for n in os.listdir(out_dir)
            if n.lower().endswith(".png")]
    pngs.sort(key=lambda p: _natural_key(os.path.basename(p)))
    if not pngs:
        raise RuntimeError(f"PNG 가 zip 에 없습니다: {zip_path}")

    log(f"카드 PNG {len(pngs)}장 준비: {out_dir}")
    data["images"] = pngs
    data["gamma_url"] = gamma_url
    # 결과를 json 에 반영 저장
    with open(os.path.join(POSTS_DIR, f"{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return pngs


if __name__ == "__main__":
    import sys
    # posts/xxx.json 을 받아 카드 PNG 생성 (없으면 가장 최근 json)
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        files = sorted(f for f in os.listdir(POSTS_DIR) if f.endswith(".json"))
        if not files:
            raise SystemExit("먼저 generate_cards.py 를 실행하세요.")
        path = os.path.join(POSTS_DIR, files[-1])
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    for p in make_cards(d):
        print(p)
