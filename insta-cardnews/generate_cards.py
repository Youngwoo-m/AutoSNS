"""실제 뉴스(Google News RSS)를 바탕으로 인스타그램 '카드뉴스' 문구를 생성한다.

반환: dict(title, cards[list[str]], caption, hashtags[list], sources[list]) + posts/ 저장.
- cards: 카드 한 장당 텍스트 1블록. (표지 / 뉴스 3~4건 / 안전수칙 / 마무리)
  이 블록들을 '---' 로 이어 Gamma 에 넘기면 카드 경계가 그대로 유지된다.
- caption: 인스타 본문 캡션. hashtags 와 출처를 코드에서 덧붙인다.

사실성 원칙(블로그와 동일): '제공된 뉴스 목록'에 없는 구체적 사실(사망자 수, 날짜,
지명, 인용)은 절대 지어내지 않는다. 안전 수칙은 보편적 일반 정보로만 쓴다.
"""
import json
import os
from datetime import datetime

from anthropic import Anthropic

from common import POSTS_DIR, load_config, load_history, save_history, log
from fetch_news import fetch_news

SYSTEM = """너는 한국의 __DOMAIN__ 분야 SNS(인스타그램) 카드뉴스를 만드는 신뢰감 있는 에디터다.
지켜야 할 원칙:
- '제공된 뉴스 목록'에 있는 내용만 사실로 다룬다. 목록에 없는 구체적 수치, 사망/부상자
  수, 날짜, 장소, 인용문을 절대 지어내지 않는다.
- 뉴스 제목만으로 단정하기 어려운 세부는 단정하지 말고 신중하게 표현한다.
- __TIPSLABEL__ 관련 내용은 보편적으로 알려진 일반 정보만 쓰고, 목록 밖 사실을 지어내지 않는다.
- 과장/공포 조장/낚시성 표현을 쓰지 않는다. (단, 사실에 근거한 '긴박함'은 살린다)
- ★ 첫 표지 카드는 스크롤을 멈추게 하는 '후킹'이어야 한다. "이번 주 __DOMAIN__ 뉴스"
  같은 밋밋한 제목을 절대 쓰지 말고, 뉴스 목록에서 가장 충격적·긴박한 사실 한 조각을
  구체적 지명·숫자와 함께 큰 제목으로 쓴다.
  (예: __HOOKEX__)
- 카드뉴스는 짧고 강해야 한다. 카드 한 장은 제목 1줄 + 핵심 3~4줄 정도로,
  배경·영향·대응 같은 맥락을 조금 더 구체적으로 담되 장황하지 않게 한다.
- ★ 카드 렌더링(Gamma)은 내가 나눈 줄을 하나의 문장으로 합쳐 박스 너비에 맞춰 다시
  줄바꿈한다. 그래서 문장이 길면 끝의 한두 글자('다.' 등)만 다음 줄로 떨어지는 보기 싫은
  줄바꿈(위도우)이 생긴다. 이를 막으려면 '줄'이 아니라 '문장'을 짧게 써야 한다:
  · 제목(소제목)은 한글 약 14자 이내로 짧고 굵게. (이모지 포함해서 세도 넉넉히)
  · 본문은 짧은 '문장' 단위로 쓴다. 한 문장은 한글 약 22자 이내! (카드 박스 한 줄에
    들어가는 길이) 길어질 것 같으면 반드시 두 개의 짧은 문장으로 나눈다.
  · 그래야 각 문장이 박스 안에서 한 줄에 딱 들어가, 마지막에 한두 글자만 떨어지는
    어색한 줄바꿈이 생기지 않는다.
  · '집중호우·화재·기후재난' 처럼 가운뎃점으로 단어를 길게 잇지 말고 짧게 나눈다.
- 마크다운 기호(#, *, - 등)를 쓰지 않는다. 카드 본문은 순수 텍스트.
- 출력은 반드시 지정된 구분자(===) 형식만 반환한다. (JSON 아님)"""

