"""GeoAI·생성형AI 개념 시리즈 — 기획된 주제 목록을 하루 1편씩 글로 써서 발행한다.

career_series.py 는 본문까지 손으로 써 두었지만, 여기는 주제 수가 많고 설명 글이라
**주제·관점만 목록으로 두고 본문은 Claude 가 쓴다**. 주제 목록이 있으므로 매번
'무슨 글을 쓸지' 흔들리지 않고, 순서대로 빠짐없이 나간다.

사용:
    python geoai_series.py --dry     # 오늘 나갈 1편을 생성만 하고 보여준다(발행 안 함)
    python geoai_series.py --plan    # 무엇이 남았는지만 출력(API 호출 없음)
    python geoai_series.py --go      # 실제 발행(보통은 geoai_daily.py 가 호출)
"""
import json
import os
import re
import sys
from datetime import datetime

from anthropic import Anthropic

from common import BASE_DIR, load_config, log
from geoai_blogger import channel_links_html, publish, service, blog_id, posted_titles
from post_blogger import _esc

STATE_PATH = os.path.join(BASE_DIR, "geoai_state.json")

# (slug, 제목, 글의 관점/꼭 다룰 것, 태그) — 순서대로 하루 1편씩 나간다.
# 제목은 사람들이 실제로 검색할 말로 짓는다(개념어 + '무엇/어떻게').
TOPICS = [
    ("what-is-geoai", "GeoAI란 무엇인가? 공간정보와 인공지능이 만나면",
     "GeoAI 의 정의, 기존 GIS 분석과 무엇이 다른지, 어디에 쓰이는지(재난·도시·농업·환경). 첫 편이므로 시리즈 전체 지도를 간단히 보여준다.",
     ["GeoAI", "공간정보", "GIS", "인공지능"]),
    ("gis-vs-geoai", "GIS와 GeoAI는 어떻게 다른가 | 규칙 기반과 학습 기반",
     "전통 GIS 의 규칙·수식 기반 분석과 학습 기반 모델의 차이, 각각 잘하는 일과 한계, 둘을 섞어 쓰는 실제 흐름.",
     ["GIS", "GeoAI", "공간분석"]),
    ("satellite-basics", "위성영상 기초 | 해상도·밴드·광학과 SAR의 차이",
     "공간/시간/분광 해상도, 광학과 SAR 의 차이와 장단점(구름·야간), 재난 상황에서 어느 쪽을 쓰는지.",
     ["위성영상", "원격탐사", "SAR"]),
    ("spectral-index", "NDVI·NDWI는 무엇을 보는 지표인가",
     "분광 지수의 원리(반사 특성), NDVI·NDWI·NBR 이 각각 무엇을 드러내는지, 산불 피해·가뭄·침수 판독에 쓰는 방법.",
     ["NDVI", "원격탐사", "분광지수"]),
    ("qgis-start", "QGIS 입문 | 처음 열고 무엇부터 해보면 되나",
     "무료 오픈소스 GIS 로 시작하는 법, 좌표계·레이어·속성테이블이라는 세 가지 기본 개념, 첫 실습 과제 제안.",
     ["QGIS", "GIS입문", "오픈소스GIS"]),
    ("crs-basics", "좌표계(CRS)가 헷갈릴 때 | EPSG:4326과 5186",
     "지리좌표계와 투영좌표계의 차이, 한국에서 자주 쓰는 EPSG 코드, 좌표계가 어긋났을 때 생기는 증상과 해결 순서.",
     ["좌표계", "EPSG", "GIS"]),
    ("geopandas", "파이썬으로 공간분석 시작하기 | GeoPandas 기초",
     "GeoDataFrame 개념, 파일 읽기·좌표변환·공간조인 흐름을 짧은 코드로. 엑셀·QGIS 로 하던 일을 코드로 옮길 때의 이점.",
     ["GeoPandas", "파이썬", "공간분석"]),
    ("earth-engine", "Google Earth Engine이란? 클라우드에서 위성영상 분석",
     "내 컴퓨터에 영상을 내려받지 않고 분석하는 방식, 컬렉션·필터·리듀서라는 사고 틀, 어떤 작업에 특히 유리한지.",
     ["EarthEngine", "위성영상", "클라우드"]),
    ("label-data", "공간 AI의 학습 데이터는 어떻게 만드나 | 라벨링과 품질",
     "위성·드론 영상 라벨링 방식(점·폴리곤·마스크), 클래스 불균형과 지역 편향 문제, 좋은 데이터셋의 조건.",
     ["학습데이터", "라벨링", "GeoAI"]),
    ("cnn-remote-sensing", "위성영상에 딥러닝을 쓰면 | 분류·탐지·분할의 차이",
     "영상 분류, 객체 탐지, 의미론적 분할이 각각 답하는 질문과 산출물, 재난 판독에서 어느 것을 골라야 하는지.",
     ["딥러닝", "객체탐지", "영상분할"]),
    ("landcover", "토지피복 분류 | 위성으로 땅의 쓰임을 읽는 법",
     "토지피복 분류의 개념과 쓰임(도시화·불투수면·유출계수), 정확도 평가(혼동행렬·카파)를 쉬운 말로.",
     ["토지피복", "원격탐사", "정확도평가"]),
    ("sar-flood", "SAR 위성으로 침수 지역을 찾는 원리",
     "물이 SAR 영상에서 어둡게 보이는 이유, 변화탐지로 침수 범위를 잡는 절차, 오탐(그림자·매끈한 지면) 주의점.",
     ["SAR", "침수", "재난탐지"]),
    ("landslide-susceptibility", "산사태 위험지도는 어떻게 만드나 | 취약성 모델링",
     "경사·지질·강우 등 입력 인자, 통계·머신러닝 취약성 모델의 흐름, 지도 해석 시 주의할 점(확률이지 예언이 아니다).",
     ["산사태", "위험지도", "머신러닝"]),
    ("wildfire", "산불을 위성으로 감시하고 피해를 추정하는 법",
     "열적외 밴드 기반 화점 탐지, dNBR 로 피해 심도 산정, 조기 감지와 사후 평가의 역할 차이.",
     ["산불", "원격탐사", "dNBR"]),
    ("drone-mapping", "드론 사진측량 | 사진 몇 장이 지도가 되기까지",
     "중복도·GCP·SfM 처리 흐름, 산출물(정사영상·DSM·점군)과 재난 현장에서의 활용, 비행 전 확인할 제도적 사항.",
     ["드론", "사진측량", "정사영상"]),
    ("lidar-dem", "LiDAR와 DEM | 지형 데이터가 방재에 쓰이는 방식",
     "DSM 과 DEM 의 차이, LiDAR 로 수목 아래 지형을 얻는 원리, 침수·산사태 모의에 지형 정확도가 중요한 이유.",
     ["LiDAR", "DEM", "지형분석"]),
    ("interpolation", "관측점 사이는 어떻게 채우나 | 공간 보간과 크리깅",
     "IDW·크리깅 등 보간의 기본 아이디어, 강우·미세먼지 지도에서의 사용, 보간 결과를 과신하면 안 되는 이유.",
     ["공간보간", "크리깅", "공간통계"]),
    ("spatial-autocorrelation", "가까운 것은 닮는다 | 공간 자기상관과 핫스팟 분석",
     "토블러의 제1법칙, Moran's I 와 핫스팟(Getis-Ord) 의 의미, 사고·재난 발생 지점 분석에 쓰는 방법.",
     ["공간통계", "핫스팟분석", "공간자기상관"]),
    ("change-detection", "시계열 변화탐지 | 같은 곳을 다른 시점으로 비교하기",
     "전후 비교와 시계열 분해의 차이, 계절·촬영조건이 만드는 가짜 변화, 개발·침수·붕괴 판독 사례.",
     ["변화탐지", "시계열", "위성영상"]),
    ("digital-twin", "디지털트윈은 지도와 무엇이 다른가",
     "정적 지도 → 3차원 모델 → 실시간 연동 모델로 이어지는 단계, 도시 침수·대피 시뮬레이션에서의 쓰임과 한계.",
     ["디지털트윈", "스마트시티", "시뮬레이션"]),
    ("foundation-model", "지구관측 파운데이션 모델이란 | 범용 모델이 지도에 오다",
     "대규모 사전학습 모델이 원격탐사에 들어오며 달라진 점(적은 라벨로 적응), 분할 기반 모델의 활용 방식과 검증 필요성.",
     ["파운데이션모델", "GeoAI", "원격탐사"]),
    ("llm-for-gis", "생성형 AI로 공간분석 코드를 짜는 법",
     "LLM 에게 공간분석을 시킬 때의 요령(데이터 스키마·좌표계·검증 요구), 자주 나오는 오류와 결과를 반드시 눈으로 확인해야 하는 이유.",
     ["생성형AI", "LLM", "공간분석"]),
    ("gis-agent", "자연어로 지도를 묻는다 | LLM 에이전트와 GIS 연동",
     "도구 호출(function calling)로 GIS 기능을 붙이는 구조, 자연어 질의가 공간 질의로 번역되는 과정, 신뢰성 확보 장치.",
     ["LLM", "AI에이전트", "GIS"]),
    ("rag-manual", "재난 매뉴얼 챗봇 만들기 | RAG의 기본 구조",
     "검색증강생성(RAG)의 구성요소, 매뉴얼·조례처럼 근거가 중요한 문서에 왜 적합한지, 출처 표기와 최신성 관리.",
     ["RAG", "생성형AI", "재난매뉴얼"]),
    ("geoai-ethics", "GeoAI의 그늘 | 프라이버시·편향·오탐의 대가",
     "위치정보의 민감성, 학습 데이터 지역 편향, 오탐/미탐이 재난 대응에서 갖는 비대칭적 비용, 공개 시 지켜야 할 원칙.",
     ["AI윤리", "프라이버시", "GeoAI"]),
    ("geoai-career", "GeoAI로 진로를 잡으려면 | 배울 것과 포트폴리오",
     "필요한 역량 묶음(GIS·프로그래밍·도메인), 단계별 학습 순서, 포트폴리오로 쓸 만한 프로젝트 예시와 공개 데이터.",
     ["GeoAI진로", "포트폴리오", "공간정보"]),
]

