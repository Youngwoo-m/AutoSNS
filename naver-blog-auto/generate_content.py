"""실제 뉴스(Google News RSS)를 바탕으로 이번 주 재난안전 블로그 글을 생성한다.

반환: dict(title, body, tags) + posts/ 폴더에 저장.
사실성 원칙: 제공된 뉴스 목록에 없는 구체적 사실(사망자 수, 날짜, 지명 등)은
지어내지 않는다. 안전 수칙 등 일반 정보는 일반론으로 명확히 구분해 작성한다.
글 하단에는 실제 기사 출처 링크를 붙여 독자가 검증할 수 있게 한다.
"""
import sys
import json
import os
import re
from datetime import datetime

from anthropic import Anthropic

from common import POSTS_DIR, load_config, load_history, save_history, log

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.keyword_terms import GEO_TERMS, TAG_DISASTER_TERMS, TAG_REGION_TERMS  # noqa: E402
from fetch_news import fetch_news

SYSTEM = """너는 한국의 __DOMAIN__ 분야 블로그를 운영하는 세명대학교 재난안전학과의 필진이다.
독자는 제천·충북 주민과 재난안전 분야 수험생·학생이다.

<원칙 — 아래 순서대로 우선한다>
1. 사실: '제공된 뉴스 목록'에 있는 내용만 사실로 쓴다. 목록에 없는 수치·사상자 수·날짜·장소·
   인용문은 절대 만들지 않는다. 제목만으로 단정하기 어려운 세부는 "~로 알려졌다",
   "자세한 내용은 원문 참고"로 쓴다.
2. 형식: 지정된 구분자(===, @출처:) 형식만 출력한다. JSON·마크다운 기호(#, *, -)·설명 문장을
   붙이지 않는다. 네이버 블로그에 그대로 붙여넣을 순수 텍스트다.
3. 해설: 각 뉴스 블록은 요약으로 끝내지 않고, 마지막 2~3문장을 학과의 시각에서 쓴 의견으로 채운다.
4. 어조: 과장·공포 조장·낚시성 표현 없이 차분하고 신뢰감 있게 쓴다.
5. __TIPSLABEL__ 정보는 널리 알려진 일반 정보만 쓰고, 일반 정보임이 드러나게 쓴다.

시점 표현: 이 글은 매일 한 편씩 올리는 연재다. '이번 주'라는 말을 쓰지 말고 '오늘', '최근'을 쓴다."""