USER_TEMPLATE = """주제: {topic}
오늘 날짜: {today}

[이번 주 실제 재난안전 뉴스 목록]
{news_block}

위 '실제 뉴스 목록'을 바탕으로 인스타그램 카드뉴스를 만들어줘. 구성:
1) 표지 카드: 가장 충격적·긴박한 사실을 지명·숫자와 함께 큰 제목으로(후킹).
   "이번 주 __DOMAIN__ 뉴스" 같은 밋밋한 제목 금지. + 핵심 한 줄
2) 뉴스 카드 3~4장: 카드마다 [이모지+짧은 소제목] 1줄 + 핵심 3~4줄.
   무슨 일인지에 더해 '왜 중요한지/어떤 영향인지/무엇을 하면 되는지'를 한두 가지
   덧붙여 조금 더 자세히. (단, 목록 밖 구체 사실 날조 금지 / 각 줄은 짧게)
3) __TIPSLABEL__ 카드 1장: __TIPSDESC__
4) 마무리 카드 1장: 짧은 당부 + "자세한 내용은 프로필/출처 참고" 류 한마디
각 카드의 첫 줄은 그 카드의 제목(소제목)으로, 짧고 굵게.

최근에 이미 만든 제목(중복 회피):
{recent}

반드시 아래 형식 그대로 응답해. 마커(===, ---) 줄은 글자 그대로 쓰고, 그 외 설명은 붙이지 마.

===제목===
대표 제목 한 줄. 맨 앞에 구체적 지명·숫자를 넣고 궁금증을 남긴다. 과장/낚시 금지.
===카드===
표지 카드 텍스트 (제목줄 + 1~2줄)
---
뉴스 카드 1 (소제목줄 + 2~3줄)
---
뉴스 카드 2
---
뉴스 카드 3
---
__TIPSLABEL__ 카드
---
마무리 카드
===캡션===
인스타 피드 본문 캡션 (2~4문장, 친근하지만 신뢰감 있게).
★ 첫 문장은 피드에서 '…더 보기' 앞에 노출되는 훅이므로, 지명·숫자가 든 가장
궁금한 한 문장으로 시작한다.
===해시태그===
(이 카드뉴스 주제의 핵심 해시태그 6~9개 — 사건·인물·분야 등 구체적으로)"""


def _news_block(news):
    if not news:
        return "(이번 주 수집된 뉴스가 없습니다. 일반적인 재난안전 안전수칙 카드뉴스로 작성하세요.)"
    lines = []
    for i, n in enumerate(news, 1):
        src = f" / {n['source']}" if n["source"] else ""
        lines.append(f"{i}. [{n['published_str']}{src}] {n['title']}")
    return "\n".join(lines)


def _between(text, start, end):
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = text.find(end, i) if end else -1
    return (text[i:j] if j >= 0 else text[i:]).strip()


def _parse(text):
    """===제목===/===카드===/===캡션===/===해시태그=== 형식을 파싱한다."""
    title = _between(text, "===제목===", "===카드===")
    cards_raw = _between(text, "===카드===", "===캡션===")
    caption = _between(text, "===캡션===", "===해시태그===")
    tags_raw = _between(text, "===해시태그===", "")

    # 카드 블록을 '---' 단독 줄 기준으로 분리
    cards, buf = [], []
    for line in cards_raw.splitlines():
        if line.strip() == "---":
            block = "\n".join(buf).strip()
            if block:
                cards.append(block)
            buf = []
        else:
            buf.append(line)
    last = "\n".join(buf).strip()
    if last:
        cards.append(last)

    tags = [t.strip().lstrip("#") for t in tags_raw.replace("\n", ",").split(",")
            if t.strip()]
    return title, cards, caption, tags