SYSTEM = """너는 공간정보(GIS)와 인공지능을 처음 배우는 사람에게 쉽게 설명하는 한국어 기술 블로그 작가다.
지켜야 할 원칙:
- 개념과 원리를 정확하게 설명한다. 확인되지 않은 수치, 연도, 기관명, 제품 사양, 논문 제목,
  최신 버전·순위 같은 것은 지어내지 않는다. 필요하면 "도구에 따라 다르다" 처럼 일반론으로 쓴다.
- 특정 제품/서비스의 현재 상태를 단정하지 않는다("현재 무료다", "가장 정확하다" 금지).
- 전문용어는 처음 나올 때 한 줄로 풀어 준다. 비유를 한두 개 쓰되 과장하지 않는다.
- 과장·공포 조장·낚시성 표현을 쓰지 않는다.
- 마크다운 강조 기호(#, *, - 등)를 쓰지 않는다. 코드 예시가 꼭 필요할 때만 ``` 로 감싼다.
- 출력은 반드시 지정된 구분자(===) 형식만 반환한다."""

USER = """시리즈: 'GeoAI와 생성형AI' 블로그의 개념 시리즈 {n}편
글 제목: {title}
이번 글의 관점(반드시 반영): {angle}
오늘 날짜: {today}
말투: 친근하지만 군더더기 없는 설명체(존댓말)

요구사항
- 전체 본문 2,000자 이상. 같은 말을 되풀이해 늘리지 말고 원리·예시·주의점으로 채운다.
- 본문 소제목은 4~5개, 사람들이 검색창에 칠 법한 '질문형'으로 쓴다.
  (예: "SAR 영상에서 물은 왜 어둡게 보이나요?")
- 소제목마다 맨 앞에 어울리는 이모지 1개.
- 각 소제목 본문은 300~450자. 마지막 1~2문장은 재난안전(홍수·산사태·산불·대피 등)이나
  실제 업무에서 이 개념이 어떻게 쓰이는지로 연결한다.
- 최소 한 곳에는 '해봐야 아는 것'(직접 확인할 절차나 판단 기준)을 넣는다.
- 코드 예시는 필요한 글에서만 3~10줄, ``` 로 감싼다. 없어도 된다.

이미 발행한 글(내용이 겹치지 않게 참고):
{recent}

반드시 아래 형식 그대로 응답해. 마커(===)는 글자 그대로. 그 외 설명 금지.

===요약===
이 글의 핵심 3줄. 각 줄은 '· '로 시작하고 40자 내외, 한 줄에 하나의 내용만.
===도입===
이 개념이 왜 필요한지 보여주는 짧은 장면이나 질문으로 시작하는 1~2단락(250자 이상).
===본문===
## 🛰️ 질문형 소제목
본문 단락
## 🌊 질문형 소제목
본문 단락
(이런 식으로 4~5개. 소제목 줄은 반드시 '## ' 로 시작)
===해보기===
독자가 오늘 바로 해볼 수 있는 확인·실습 2~3가지. 각 줄은 '· '로 시작, 한 줄 한 가지.
무료로 접근 가능한 방법 위주로 쓰되, 특정 서비스의 가격·정책은 단정하지 않는다.
===FAQ===
이 주제로 사람들이 실제로 검색할 법한 질문 3개.
'Q. 질문' 다음 줄에 'A. 답변(2~3문장)' 형식.
===마무리===
한 단락(150자 이상). 다음 편으로 이어질 궁금증을 한 문장 남긴다.
===태그===
검색에 걸릴 만한 태그 8~11개를 쉼표로."""


