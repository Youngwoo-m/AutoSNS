"""실제 뉴스(Google News RSS)를 바탕으로 유튜브 Shorts 대본을 생성한다.

반환 dict:
  title      : 유튜브 영상 제목(<=100자, 후킹 있는 한 줄)
  scenes     : [{heading, lines[list[str]], narration}]  장면(=카드) 단위
               - heading/lines: 세로 카드에 '보이는' 자막
               - narration: TTS 로 '읽어줄' 문장(자막보다 조금 더 자연스러운 구어체)
  description : 유튜브 설명란 본문
  hashtags    : 해시태그(#Shorts, #재난안전 등 포함, 코드에서 병합)
  sources     : 참고 뉴스 출처

사실성 원칙(블로그/인스타와 동일): '제공된 뉴스 목록'에 없는 구체적 사실(사망자 수,
날짜, 지명, 인용)은 절대 지어내지 않는다. 안전 수칙은 보편적 일반 정보로만 쓴다.
"""
import json
import os
import re
from datetime import datetime

from anthropic import Anthropic

from common import POSTS_DIR, load_config, load_history, save_history, log
from fetch_news import fetch_news

SYSTEM = """너는 한국의 __DOMAIN__ 분야 유튜브 Shorts(30~35초 세로 영상) 대본을 쓰는 신뢰감 있는 에디터다.
지켜야 할 원칙:
- '제공된 뉴스 목록'에 있는 내용만 사실로 다룬다. 목록에 없는 구체적 수치, 사망/부상자
  수, 날짜, 장소, 인용문을 절대 지어내지 않는다.
- 뉴스 제목만으로 단정하기 어려운 세부는 단정하지 말고 신중하게 표현한다.
- __TIPSLABEL__ 관련 내용은 보편적으로 알려진 일반 정보만 쓰고, 목록 밖 사실을 지어내지 않는다.
- 과장/공포 조장/낚시성 표현을 쓰지 않는다. (단, 사실에 근거한 '긴박함'은 살린다)
- Shorts 는 짧고 빠르다. 전체 30~35초가 목표다. 완주율이 노출을 결정하므로 극도로
  짧고 밀도 높게 쓴다. 군더더기·수식어·중복 설명을 넣지 않는다.
- ★★ 나레이션 분량 예산(반드시 지킬 것): 각 장면 나레이션은 '공백 포함 한글 40자
  이내'(딱 1문장, 약 6초). 전체 5장이면 나레이션 합계가 약 180~200자를 넘지 않게 한다.
  (한국어 TTS 는 초당 약 5~6자를 읽으므로 이 예산을 넘으면 35초를 초과한다.)
- 장면(카드)은 4~5개. 첫 장면은 강한 후킹, 중간은 뉴스/정보, 마지막은 안전수칙+마무리.
- ★ 첫 장면(후킹)은 시청자가 1~2초 안에 멈추게 만든다. 브랜드·인사·"이번 주 소식"
  같은 밋밋한 도입을 절대 쓰지 말고, 뉴스 목록에서 가장 충격적·긴박한 '사실 한 조각'
  으로 바로 시작한다. 가능하면 구체적 지명·숫자를 넣는다.
  (예: "인천 물류센터, 사흘째 불타고 있습니다" / "충남에 250mm 폭우가 옵니다")
- ★ 자막(화면에 보이는 글자)과 나레이션(TTS 가 읽는 말)을 나눠서 쓴다:
  · 자막(heading/lines): 한눈에 읽히게 아주 짧게. 소제목 1줄(한글 약 12자 이내) +
    핵심 1~3줄(각 줄 한글 약 16자 이내). 마크다운 기호(#,*,- 등) 쓰지 않는다.
  · 나레이션: 귀로 들어 자연스러운 구어체 1~3문장. 자막을 그대로 읽지 말고,
    말하듯 매끄럽게. 숫자·영문·기호는 한글로 풀어서 읽기 좋게 쓴다.
- ★ 뉴스 장면에는 [출처] 줄에 그 장면이 근거한 '뉴스 목록의 번호'를 정확히 하나 적는다.
  화면에 그 기사 사진이 함께 나가므로, 장면 내용과 번호가 반드시 일치해야 한다.
  (표지·안전수칙·마무리 장면에는 [출처] 줄을 넣지 않는다.)
- 출력은 반드시 지정된 구분자 형식만 반환한다. (JSON 아님)"""