USER_TEMPLATE = """블로그 주제: {topic}
말투: {tone}
오늘 날짜: {today}

<뉴스 목록> (각 줄 맨 앞 번호가 출처 번호)
{news_block}
</뉴스 목록>

<최근 쓴 부제 — 겹치지 않게>
{recent}
</최근 쓴 부제>

위 뉴스 목록으로 '__BRIEF_LABEL__' 글을 쓴다.

<내용 요구>
- 뉴스 4~5건을 골라 한 건에 한 블록. 현장 사건·정책/제도·산업/신기술을 고루 섞는다.
- 블록 첫 줄은 반드시 '@출처:<번호>'(목록의 실제 번호). 다음 줄은 이모지 1개로 시작하는
  질문형 소제목(사람들이 검색창에 칠 문장. 예: "제천 호우 때 대피는 어떻게 하나요?").
- 블록 본문은 블록마다 300~380자(최소 300자) = 무슨 일인지(사실) → 왜 중요한지 → 해설 2~3문장.
  · 사실 부분에 기관·지역·날짜·수치가 한 문장에 함께 든 문장을 1개 이상 넣는다(목록에 있는 것만).
    (예: "행정안전부는 2026년 9월 10일 강원 지역에 드론 22대를 투입했다.")
  · 해설은 다음 중 하나 이상: 제천·충북에 주는 의미 / 학과 개념(재해영향평가, BCP, GeoAI,
    위험성 평가)과의 연결 / 주민·수험생이 대비할 점. 기사 문장을 바꿔 쓴 것이 아니라 기사에 없는
    '판단'을 담고, "~로 보입니다", "~할 필요가 있습니다"처럼 의견임이 드러나게 블록 끝에 모아 쓴다.
- 분량: 인사 250자 이상, 마무리 150자 이상, 본문 전체 2,000자 안팎(최소 1,800자). 같은 말 반복이 아니라
  배경·영향·대응 관점으로 채운다.
- 마무리는 오늘 다룬 소식들을 꿰는 흐름을 한 문장으로 정리한다
  (예: "최근 소식은 감시 기술이 예방 단계로 옮겨 가고 있음을 보여 줍니다.").
</내용 요구>

<출력 직전 확인 — 결과에만 반영하고 확인 과정은 쓰지 않는다>
- 모든 @출처 번호가 목록에 있는 번호인가
- 목록에 없는 수치·날짜·인용이 없는가
- '이번 주'라는 표현이 없는가
- 블록마다 300자 이상인가
</출력 직전 확인>

반드시 아래 형식 그대로 응답해. 마커(===, @출처:)는 글자 그대로. 그 외 설명 금지.

===부제===
검색이 잘 되도록 __SUBKW__ 키워드를 **맨 앞**에 넣은 한 줄 부제(18~28자).
- 사람이 검색창에 실제로 칠 말로 시작한다(예: "추석 화재 예방 수칙", "지진 대피 요령").
- 여러 주제를 '·'로 나열하지 않는다. 하나만 고른다 — 나열하면 무엇으로도 검색되지 않는다.
- "총정리", "주간 브리핑" 같은 형식어로 채우지 않는다.
사람들이 실제로 검색할 말로 시작한다. (예: __SUBEX__)
===태그===
검색에 걸릴 만한 핵심 태그 10~13개를 쉼표로. 지명·재난유형·기관·주제어 등
사람들이 실제로 검색할 말로. (예: 재난안전, 집중호우, 제천, 드론재난, 세명대학교)
===요약===
이 글의 핵심을 3줄로. 각 줄은 '· '로 시작하고 40자 내외, 한 줄에 하나의 사실만.
수치·지역·기관이 들어가면 더 좋다. (검색 스니펫·AI 요약이 이 부분을 가져간다)
===리드===
검색 결과 미리보기에 그대로 쓰이는 글 첫 문단. 1~2문장, 합쳐서 80~150자.
- 본문과 같은 존댓말('~습니다')로 쓴다. '~다'로 끝나는 기사체를 쓰지 않는다.
- 첫 문장은 부제 맨 앞의 검색어로 시작하고, 무슨 일이 있었는지 핵심 사실을 바로 말한다.
- 두 번째 문장(쓸 경우)도 사실이나 독자가 알아 둘 점을 하나 더 준다. 두 문장 모두에 '오늘은',
  '이 글에서는', '이번 글', '정리했습니다', '살펴봅니다', '알아봅니다' 같은 안내 문구를 쓰지 않는다 —
  미리보기 칸이 짧아 정보가 아닌 말은 그대로 버려진다.
- 위 뉴스 목록에 없는 수치·지명·날짜는 넣지 않는다.
좋은 예: 축제장 안전사고가 가을 지역 행사에서 잇따르고 있습니다. 관람객이 몰리는 무대 주변과 임시 구조물은 행사 전 하중·동선 점검이 필요합니다.
나쁜 예: 축제장 안전사고가 반복되고 있다. 오늘은 관련 사고와 생활안전 이슈를 정리해본다.
===인사===
짧은 인사 + 오늘 다룰 소식 요약 (1~2단락).
★ 첫 문장에 이 글의 핵심 검색 키워드(__SUBKW__·'__DOMAIN__')를 자연스럽게 넣는다.
(네이버는 첫 문단을 검색에 크게 반영한다. 단, 키워드 나열이 아니라 문장으로 녹인다.)
===뉴스===
@출처:3
🌧️ 소제목
사실 위주 본문 단락
@출처:1
🤝 소제목
본문 단락
(이런 식으로 4~5개 블록. 각 블록 첫 줄은 반드시 @출처:번호)
===안전수칙===
🧰 소제목(섹션 이름은 __TIPSLABEL__)
__TIPSDESC__
===자주묻는질문===
오늘 다룬 내용과 관련해 사람들이 실제로 검색할 법한 질문 3개와 답을 쓴다.
형식은 'Q. 질문' 다음 줄에 'A. 답변(2~3문장, 사실 위주)'. 질문은 지역·상황을 구체적으로.
===마무리===
마무리 한마디"""