def state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"posted": {}}


def save_state(s):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def post_title(idx, title):
    return f"{title} | GeoAI 기초 {idx}편"


def next_topic(done_titles=()):
    """아직 안 나간 첫 주제. (로컬 상태 + 블로그에 실제로 있는 제목) 둘 다 본다.

    상태 파일이 지워지거나 다른 기기에서 돌아도 같은 글이 두 번 나가지 않게 한다."""
    done = set(state().get("posted", {}))
    for i, t in enumerate(TOPICS, start=1):
        if t[0] in done:
            continue
        if post_title(i, t[1]) in done_titles:
            continue
        return i, t
    return None, None


def _split(text):
    """===마커=== 로 나눈 구간 dict."""
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^===\s*([^=]+?)\s*===$", line.strip())
        if m:
            cur = m.group(1).strip()
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def _lines(block):
    return [re.sub(r"^[·\-•*]\s*", "", l).strip()
            for l in (block or "").splitlines() if l.strip()]


def _prose_html(text):
    """빈 줄로 나뉜 덩어리를 <p> 로. ``` 로 감싼 부분은 <pre> 로."""
    parts = []
    for i, seg in enumerate(re.split(r"```", text or "")):
        if i % 2:                                   # 코드 블록
            body = seg.strip("\n")
            body = re.sub(r"^[a-zA-Z0-9_+-]{0,12}\n", "", body)   # 첫 줄 언어 표기 제거
            if body.strip():
                parts.append("<pre style=\"background:#f6f8fa;padding:12px;"
                             "overflow-x:auto\"><code>" + _esc(body) + "</code></pre>")
            continue
        for chunk in re.split(r"\n\s*\n", seg.strip()):
            if chunk.strip():
                parts.append("<p>" + _esc(chunk.strip()).replace("\n", "<br>") + "</p>")
    return "\n".join(parts)