USER_TEMPLATE = """주제: {topic}
오늘 날짜: {today}

[이번 주 실제 재난안전 뉴스 목록]
{news_block}

위 '실제 뉴스 목록'을 바탕으로 유튜브 Shorts 대본을 만들어줘. 구성:
1) 후킹 장면: 가장 충격적·긴박한 사실 한 조각으로 즉시 시작(지명·숫자 넣기).
   "이번 주 소식", 브랜드·인사 도입 금지. 시청자가 1~2초 안에 멈추게 만든다.
2) 뉴스 장면 2개: 무슨 일인지 + 왜 중요한지/무엇을 하면 되는지 (목록 밖 사실 날조 금지)
3) __TIPSLABEL__ 장면 1개: __TIPSDESC__
4) 마무리 장면 1개: 짧은 당부 + 구독/안전 실천 권유 한마디
   ※ 전체는 30~35초 분량으로 짧고 밀도 높게.

반드시 아래 형식 그대로 응답해. 마커(===, ---, [자막], [나레이션]) 줄은 글자 그대로 쓰고,
그 외 설명은 붙이지 마. 각 장면은 --- 한 줄로 구분한다.

최근에 이미 만든 제목(중복 회피):
{recent}

===제목===
유튜브 영상 제목 한 줄. 규칙: (1) 맨 앞에 구체적 지명·숫자를 넣는다
("충남 250mm 폭우", "인천 물류센터 화재"처럼). (2) 궁금증을 남기는 한 문장
("지금 각 지자체는?"). (3) 핵심 키워드를 앞쪽에 배치. (4) 과장/낚시는 금지,
사실 기반. (5) 60자 이내로 간결하게. (6) 예보·전망 위주 소식이라도 이미 확인된
피해 규모·조치 수치(사망·이재민·통제 구간·동원 장비 수 등)를 우선 앞세운다.
확인된 수치가 없으면 '무엇이 어떻게 달라지는지'를 구체적으로 쓴다.
(같은 채널에서 결과·피해 규모형 제목이 예보형보다 평균 시청률이 2배 이상 높다.)
===장면===
[자막]
표지 소제목(짧게)
핵심 한 줄
[나레이션]
표지에서 말할 구어체 문장.
---
[자막]
뉴스1 소제목
핵심 줄1
핵심 줄2
[나레이션]
뉴스1을 말하듯 설명하는 1~2문장.
[출처]1
---
[자막]
뉴스2 소제목
핵심 줄1
[나레이션]
뉴스2 나레이션.
[출처]2
---
[자막]
안전수칙
수칙1
수칙2
[나레이션]
안전수칙 나레이션.
---
[자막]
마무리
한마디
[나레이션]
마무리 나레이션 + 구독/안전 실천 권유.
===설명===
유튜브 설명란 본문(검색 최적화). 규칙: (1) 첫 문장에 이 영상의 핵심 검색어를
자연스럽게 넣는다 — 지명, 재난 유형(호우·산사태·화재·폭염 등), '재난안전'.
(2) 2~3문장으로 무슨 일인지 요약. (3) 마지막 문장에 '세명대학교 재난안전학과'를
한 번 언급. 키워드를 부자연스럽게 나열(스터핑)하지 말고 문장으로 녹인다. 과장 금지.
===해시태그===
Shorts, (이 영상 주제의 핵심 해시태그 6~9개 — 사건·인물·지명·분야 등 구체적으로)"""


