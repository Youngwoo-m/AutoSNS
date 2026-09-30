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

SYSTEM = """너는 한국의 __DOMAIN__ 분야 블로그를 운영하는 신뢰감 있는 작가다.
지켜야 할 원칙:
- '제공된 뉴스 목록'에 있는 내용만 사실로 다룬다. 목록에 없는 구체적 수치,
  사망/부상자 수, 날짜, 장소, 인용문을 절대 지어내지 않는다.
- 뉴스 제목만으로 단정하기 어려운 세부사항은 단정하지 말고 "~로 알려졌다",
  "자세한 내용은 원문 참고" 식으로 신중하게 표현한다.
- __TIPSLABEL__ 관련 일반 정보는 보편적으로 알려진 내용만 쓰고,
  '일반 정보'임을 자연스럽게 드러낸다.
- 과장/공포 조장/낚시성 표현을 쓰지 않는다.
- 마크다운 기호(#, *, - 등) 없이 네이버 블로그에 붙여넣을 순수 텍스트로 쓴다.
- 출력은 반드시 지정된 구분자(===) 형식만 반환한다. (JSON 아님)"""

USER_TEMPLATE = """블로그 주제: {topic}
말투: {tone}
오늘 날짜: {today}

[이번 주 실제 재난안전 뉴스 목록] (각 줄 맨 앞 번호가 '출처 번호')
{news_block}

위 '실제 뉴스 목록'으로 '__BRIEF_LABEL__' 블로그 글을 작성해줘.
(매일 다른 주제로 한 편씩 올리는 연재다. '이번 주'처럼 주간을 전제하는 표현 대신
'오늘', '최근' 같은 말을 쓴다.)
- 주요 뉴스 4~5건을 골라 각각 한 블록으로 정리(사실 위주, 목록 밖 날조 금지).
  현장 뉴스 + '정책·제도' 뉴스 + '산업·신기술' 뉴스를 가능한 한 고루 포함.
- ★ 분량(중요): 블로그 글로 읽을 만하게 충실히 쓴다.
  · 각 뉴스 블록 본문은 한글 250~350자(무슨 일인지 + 왜 중요한지 + 참고할 점).
  · 인사 단락 250자 이상, 마무리 150자 이상.
  · 전체 본문 합계가 최소 1,800자 이상이 되게 한다. 문장을 늘리려 같은 말을
    반복하지 말고, 배경·영향·대응 관점을 더해 내용을 채운다.
- 각 뉴스 블록의 첫 줄은 반드시 '@출처:<번호>' (위 목록의 정확한 번호)로 시작.
- 각 소제목 맨 앞에 어울리는 이모지 1개.
- ★ 소제목은 사람들이 검색창에 칠 법한 '질문형'으로 쓴다(답변형 검색·AI 요약에 인용되기
  쉬운 형태). 예: "제천 호우 때 대피는 어떻게 하나요?", "드론은 재난 현장에서 무엇을 하나요?"
- ★ 각 뉴스 블록에 '기관·지역·날짜·수치'가 한 문장에 담긴 문장을 최소 1개 넣는다.
  (예: "행정안전부는 2026년 9월 10일 강원 지역에 드론 22대를 투입했다.")
  생성형 AI·검색 스니펫이 인용할 수 있는 형태라 노출에 유리하다. 없는 수치는 지어내지 않는다.
- ★★ 해설(가장 중요): 각 뉴스 블록은 '요약'으로 끝내지 말고, 마지막 2~3문장을 반드시
  재난안전학과의 시각에서 쓴 해설로 채운다. 아래 중 하나 이상을 담는다.
  · 이 소식이 우리 지역(제천·충북)에 어떤 의미인지
  · 학과에서 배우는 개념·기술과 어떻게 연결되는지(예: 재해영향평가, BCP, GeoAI, 위험성 평가)
  · 독자(주민·수험생)가 실제로 참고하거나 대비할 점
  기사 문장을 바꿔 쓴 것이 아니라, 기사에 없는 '판단'이 들어가야 한다.
  해설 문장은 "~로 보입니다", "~할 필요가 있습니다"처럼 의견임이 드러나게 쓰고,
  사실과 섞이지 않게 문단 끝에 모아 둔다.
- ★ 마무리 단락에는 이번 주 소식을 관통하는 흐름을 한 문장으로 정리한다
  (단순 인사 반복 금지). 예: "이번 주는 감시 기술이 예방 단계로 옮겨간 한 주였습니다."
- 단정하기 어려운 세부는 "~로 알려졌다" 식으로 신중하게.

최근에 이미 쓴 부제(중복 회피):
{recent}

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
===인사===
짧은 인사 + 이번 주 핵심 요약 (1~2단락).
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
이번 주 내용과 관련해 사람들이 실제로 검색할 법한 질문 3개와 답을 쓴다.
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
        return "(이번 주 수집된 뉴스가 없습니다. 일반적인 재난안전 정보 글로 작성하세요.)"
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
    summary = _section(text, "===요약===", "===인사===")
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
    subtitle = intro = tips = outro = summary = faq = ""
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
        # 마무리까지 나와야 글이 끝까지 생성된 것이다(토큰 상한에 걸리면 뒤가 잘린다)
        ok_form = bool(subtitle and intro and outro) and len(blocks) >= 2
        length = _body_len(intro, blocks, tips, outro)
        # 가장 잘 나온 결과를 보관(전부 미달이면 이걸 쓴다)
        if ok_form and (best is None or length > best[-1]):
            best = (subtitle, tags, summary, intro, blocks, tips, faq, outro, length)
        if ok_form and length >= min_chars and len(blocks) >= min_blocks:
            break
        log(f"분량/형식 미달(시도 {attempt}/3: 본문 {length}자 / 기준 {min_chars}자, "
            f"블록 {len(blocks)}개 / 기준 {min_blocks}개) → 재시도")
    else:
        if best is None:
            raise RuntimeError("글 생성 형식 파싱 실패(3회). 잠시 후 다시 시도하세요.")
        (subtitle, tags, summary, intro, blocks,
         tips, faq, outro, _) = best
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