# 태그 자동 보강 키워드 — 공통 목록은 shared/keyword_terms.py 에 있다.
# 블로그는 글이 길어 본문에 걸리는 표현이 많으므로 아래를 더 붙인다.
EXTRA_TAG_TERMS = ["열사병", "붕괴", "실종", "대피", "재난문자", "특보", "경보"]
DISASTER_TERMS = TAG_DISASTER_TERMS + EXTRA_TAG_TERMS
REGION_TERMS = TAG_REGION_TERMS



MIN_NEWS = 2


class NoNewsError(RuntimeError):
    """이 판의 주제로 모인 뉴스가 너무 적다(run_weekly 가 대체 판으로 바꾼다)."""

def _detected_tags(subtitle, blocks, news):
    """부제·본문 소제목·뉴스 제목에서 지역/재난 키워드를 뽑아 검색 태그로 쓴다.

    뉴스 제목 끝의 ' - 언론사'는 제거해 출처명 오탐(예: '서울경제TV'→'서울')을 막는다.
    """
    strip = lambda t: re.sub(r"\s*-\s*[^-]+$", "", t or "")
    hay = subtitle + " " + " ".join(b.get("heading", "") for b in blocks)
    hay += " " + " ".join(strip(n.get("title", "")) for n in news)
    # 학과별 키워드는 config.keywords 로 덮어쓸 수 있다(없으면 아래 기본값=재난안전).
    kw = load_config().get("keywords", {})
    terms = (kw.get("tag_terms") or (DISASTER_TERMS + GEO_TERMS)) \
        + (kw.get("region_terms") or REGION_TERMS)
    # 본문은 "안전 훈련", "생성형 AI" 처럼 띄어 쓰는 일이 잦다. 띄어쓰기를 지운 사본과도
    # 맞춰 보되, 태그로 붙는 값은 목록에 적힌 붙여 쓴 형태다(해시태그에 공백이 못 들어간다).
    flat = hay.replace(" ", "")
    return [term for term in terms
            if term in hay or term.replace(" ", "") in flat]


def _news_block(news):
    if not news:
        return "(최근 수집된 뉴스가 없습니다. 일반적인 재난안전 정보 글로 작성하세요.)"
    lines = []
    for i, n in enumerate(news, 1):
        src = f" / {n['source']}" if n["source"] else ""
        lines.append(f"{i}. [{n['published_str']}{src}] {n['title']}")
    return "\n".join(lines)


def _sources_footer(news):
    if not news:
        return ""
    lines = ["", "─────────────", "📰 참고한 뉴스 출처 (검색어로 확인 가능)"]
    for n in news:
        # 제목 끝에 이미 ' - 언론사' 가 붙어 있어 출처를 중복 표기하지 않는다
        lines.append(f"· [{n['published_str']}] {n['title']}")
    return "\n".join(lines)


def _section(text, start, end):
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = text.find(end, i) if end else -1
    return (text[i:j] if j >= 0 else text[i:]).strip()


def _parse_structured(text, news):
    """부제/태그/인사/뉴스(@출처:N)/안전수칙/마무리 구조를 파싱한다."""
    subtitle = _section(text, "===부제===", "===태그===")
    # 태그 구간 끝은 바로 다음 섹션(===요약===)이다. '===인사===' 로 두면 그 사이의
    # 요약 본문까지 태그로 빨려 들어간다(2026-09-16 '===요약===', '·', '40분' 이 태그로 저장됨).
    tags_raw = _section(text, "===태그===", "===요약===")
    # 요약 다음 칸은 ===리드=== 다. 모델이 리드를 빠뜨리면 예전처럼 ===인사=== 까지.
    summary = _section(text, "===요약===", "===리드===" if "===리드===" in text else "===인사===")
    intro = _section(text, "===인사===", "===뉴스===")
    news_raw = _section(text, "===뉴스===", "===안전수칙===")
    tips = _section(text, "===안전수칙===", "===자주묻는질문===")
    faq = _section(text, "===자주묻는질문===", "===마무리===")
    outro = _section(text, "===마무리===", "")
    # 태그 정규화: '#'·공백·쉼표·줄바꿈 모두로 쪼개 한 뭉치로 뭉치는 것을 방지.
    tags = [t for t in tags_raw.replace("#", " ").replace(",", " ").split() if t]

    blocks = []
    parts = re.split(r"@출처:\s*(\d+)", news_raw)  # [pre, idx, chunk, idx, chunk, ...]
    for k in range(1, len(parts), 2):
        try:
            idx = int(parts[k])
        except ValueError:
            continue
        chunk = parts[k + 1].strip() if k + 1 < len(parts) else ""
        if not chunk or not (1 <= idx <= len(news)):
            continue
        lines = chunk.split("\n")
        heading, rest = "", []
        for li, ln in enumerate(lines):
            if ln.strip():
                heading = ln.strip()
                rest = lines[li + 1:]
                break
        src = news[idx - 1]
        blocks.append({
            "index": idx, "heading": heading,
            "paragraph": "\n".join(rest).strip(),
            "source": {"title": src["title"], "link": src["link"],
                       "published_str": src["published_str"]},
        })
    return subtitle, tags, summary, intro, blocks, tips, faq, outro