def _news_block(news):
    if not news:
        return "(이번 주 수집된 뉴스가 없습니다. 일반적인 재난안전 안전수칙 Shorts 로 작성하세요.)"
    lines = []
    for i, n in enumerate(news, 1):
        src = f" / {n['source']}" if n["source"] else ""
        star = "★ " if n.get("_lead") else ""
        lines.append(f"{i}. {star}[{n['published_str']}{src}] {n['title']}")
    return "\n".join(lines)


LEAD_NOTE = """

[이번 영상은 속보 영상입니다]
★ 표시 기사가 지금 발행하게 된 사건입니다. 제목과 첫 장면은 반드시 이 사건으로 시작하고,
영상의 중심도 이 사건에 둡니다. 나머지 기사는 이 사건과 관련이 있을 때만 뒤 장면에서 짧게 곁들이고,
관련이 없으면 쓰지 않습니다."""


def _with_lead(news, lead):
    """트리거 사건 기사(lead)를 뉴스 목록 맨 앞에 ★로 올린다(같은 기사는 한 번만)."""
    if not lead:
        return news
    seen, head = set(), []
    for n in lead:
        key = n.get("link") or n.get("title")
        if key in seen:
            continue
        seen.add(key)
        head.append({**n, "_lead": True, "source": n.get("source", "")})
    rest = [n for n in news if (n.get("link") or n.get("title")) not in seen]
    return head + rest


def _between(text, start, end):
    i = text.find(start)
    if i < 0:
        return ""
    i += len(start)
    j = text.find(end, i) if end else -1
    return (text[i:j] if j >= 0 else text[i:]).strip()


def _parse_scene(block):
    """한 장면 블록에서 (heading, lines[], narration, src_idx) 추출.

    [자막] ... [나레이션] ... ([출처]N) 구조. [자막] 첫 줄이 heading, 나머지가 lines.
    src_idx: 이 장면이 근거한 뉴스 목록 번호(1-based). 없으면 None.
    """
    has_src = "[출처]" in block
    subtitle = _between(block, "[자막]", "[나레이션]")
    narration = _between(block, "[나레이션]", "[출처]" if has_src else "")
    src_raw = _between(block, "[출처]", "") if has_src else ""
    m = re.search(r"\d+", src_raw)
    src_idx = int(m.group()) if m else None

    sub_lines = [ln.strip() for ln in subtitle.splitlines() if ln.strip()]
    heading = sub_lines[0] if sub_lines else ""
    lines = sub_lines[1:]
    # 나레이션이 비면 자막을 이어붙여 대체
    if not narration:
        narration = " ".join(sub_lines)
    narration = " ".join(narration.split())  # 개행/중복공백 정리(TTS 안정)
    return {"heading": heading, "lines": lines, "narration": narration,
            "src_idx": src_idx}


def _parse(text):
    title = _between(text, "===제목===", "===장면===")
    scenes_raw = _between(text, "===장면===", "===설명===")
    description = _between(text, "===설명===", "===해시태그===")
    tags_raw = _between(text, "===해시태그===", "")

    scenes, buf = [], []
    for line in scenes_raw.splitlines():
        if line.strip() == "---":
            block = "\n".join(buf).strip()
            if block:
                scenes.append(_parse_scene(block))
            buf = []
        else:
            buf.append(line)
    last = "\n".join(buf).strip()
    if last:
        scenes.append(_parse_scene(last))
    scenes = [s for s in scenes if s["narration"]]

    # 해시태그 정규화: 쉼표·줄바꿈뿐 아니라 '#'·공백으로도 쪼갠다.
    # (LLM이 "Shorts #a #b #c" 처럼 공백으로 붙여 반환하면 한 뭉치가 하나의 태그로
    #  잘못 들어가던 버그 방지. '#Shorts #Shorts' 중복도 이후 dedup 으로 정리됨.)
    tags = [t for t in tags_raw.replace("#", " ").replace(",", " ").split() if t]
    return title, scenes, description, tags


