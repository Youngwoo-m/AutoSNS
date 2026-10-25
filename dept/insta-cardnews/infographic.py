"""카드뉴스 일부 카드를 인포그래픽(숫자·흐름·비교)으로 바꿀 설계를 만든다.

카드 문구가 나온 뒤 따로 부른다(이미 만든 카드에도 적용할 수 있게). Claude 가 카드별로
형태와 값을 정하고, 코드가 검증한다. 뉴스 카드가 모두 같은 틀이라 단조로웠던 것을
2~3장만 바꿔 넘기는 재미를 준다(2026-09-29).

숫자는 크게 보이는 만큼 틀리면 피해가 크다. 숫자형(stat)의 값은 출처 기사 제목에 실제로
있는 숫자와 '값으로' 같아야 한다 — 표기는 달라도 된다(4천200만 = 4,200만). 다른 형태에도
출처에 없는 숫자가 들어 있으면 그 카드는 인포그래픽으로 만들지 않는다.

data["infographics"] = {"3": {"type": "stat", ...}, ...}   (카드 번호는 1부터)
"""
import json
import re

from common import load_config, log

PROMPT = """아래 인스타그램 카드뉴스에서 인포그래픽으로 바꾸면 더 한눈에 들어오는 카드를 2~3장 골라,
형태와 값을 정해라. 표지(1번)와 마지막 카드는 고르지 않는다.

형태:
- stat: 숫자가 핵심인 카드. 큰 숫자 1~3개. value 는 짧게('6건', '4,200만 원', '4개 권역').
- flow: 실제로 순서·절차가 있는 카드만(신고→출동→대응처럼). 나열(안전수칙 목록)은 flow 가 아니다. 단계 3~5개, 각 8자 이내.
- compare: 전과 후·두 방식을 견주는 카드. 양쪽 제목 8자 이내, 요점 2~3개(각 16자 이내).

규칙:
- 카드에 이미 있는 내용만 쓴다. 새 사실·해석·수치를 더하지 않는다.
- 숫자는 아래 '출처 기사 제목'에 있는 숫자만 쓴다. 없으면 stat 로 만들지 않는다.
- 맞는 카드가 없으면 빈 목록을 돌려준다(억지로 만들지 않는다).
- 출력은 JSON 배열 하나만.

[카드]
{cards}

[출처 기사 제목]
{sources}

형식:
[{{"card": 3, "type": "stat", "items": [{{"value": "6건", "label": "추석 연휴 화재(5년간)"}}]}},
 {{"card": 4, "type": "flow", "steps": ["신고", "드론 출동", "영상 확보", "지휘 결정"]}},
 {{"card": 5, "type": "compare", "left": {{"title": "기존", "points": ["…"]}},
   "right": {{"title": "드론 선제 출동", "points": ["…"]}}}}]
"""

_UNIT = {"천": 1_000, "백": 100, "십": 10}


def to_number(s):
    """'4천200만', '4,200만 원', '4200만원', '1억 2천만' → 정수. 숫자가 없으면 None."""
    t = re.sub(r"[,\s]", "", s or "")
    if not re.search(r"\d", t):
        return None
    total, part, big = 0, 0, False
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)?(억|만|천|백|십)?", t):
        if not num and not unit:
            continue
        v = float(num) if num else 1.0
        if unit in _UNIT:
            part += v * _UNIT[unit]
        elif unit == "만":
            total += (part + (v if num else 0)) * 10_000
            part, big = 0, True
        elif unit == "억":
            total += (part + (v if num else 0)) * 100_000_000
            part, big = 0, True
        else:
            part += v
    v = round(total + part, 3)
    return (int(v) if v == int(v) else v) if (total or part) else None


def _numbers(text):
    """글 속 숫자 표현들의 값 집합(단위 앞 숫자 덩어리 단위로)."""
    vals = set()
    for m in re.finditer(r"\d[\d,.]*(?:\s*(?:억|만|천|백))*(?:\s*\d[\d,.]*(?:\s*(?:억|만|천|백))*)*", text or ""):
        v = to_number(m.group(0))
        if v is not None:
            vals.add(v)
    return vals