def generate():
    cfg = load_config()
    blog = cfg["blog"]
    history = load_history()
    recent = "\n".join(f"- {t}" for t in history[-12:]) or "- (아직 없음)"

    # 도메인/팁/키워드 라벨(에디션별). 기본=재난안전. 토요일 AI판은 editions.ai 로 덮임.
    domain = cfg.get("domain", "재난안전")
    tips_label = cfg.get("tips_label", "안전수칙")
    tips_desc = cfg.get("tips_desc", "일반적으로 알려진 안전 수칙 1~2가지")
    sub_kw = cfg.get("subtitle_keyword_hint", "'지명 + 재난유형'")
    # 매일 발행이라 '주간 브리핑'은 맞지 않는다. 에디션마다 그날의 성격을 붙인다.
    brief_label = cfg.get("brief_label", "오늘의 재난안전 브리핑")
    sub_ex = cfg.get("subtitle_example",
                     '"제천·충북 집중호우 대비, 재난대책본부 가동", '
                     '"강원 산사태 위기경보, 여름철 안전수칙 총정리"')

    def _fill(t):
        return (t.replace("__DOMAIN__", domain)
                 .replace("__TIPSLABEL__", tips_label)
                 .replace("__TIPSDESC__", tips_desc)
                 .replace("__SUBKW__", sub_kw)
                 .replace("__SUBEX__", sub_ex)
                 .replace("__BRIEF_LABEL__", brief_label))

    system = _fill(SYSTEM)
    news = fetch_news()
    # 뉴스가 거의 없으면 글이 1,000자 남짓으로 끝나 분량 기준에 3번 떨어진다(9/3·9/10·9/22).
    # 모델을 부르기 전에 알려 실행부가 다른 판(지역 재난안전)으로 바꿔 쓰게 한다.
    if len(news) < MIN_NEWS:
        raise NoNewsError(f"뉴스 {len(news)}건(기준 {MIN_NEWS}건) — 이 판으로는 글을 쓸 수 없음")
    user_msg = _fill(USER_TEMPLATE).format(
        topic=blog["topic"],
        tone=blog.get("tone", "친근한 블로그 말투"),
        today=f"{datetime.now():%Y-%m-%d (%A)}",
        news_block=_news_block(news),
        recent=recent,
    )

    min_chars = int(blog.get("min_chars", 1200))
    min_blocks = int(blog.get("min_blocks", 4))

    def _body_len(intro, blocks, tips, outro):
        return len(intro) + len(tips) + len(outro) + sum(
            len(b.get("heading", "")) + len(b.get("paragraph", "")) for b in blocks)

    client = _llm_client(cfg)
    subtitle = intro = tips = outro = summary = faq = lead = ""
    tags, blocks = [], []
    best = None
    for attempt in range(1, 4):
        msg = client.messages.create(
            model=cfg.get("model", "claude-sonnet-4-6"),
            # 요약·해설·FAQ·마무리까지 담으려면 4000 으로는 중간에 끊긴다
            # (해설 규칙을 넣은 뒤 FAQ 가 잘리고 마무리가 비는 일이 있었다)
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = msg.content[0].text.strip()
        (subtitle, tags, summary, intro, blocks,
         tips, faq, outro) = _parse_structured(text, news)
        lead = _section(text, "===리드===", "===인사===")
        # 마무리까지 나와야 글이 끝까지 생성된 것이다(토큰 상한에 걸리면 뒤가 잘린다)
        ok_form = bool(subtitle and intro and outro) and len(blocks) >= 2
        length = _body_len(intro, blocks, tips, outro)
        # 가장 잘 나온 결과를 보관(전부 미달이면 이걸 쓴다)
        if ok_form and (best is None or length > best[-1]):
            best = (subtitle, tags, summary, intro, blocks, tips, faq, outro, lead, length)
        if ok_form and length >= min_chars and len(blocks) >= min_blocks:
            break
        log(f"분량/형식 미달(시도 {attempt}/3: 본문 {length}자 / 기준 {min_chars}자, "
            f"블록 {len(blocks)}개 / 기준 {min_blocks}개) → 재시도")
    else:
        if best is None:
            raise RuntimeError("글 생성 형식 파싱 실패(3회). 잠시 후 다시 시도하세요.")
        (subtitle, tags, summary, intro, blocks,
         tips, faq, outro, lead, _) = best
        log("3회 시도 후 기준 미달 → 그중 가장 긴 결과로 진행합니다.")
    if not (subtitle and intro and len(blocks) >= 2):
        raise RuntimeError("글 생성 형식 파싱 실패(3회). 잠시 후 다시 시도하세요.")
    log(f"본문 분량 {_body_len(intro, blocks, tips, outro)}자 (기준 {min_chars}자), "
        f"뉴스 {len(blocks)}블록")

    # 제목: 검색어가 앞, 브랜드는 짧게 뒤. 날짜는 넣지 않는다.
    #
    # 예전에는 '부제 | 세명대 재난안전학과 2026.09.21' 이었는데, 네이버 검색결과는
    # 제목을 30자 안팎에서 자른다. 날짜 11자가 잘리는 자리를 차지하면서 정작 검색어는
    # 밀려났다. 날짜는 글 메타데이터에 이미 있으므로 제목에서 뺀다.
    # (config.blog.title_suffix 를 빈 문자열로 두면 브랜드도 뺄 수 있다.)
    suffix = (cfg.get("title_suffix", "세명대 재난안전학과") or "").strip()
    title = f"{subtitle} | {suffix}" if suffix else subtitle
    # 태그: 감지된 지역·재난 키워드 + Claude 태그 + 고정 태그 + 지역 브랜딩(local_tags).
    # local_tags 는 에디션(ai/impact/biz)이 blog.tags 를 덮어써도 항상 유지된다
    # → "모든 게시물에 지역 태그 항상 추가" 규칙 보장(제천·충북 등).
    tags = list(dict.fromkeys(
        _detected_tags(subtitle, blocks, news) + (tags or [])
        + blog.get("tags", []) + cfg.get("local_tags", [])
    ))[:30]
    data = {
        "title": title, "subtitle": subtitle, "intro": intro,
        "news_blocks": blocks, "tips": tips, "outro": outro, "tags": tags,
        # 검색 스니펫·AI 요약이 가져가기 좋은 블록(글 맨 위 3줄 요약 / 맨 아래 FAQ)
        "summary": summary, "faq": faq,
        # 글 맨 첫 문단(검색어로 시작하는 1~2문장) — 검색 설명이 없을 때 미리보기에 쓰인다
        "lead": " ".join(lead.split()),
    }

    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    with open(os.path.join(POSTS_DIR, f"{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(os.path.join(POSTS_DIR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        parts = [title, "", intro, ""]
        for b in blocks:
            parts += [b["heading"], b["paragraph"],
                      f"출처: {b['source']['title']}\n{b['source']['link']}", ""]
        parts += [tips, "", outro]
        f.write("\n".join(parts))

    history.append(subtitle)
    save_history(history)
    log(f"글 생성 완료: {title}  (뉴스 {len(blocks)}블록)")
    return data



def _llm_client(cfg):
    """학교 AI 게이트웨이 → (실패 시) Anthropic 키. shared/llm.py 참고."""
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared.llm import client
    return client(cfg)


if __name__ == "__main__":
    d = generate()
    print("\n제목:", d["title"])
    print("인사:", d["intro"][:60], "...")
    for b in d["news_blocks"]:
        print(f"\n[{b['index']}] {b['heading']}")
        print("  ", b["paragraph"][:50], "...")
        print("   출처:", b["source"]["link"][:60])