def _sections(block):
    """'## 소제목' 단위로 (소제목, 본문) 목록."""
    out = []
    for part in re.split(r"^##\s+", block or "", flags=re.M):
        part = part.strip()
        if not part:
            continue
        head, _, rest = part.partition("\n")
        out.append((head.strip(), rest.strip()))
    return out


def generate(idx, topic, cfg=None, recent=()):
    """한 편을 생성한다. 형식·분량이 모자라면 최대 3번까지 다시 쓴다."""
    cfg = cfg or load_config()
    slug, title, angle, tags = topic
    client = Anthropic(api_key=cfg["anthropic_api_key"])
    user = USER.format(n=idx, title=title, angle=angle,
                       today=f"{datetime.now():%Y-%m-%d}",
                       recent="\n".join(f"- {t}" for t in list(recent)[-12:]) or "(없음)")
    min_chars = int((cfg.get("geoai") or {}).get("min_chars", 1800))
    best = None
    for attempt in range(1, 4):
        msg = client.messages.create(
            model=cfg.get("model", "claude-sonnet-4-6"),
            max_tokens=8000, system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        S = _split(msg.content[0].text.strip())
        secs = _sections(S.get("본문", ""))
        data = {
            "slug": slug, "title": post_title(idx, title), "index": idx,
            "summary": _lines(S.get("요약", ""))[:3],
            "intro": S.get("도입", ""), "sections": secs,
            "practice": _lines(S.get("해보기", "")),
            "faq": S.get("FAQ", "") or S.get("자주묻는질문", ""),
            "outro": S.get("마무리", ""),
            "tags": [t.strip() for t in re.split(r"[,\n]", S.get("태그", "")) if t.strip()] or list(tags),
        }
        length = len(data["intro"]) + len(data["outro"]) + sum(
            len(h) + len(p) for h, p in secs)
        ok = bool(data["intro"] and data["outro"]) and len(secs) >= 3
        if ok and (best is None or length > best[1]):
            best = (data, length)
        if ok and length >= min_chars and len(secs) >= 4:
            log(f"본문 {length}자 / 소제목 {len(secs)}개 — 생성 완료")
            return data
        log(f"분량·형식 미달(시도 {attempt}/3: 본문 {length}자, 소제목 {len(secs)}개) → 재시도")
    if best is None:
        raise RuntimeError("시리즈 글 생성 형식 파싱 실패(3회).")
    log("3회 시도 후 기준 미달 → 그중 가장 긴 결과로 진행합니다.")
    return best[0]


def build_html(data, cfg=None):
    cfg = cfg or load_config()
    P = []
    if data.get("summary"):
        P.append("<h3>📌 3줄 요약</h3><ul>"
                 + "".join(f"<li>{_esc(s)}</li>" for s in data["summary"]) + "</ul>")
    P.append(_prose_html(data.get("intro", "")))
    for head, body in data.get("sections", []):
        P.append(f"<h3>{_esc(head)}</h3>")
        P.append(_prose_html(body))
    if data.get("practice"):
        P.append("<h3>🧪 직접 해보기</h3><ul>"
                 + "".join(f"<li>{_esc(s)}</li>" for s in data["practice"]) + "</ul>")
    if data.get("faq"):
        P.append("<h3>❓ 자주 묻는 질문</h3>" + _prose_html(data["faq"]))
    if data.get("outro"):
        P.append(_prose_html(data["outro"]))
    P.append(f'<p><em>GeoAI 기초 시리즈 {data.get("index","")}편 · 전체 {len(TOPICS)}편</em></p>')
    P.append(channel_links_html(cfg))
    return "\n".join(p for p in P if p)


def run(dry_run=False, cfg=None):
    """오늘 나갈 1편을 생성해 발행한다. 결과 dict 를 돌려준다."""
    cfg = cfg or load_config()
    have = set()
    if not dry_run:
        try:
            have = posted_titles(service(), blog_id(cfg))
        except Exception as e:
            log(f"GeoAI: 기존 글 목록 확인 실패({type(e).__name__}) — 로컬 상태로만 판단합니다")
    idx, topic = next_topic(have)
    if topic is None:
        log("GeoAI 시리즈: 남은 주제가 없습니다(TOPICS 에 주제를 더 넣어주세요).")
        return {"status": "exhausted"}
    log(f"GeoAI 시리즈 {idx}/{len(TOPICS)}편 생성: {topic[1]}")
    s = state()
    recent = [v.get("title", "") for v in s.get("posted", {}).values()]
    data = generate(idx, topic, cfg, recent)
    html = build_html(data, cfg)
    r = publish(data["title"], html, data["tags"] + list(topic[3]),
                dry_run=dry_run, cfg=cfg)
    if r.get("status") == "published":
        s.setdefault("posted", {})[topic[0]] = {
            "title": data["title"], "url": r.get("url", ""),
            "date": f"{datetime.now():%Y-%m-%d}"}
        save_state(s)
    r["title"] = data["title"]
    r["kind"] = "series"
    return r


if __name__ == "__main__":
    if "--plan" in sys.argv:
        done = set(state().get("posted", {}))
        for i, t in enumerate(TOPICS, start=1):
            print(("[완료] " if t[0] in done else "[대기] ") + f"{i:2d}. {t[1]}")
        idx, topic = next_topic()
        print("\n다음 발행 예정:", post_title(idx, topic[1]) if topic else "없음")
        raise SystemExit(0)
    go = "--go" in sys.argv
    print(json.dumps(run(dry_run=not go), ensure_ascii=False, indent=2))