def generate(lead=None):
    """lead: 트리거가 잡은 사건의 기사들. 주면 영상이 그 사건으로 시작한다.

    예전엔 트리거가 발행 여부만 정하고 내용은 평소 수집을 그대로 써서, 9/28 트리거가
    '양구 사방사업'으로 발동했는데 영상은 '보은 화재'를 다뤘다."""
    cfg = load_config()
    topic = cfg.get("topic", "재난안전 관련 뉴스와 안전 정보")
    history = load_history()
    recent = "\n".join(f"- {t}" for t in history[-12:]) or "- (아직 없음)"

    # 도메인/팁 라벨(에디션별). 기본=재난안전. 토요일 AI판은 config editions.ai 로 덮임.
    domain = cfg.get("domain", "재난안전")
    tips_label = cfg.get("tips_label", "안전수칙")
    tips_desc = cfg.get("tips_desc", "관련된 일반 안전 수칙 2~3가지")
    system = (SYSTEM.replace("__DOMAIN__", domain)
              .replace("__TIPSLABEL__", tips_label))

    news = _with_lead(fetch_news(), lead)
    user_msg = (USER_TEMPLATE
                .replace("__TIPSLABEL__", tips_label)
                .replace("__TIPSDESC__", tips_desc)
                .format(
                    topic=topic,
                    today=f"{datetime.now():%Y-%m-%d (%A)}",
                    news_block=_news_block(news),
                    recent=recent,
                ))
    if lead:
        user_msg += LEAD_NOTE

    client = _llm_client(cfg)
    title, scenes, description, tags = "", [], "", []
    for attempt in range(1, 4):
        msg = client.messages.create(
            model=cfg.get("model", "claude-sonnet-4-6"),
            max_tokens=3000,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = msg.content[0].text.strip()
        title, scenes, description, tags = _parse(text)
        if title and len(scenes) >= 4 and description:
            break
        log(f"대본 형식 불완전(시도 {attempt}/3, 장면 {len(scenes)}개) → 재시도")
    if not (title and len(scenes) >= 3):
        raise RuntimeError("대본 생성 형식 파싱 실패(3회). 잠시 후 다시 시도하세요.")

    # 기본 해시태그 병합(#Shorts 항상 포함) + 중복 제거 + 15개 제한
    base_tags = cfg.get("hashtags", [])
    tags = list(dict.fromkeys(["Shorts"] + tags + base_tags))[:15]

    data = {
        "news_stock": True,          # 사진 없는 장면에 주제 맞춤 실사 + '자료 화면' 표기(render_frames)
        "title": title.strip()[:100],
        "scenes": scenes,
        "description": description,
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
    preview = [f"# {data['title']}", ""]
    for i, s in enumerate(data["scenes"], 1):
        cap = " / ".join([s["heading"]] + s["lines"])
        preview.append(f"[장면 {i}] 자막: {cap}\n  나레이션: {s['narration']}\n")
    preview.append("\n[설명]\n" + description)
    preview.append("\n[해시태그]\n" + " ".join("#" + t for t in tags))
    with open(os.path.join(POSTS_DIR, f"{stamp}.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(preview))

    history.append(data["title"])
    save_history(history)
    log(f"Shorts 대본 생성 완료: {data['title']}  (장면 {len(scenes)}개, 뉴스 {len(news)}건)")
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
    print("\n===== 제목 =====\n" + d["title"])
    for i, s in enumerate(d["scenes"], 1):
        print(f"\n----- 장면 {i} -----")
        print("자막:", " / ".join([s["heading"]] + s["lines"]))
        print("나레이션:", s["narration"])
    print("\n===== 설명 =====\n" + d["description"])
    print("\n===== 해시태그 =====\n" + " ".join("#" + t for t in d["hashtags"]))
