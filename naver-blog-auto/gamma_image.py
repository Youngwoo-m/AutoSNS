"""Gamma REST API 로 '본문 내용과 관련된' 헤더 이미지(PNG) 1장을 만든다.

블로그 글의 제목 + 소제목(테마)을 Gamma 에 넣어 16:9 대표 이미지를 생성하고
PNG 경로를 반환한다. 실패 시 예외 → 호출부에서 기본 배너로 폴백.

흐름: POST /v1.0/generations (numCards=1, exportAs=png) → 폴링 →
completed 시 exportUrl(zip) 다운로드 → 압축 해제 → PNG 경로 반환.
표준 라이브러리(urllib)만 사용. Gamma 유료 플랜 + API 키 필요(config.gamma_api_key).
"""
import json
import os
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime

from common import POSTS_DIR, load_config, log

API_BASE = "https://public-api.gamma.app/v1.0/generations"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def _post(api_key, body):
    req = urllib.request.Request(
        API_BASE, data=json.dumps(body).encode("utf-8"),
        headers={"X-API-KEY": api_key, "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": UA},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gamma 요청 실패(HTTP {e.code}): "
                           f"{e.read().decode('utf-8','ignore')}")


def _status(api_key, gen_id):
    req = urllib.request.Request(
        f"{API_BASE}/{gen_id}",
        headers={"X-API-KEY": api_key, "Accept": "application/json",
                 "User-Agent": UA}, method="GET")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())


def _themes(body_text, limit=4):
    """본문에서 소제목(이모지로 시작하는 짧은 줄)을 테마로 뽑는다."""
    out = []
    for line in body_text.split("\n"):
        s = line.strip()
        if not s or len(s) > 45:
            continue
        first = s[0]
        # 이모지/기호로 시작하고 마침표로 끝나지 않는 줄 = 소제목
        if ord(first) > 0x2300 and not s.endswith(("다.", "요.", ".")):
            out.append(s)
        if len(out) >= limit:
            break
    return out


def make_gamma_image(data):
    cfg = load_config()
    api_key = (cfg.get("gamma_api_key") or "").strip()
    if not api_key or "여기" in api_key:
        raise RuntimeError("config.json 의 gamma_api_key 가 비어 있습니다.")
    icfg = cfg.get("image", {})
    dims = icfg.get("dimensions", "16x9")

    themes = _themes(data.get("body", ""))
    date_kr = f"{datetime.now():%Y년 %m월 %d일}"
    # 제목/날짜를 내가 직접 명시하고 preserve 로 그대로 쓰게 해 날짜 오류·텍스트 깨짐을 줄인다
    # 배너 제목은 그날 에디션 라벨을 따른다(매일 발행이라 '주간'은 맞지 않는다).
    label = (cfg.get("blog", {}) or {}).get("brief_label", "재난안전 뉴스 브리핑")
    head = f"{label}\n{date_kr}"
    input_text = head + "\n\n" + "\n".join(themes) if themes else head

    req_body = {
        "inputText": input_text,
        "format": "social",
        "exportAs": "png",
        "numCards": 1,
        "textMode": "preserve",
        "cardOptions": {"dimensions": dims},
        "textOptions": {"language": "ko"},
        "additionalInstructions": icfg.get(
            "style_instructions",
            "한국 재난안전 뉴스 브리핑 대표 이미지. 신뢰감 있는 남색·적색 톤, "
            "또렷한 가독성, 깔끔한 카드 레이아웃, 주제별 단순 아이콘. "
            "로고·엠블럼·영문 워드마크는 만들지 말고 제공된 한글 텍스트만 사용."),
    }
    if icfg.get("theme_id"):
        req_body["themeId"] = icfg["theme_id"]

    log(f"Gamma 헤더 이미지 생성 요청({dims})...")
    return _run_generation(api_key, req_body)


def _run_generation(api_key, req_body):
    """POST → 폴링 → 다운로드 → PNG 경로 반환. (단일카드=PNG직접, 다중=zip)"""
    res = _post(api_key, req_body)
    gen_id = res.get("generationId")
    if not gen_id:
        raise RuntimeError(f"generationId 없음: {res}")

    export_url = None
    deadline = time.time() + 360
    while time.time() < deadline:
        time.sleep(8)
        st = _status(api_key, gen_id)
        status = st.get("status")
        if status == "completed":
            export_url = st.get("exportUrl")
            cr = st.get("credits", {})
            log(f"Gamma 완료(크레딧 차감 {cr.get('deducted')}, 잔여 {cr.get('remaining')})")
            break
        if status == "failed":
            raise RuntimeError(f"Gamma 생성 실패: {st.get('error')}")
        log(f"Gamma 생성 중...(status={status})")
    if not export_url:
        raise RuntimeError("Gamma 생성 시간 초과(6분)")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    raw_path = os.path.join(POSTS_DIR, f"{stamp}_gamma.bin")
    _download(export_url, raw_path)
    with open(raw_path, "rb") as f:
        magic = f.read(8)
    if magic[:4] == b"\x89PNG":
        png_path = os.path.join(POSTS_DIR, f"{stamp}_gamma.png")
        os.replace(raw_path, png_path)
        return png_path
    if magic[:2] == b"PK":
        out_dir = os.path.join(POSTS_DIR, f"gamma_{stamp}")
        os.makedirs(out_dir, exist_ok=True)
        with zipfile.ZipFile(raw_path) as z:
            z.extractall(out_dir)
        pngs = [os.path.join(out_dir, n) for n in os.listdir(out_dir)
                if n.lower().endswith(".png")]
        if not pngs:
            raise RuntimeError("Gamma zip 에 PNG 없음")
        return pngs[0]
    raise RuntimeError(f"Gamma exportUrl 형식 불명(magic={magic!r})")


def make_news_gamma_image(block):
    """기사 이미지가 없는 뉴스 블록용 대체 이미지 1장을 Gamma 로 만든다."""
    cfg = load_config()
    api_key = (cfg.get("gamma_api_key") or "").strip()
    if not api_key or "여기" in api_key:
        raise RuntimeError("gamma_api_key 없음")
    dims = cfg.get("image", {}).get("dimensions", "16x9")
    heading = block.get("heading", "")
    para = (block.get("paragraph", "") or "")[:180]
    input_text = f"{heading}\n\n{para}"
    req_body = {
        "inputText": input_text,
        "format": "social",
        "exportAs": "png",
        "numCards": 1,
        "textMode": "condense",
        "cardOptions": {"dimensions": dims},
        "textOptions": {"language": "ko"},
        "additionalInstructions": (
            "한국 재난안전 뉴스 한 건을 설명하는 정보 이미지. 신뢰감 있는 남색 톤, "
            "주제에 어울리는 단순 아이콘, 또렷한 가독성. 로고·영문 워드마크 금지, "
            "제공된 한글 텍스트만 사용."),
    }
    log(f"Gamma 뉴스 대체 이미지 생성({dims}): {heading[:24]}")
    return _run_generation(api_key, req_body)


if __name__ == "__main__":
    import sys
    files = sorted(f for f in os.listdir(POSTS_DIR) if f.endswith(".json"))
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(POSTS_DIR, files[-1])
    with open(path, "r", encoding="utf-8") as f:
        print(make_gamma_image(json.load(f)))