def generate():
    cfg = load_config()
    topic = cfg.get("topic", "재난안전 관련 뉴스와 안전 정보")
    history = load_history()
    recent = "\n".join(f"- {t}" for t in history[-12:]) or "- (아직 없음)"

    # 도메인/팁/훅 라벨(에디션별). 기본=재난안전. 토요일 AI판은 editions.ai 로 덮임.
    domain = cfg.get("domain", "재난안전")
    tips_label = cfg.get("tips_label", "안전수칙")
    tips_desc = cfg.get("tips_desc", "관련된 일반적인 안전 수칙/대비 요령 3가지")
    hook_ex = cfg.get("hook_example", '"인천 물류센터 화재, 사흘째" / "충남 250mm 폭우 온다"')

    def _fill(t):
        return (t.replace("__DOMAIN__", domain)
                 .replace("__TIPSLABEL__", tips_label)
                 .replace("__TIPSDESC__", tips_desc)
                 .replace("__HOOKEX__", hook_ex))

    system = _fill(SYSTEM)
    news = fetch_news()
    user_msg = _fill(USER_TEMPLATE).format(
        topic=topic,
        today=f"{datetime.now():%Y-%m-%d (%A)}",
        news_block=_news_block(news),
        recent=recent,
    )

    client = Anthropic(api_key=cfg["anthropic_api_key"])
    title, cards, caption, tags = "", [], "", []
    for attempt in range(1, 4):
        msg = client.messages.create(
            model=cfg.get("model", "claude-sonnet-4-6"),
            max_tokens=3000,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = msg.content[0].text.strip()
        title, cards, caption, tags = _parse(text)
        if title and len(cards) >= 4 and caption:
            break
        log(f"생성 형식 불완전(시도 {attempt}/3, 카드 {len(cards)}장) → 재시도")
    if not (title and len(cards) >= 3):
        raise RuntimeError("카드 생성 형식 파싱 실패(3회). 잠시 후 다시 시도하세요.")

    # 해시태그 정리: 지역 브랜딩 태그(local_tags)는 반드시 포함하고, 나머지는 주제 태그로 채워
    # 총 max_hashtags(기본 15)개로 제한한다. 태그가 너무 많으면(20+) 스팸처럼 보여 도달이 준다.
    # local_tags 는 에디션(토요일 GeoAI판 등)이 hashtags 를 덮어써도 항상 유지된다
    # → "모든 게시물에 지역 태그 항상 추가" 규칙 보장(제천·충북 등 채널 지역 브랜딩).
    local = cfg.get("local_tags", [])
    maxn = int(cfg.get("max_hashtags", 15))
    topic = [t for t in dict.fromkeys(tags + cfg.get("hashtags", [])) if t not in local]
    tags = list(dict.fromkeys(topic[:max(0, maxn - len(local))] + local))[:maxn]

    data = {
        "title": title,
        "cards": cards,
        "caption": caption,
        "hashtags": tags,
        "sources": [
            {"title": n["title"], "link": n["link"],
             "published_str": n["published_str"]}
            for n in news
        ],
    }

    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    data["stamp"] = stamp
    with open(os.path.join(POSTS_DIR, f"{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # 미리보기 텍스트
    preview = [f"# {title}", ""]
    for i, c in enumerate(cards, 1):
        preview.append(f"[카드 {i}]\n{c}\n")
    preview.append("\n[캡션]\n" + caption)
    preview.append("\n[해시태그]\n" + " ".join("#" + t for t in tags))
    with open(os.path.join(POSTS_DIR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(preview))

    history.append(title)
    save_history(history)
    log(f"카드 문구 생성 완료: {title}  (카드 {len(cards)}장, 뉴스 {len(news)}건)")
    return data


if __name__ == "__main__":
    d = generate()
    print("\n===== 제목 =====\n" + d["title"])
    for i, c in enumerate(d["cards"], 1):
        print(f"\n----- 카드 {i} -----\n{c}")
    print("\n===== 캡션 =====\n" + d["caption"])
    print("\n===== 해시태그 =====\n" + " ".join("#" + t for t in d["hashtags"]))