EMERGENCY = {119, 112, 1339, 1588}


def _grounded(spec, src_vals, card_text=""):
    """spec 에 든 숫자가 모두 근거가 있는가.

    큰 수치는 반드시 출처 제목의 숫자와 값으로 같아야 한다. 카드 원문에 있는 10 이하의
    개수('3대 안전수칙')와 긴급번호(119 등)는 사실 주장이 아니라 허용한다 — 이것까지
    막으니 안전수칙 카드가 모두 떨어졌다(9/23)."""
    body = {k: v for k, v in spec.items() if k not in ("card", "note")}
    nums = _numbers(json.dumps(body, ensure_ascii=False))
    own = _numbers(card_text)
    return all(n in src_vals or n in EMERGENCY or (n <= 10 and n in own) for n in nums)


def _valid_shape(s):
    t = s.get("type")
    if t == "stat":
        its = s.get("items") or []
        return 1 <= len(its) <= 3 and all(i.get("value") and i.get("label") for i in its)
    if t == "flow":
        st = s.get("steps") or []
        return 3 <= len(st) <= 5 and all(0 < len(x) <= 10 for x in st)
    if t == "compare":
        l, r = s.get("left") or {}, s.get("right") or {}
        return bool(l.get("title") and r.get("title") and l.get("points") and r.get("points"))
    return False


def plan(data):
    """data['infographics'] 를 채우고 돌려준다. 실패하면 빈 dict(카드는 모두 일반형)."""
    from anthropic import Anthropic
    cards = data.get("cards") or []
    if len(cards) < 4:
        return {}
    src = [s.get("title", "") for s in data.get("sources") or []]
    cfg = load_config()
    prompt = PROMPT.format(cards="\n\n".join(f"[{i + 1}]\n{c}" for i, c in enumerate(cards)),
                           sources="\n".join(f"- {t}" for t in src))
    try:
        msg = _llm_client(cfg).messages.create(
            model=cfg.get("model", "claude-sonnet-4-6"), max_tokens=1500,
            messages=[{"role": "user", "content": prompt}])
        text = msg.content[0].text
        i = text.find("[")
        # 배열 뒤에 설명을 덧붙이는 일이 있어 첫 배열만 정확히 읽는다(greedy 정규식은 깨졌다)
        specs = json.JSONDecoder().raw_decode(text[i:])[0] if i >= 0 else []
    except Exception as e:
        log(f"인포그래픽 설계 건너뜀: {type(e).__name__}: {str(e)[:80]}")
        return {}
    src_vals = _numbers(" ".join(src))
    out = {}
    for s in specs:
        n = s.get("card")
        if not isinstance(n, int) or n <= 1 or n >= len(cards) or str(n) in out:
            continue
        # 핵심 포인트 카드는 전용 틀(번호 배지 상자)이 있다. 흐름형으로 바꾸면 나열이 순서처럼
        # 재구성돼 원문에 없는 절차가 생겼다(9/26 시험).
        if re.search(r"^포인트\s*\d+\s*[.．:]", cards[n - 1], re.M):
            continue
        if not _valid_shape(s):
            log(f"인포그래픽 {n}번 카드: 형식 미달 → 일반 카드")
            continue
        if not _grounded(s, src_vals, cards[n - 1]):
            log(f"인포그래픽 {n}번 카드: 출처 제목에 없는 숫자 → 일반 카드")
            continue
        # 설명 한 줄은 모델이 쓴 것을 버리고 카드 원문 첫 문장을 그대로 쓴다 — 모델이
        # '…를 한눈에 보여주는 카드' 같은 디자인 설명을 적어 넣었다(9/23 시험).
        lines = [ln.strip() for ln in cards[n - 1].splitlines() if ln.strip()]
        s["note"] = lines[1] if len(lines) > 1 else ""
        out[str(n)] = s
    data["infographics"] = out
    log(f"인포그래픽 {len(out)}장: " + ", ".join(f"{k}번 {v['type']}" for k, v in out.items()))
    return out


def _llm_client(cfg):
    """학교 AI 게이트웨이 → (실패 시) Anthropic 키. shared/llm.py 참고."""
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared.llm import client
    return client(cfg)

