"""블로그 글 → 15~19초(20초 이하) 숏츠 영상 대본(장면별 나레이션)을 만든다.

2026-10-13 채널 분석: GeoAI 채널 상위 5편이 모두 8.4~9.4초에 시청자 절반을 잃었다.
영상이 32~40초로 길고 첫 장면이 길었다. 그래서 길이를 22~26초로 줄이고, 첫 문장을
짧게 묶고, 끝이 처음으로 이어지는 고리 구조로 바꿨다.
2026-11-08 재분석(숏츠 89편): 20초 이하 조회 중앙값 78회 vs 30초 이상 8회, 질문형 제목 72회 vs
설명형 9회 → 15~19초·질문형 제목으로 다시 줄였다(config geoai.video_max_chars 100 — edge TTS 가 초당 약 5.4자라 117자가 21.7초였다).

영상은 글과 같은 내용을 다뤄야 하므로, 뉴스를 다시 모으지 않고 이미 만든 글에서 뽑는다.
결과는 youtube-shorts-auto/geoai_video.py 가 그대로 받아 쓰는 payload 다.
"""
import re

from anthropic import Anthropic

from common import load_config, log

SYSTEM = """너는 짧은 뉴스 브리핑 영상의 대본을 쓰는 한국어 방송작가다.
원칙:
- 주어진 블로그 글에 있는 내용만 말한다. 글에 없는 수치·기관·날짜를 지어내지 않는다.
- 귀로 듣고 이해되는 문장으로 쓴다. 한 문장은 45자 안팎, 어려운 표현은 풀어 쓴다.
- 읽어서 그대로 음성이 되는 글이므로 괄호·따옴표·특수기호·이모지를 쓰지 않는다.
- 과장이나 공포 조장 없이 담백하게, 아나운서 말투(존댓말)로 쓴다.
- 출력은 지정된 구분자(===) 형식만 반환한다."""

USER = """아래 블로그 글을 20초 이내 숏츠 영상 대본으로 바꿔줘.

제목: {title}
요약:
{summary}

본문 소제목과 발췌:
{body}

요구사항
- 영상 전체는 15~19초다(20초를 넘기지 않는다). 질문 하나, 핵심 답 하나만 다룬다.
- 장면은 정확히 3개. 각 장면은 '## 장면제목' 한 줄, '[화면]' 한 줄, 나레이션 한 단락.
- 나레이션 분량은 문장 수로 지킨다(전체 {budget}자, 상한 {hard}자 — 넘치면 프로그램이 뒤 문장을 잘라 낸다):
  · 장면 1: 2문장 — 첫 문장은 **20자 이내의 질문**, 둘째 문장은 바로 핵심 답(결론 먼저).
  · 장면 2: 1문장 — 그 답의 이유나 예시 하나.
  · 장면 3: 2문장 — 1장면 질문을 되받는 한 줄 정리, 그리고 짧은 블로그 안내.
  · 문장은 20~28자. 한 문장에 쉼표로 두 내용을 잇지 않는다.
  · 다 쓴 뒤 문장 수(2·1·2)를 확인한다. 더 많은 장면은 문장을 지운다.
  짧은 영상이라 곁가지(예외·역사·여러 사례 나열·인사·시리즈 소개)는 빼고 핵심만 남긴다.
- 첫 문장은 시청자를 붙잡는 질문으로 시작하고 20자를 넘기지 않는다. 의외의 사실이나
  흔한 오해를 묻는 질문이 좋다(예: "비 안 온 곳 강우량, 어떻게 알까요?").
  (2026-11-08 채널 분석: 20초 이하 숏츠 조회 중앙값 78회, 30초 이상은 8회.
  첫 화면이 질문인 숏츠는 72회, 아닌 숏츠는 9회였다.)
- 장면마다 새로운 내용을 더한다. 앞 장면에서 말한 개념을 말만 바꿔 되풀이하지 않는다.
- 끝이 처음으로 이어지는 고리 구조로 쓴다: 장면 3의 첫 문장에 장면 1의 질문·핵심어를
  한 번 되받아 답한다. "이상입니다" 같은 끝맺음 표현은 쓰지 않는다.
- 장면 3의 마지막 문장은 "자세한 내용은 블로그에 있습니다"처럼 짧은 블로그 안내로 끝낸다
  (20자 이내. 영문 약어는 소리 나는 대로 쓴다).
- 장면제목은 영상 화면에 큰 글씨로 뜨는 제목이다. 3~10자의 핵심어로 쓴다.
  **단, 장면 1의 장면제목은 물음표로 끝나는 10자 이내 질문**으로 쓴다(예: "강우량, 어떻게?",
  "드론이 왜?"). 첫 화면에서 가장 큰 글씨가 질문이어야 시청자가 멈춘다.
  '도입', '마무리', '장면1' 같은 편집 용어는 절대 쓰지 않는다(그대로 화면에 박힌다).
- 장면마다 '화면 문구'를 함께 준다: 영상 화면에 큰 글씨로 띄울 짧은 말 1~3줄.
  한 줄은 18자 이내, 조사로 끝내지 말고 핵심어 위주로. 나레이션을 그대로 옮기지 않는다.
- 단, 첫 장면의 화면 문구 첫 줄은 시청자가 스크롤을 멈추게 하는 질문으로 쓰고 물음표로 끝낸다
  (예: "회의록, 아직 손으로 쓰세요?", "비 안 온 곳 강우량은?"). 영상 안에서 답하는 질문만 쓴다.

반드시 아래 형식 그대로. 마커(===, ##)는 글자 그대로. 그 외 설명 금지.

===헤드라인===
영상 화면 상단에 뜰 한 줄(18자 이내). 보는 사람이 '내 얘기네' 하고 멈출 질문형으로 쓰고 물음표로 끝낸다
(예: "회의록, 아직 손으로 쓰세요?", "엑셀 수식, 말로 시키면?"). 영상에서 답하는 질문만 — 낚시성 표현 금지.
===제목===
유튜브 제목(35자 이내). 검색할 핵심어를 맨 앞에 두고 물음표로 끝나는 질문형으로 쓴다
(예: "공간 보간, 비 안 온 곳 강우량을 어떻게 알까?", "드론 피해조사, 며칠이 몇 시간으로 줄까?").
'~하는 법', '완전 정리', '한눈에 보기' 같은 설명형 제목은 쓰지 않는다 — 이 채널에서 설명형
제목은 조회 중앙값 9~26회, 질문형은 72회였다(2026-11-08). 영상 안에서 답하는 질문만 쓴다.
===설명===
유튜브 설명 첫 문단(2~3문장). 영상에서 무엇을 다루는지.
===대본===
## 화면제목(3~10자)
[화면] 첫 줄 / 둘째 줄
나레이션
## 화면제목(3~10자)
[화면] 첫 줄 / 둘째 줄
나레이션"""


def _split(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^===\s*([^=]+?)\s*===$", line.strip())
        if m:
            cur = m.group(1).strip()
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def _lines_from(narration, limit=3, width=18):
    """화면 문구가 없을 때 나레이션에서 짧은 줄을 만든다(카드 프레임이 비지 않게)."""
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", narration.strip()):
        sent = sent.strip().rstrip(".")
        if not sent:
            continue
        out.append(sent if len(sent) <= width * 2 else sent[:width * 2].rstrip() + "…")
        if len(out) >= limit:
            break
    return out


def _body_digest(data, limit=5):
    """글에서 소제목 + 첫 문장들을 뽑아 대본 재료로 넘긴다(토큰 절약)."""
    rows = []
    for head, para in (data.get("sections") or [])[:limit]:
        rows.append(f"- {head}: {para[:220]}")
    for blk in (data.get("news_blocks") or [])[:limit]:
        rows.append(f"- {blk.get('heading','')}: {(blk.get('paragraph') or '')[:220]}")
    return "\n".join(rows)


def _script_issues(scenes):
    """이탈 요인(긴 첫 문장·반복·끊긴 고리)을 대본에서 찾아 경고만 남긴다.

    여기서 생성을 실패시키지는 않는다 — 영상 한 편을 못 올리는 손해가 더 크다."""
    out = []
    if not scenes:
        return ["장면이 없다"]
    first = re.split(r"(?<=[.!?])\s+", (scenes[0].get("narration") or "").strip())[0]
    if len(first) > 24:
        out.append(f"첫 문장이 {len(first)}자다(20자 이내 질문으로 — 첫 2초에 붙잡아야 한다)")
    if "?" not in first:
        out.append("첫 문장이 질문이 아니다(질문형 첫 화면이 조회 중앙값 8배)")

    def words(t):
        return {w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", t or "")}

    def shared(a, b):
        return {x for x in a for y in b if x.startswith(y) or y.startswith(x)}

    for i in range(len(scenes)):
        for j in range(i + 1, len(scenes)):
            a, b = words(scenes[i].get("narration")), words(scenes[j].get("narration"))
            same = shared(a, b)
            if a and b and len(same) / min(len(a), len(b)) > 0.55:
                out.append(f"{i + 1}장면과 {j + 1}장면이 같은 내용을 되풀이한다")
    head, tail = words(scenes[0].get("narration")), words(scenes[-1].get("narration"))
    if head and tail and not shared(head, tail):
        out.append("마지막 장면이 1장면의 핵심어를 되받지 않는다(고리가 끊긴다)")
    return out


def _fit_budget(scenes, hard):
    """나레이션 합계를 상한 안으로 줄인다(문장 단위로 뒤에서 덜어낸다).

    모델이 글자 수 지시를 넘기는 일이 잦은데, 길이가 곧 영상 길이이자 HeyGen 비용이다.
    마지막 장면(블로그 안내)은 남겨 둔다 — CTA 가 빠지면 영상의 목적이 사라진다."""
    total = sum(len(s["narration"]) for s in scenes)
    if total <= hard or len(scenes) < 2:
        return scenes
    keep, last = scenes[:-1], scenes[-1]
    budget = hard - len(last["narration"])
    out, used = [], 0
    for sc in keep:
        sents = re.split(r"(?<=[.!?])\s+", sc["narration"].strip())
        picked = []
        for sent in sents:
            if used + len(sent) > budget:
                break
            picked.append(sent)
            used += len(sent) + 1
        if picked:
            out.append({**sc, "narration": " ".join(picked)})
    out.append(last)
    log(f"대본이 상한을 넘겨 {total}자 → {sum(len(s['narration']) for s in out)}자로 줄였습니다")
    return out


def make_payload(data, cfg=None):
    """영상 제작 payload(headline/title/description/scenes/hashtags/sources)."""
    cfg = cfg or load_config()
    client = _llm_client(cfg)
    summary = "\n".join(f"- {s}" for s in (data.get("summary") or [])) or "- (없음)"
    hard = int((cfg.get("geoai") or {}).get("video_max_chars", 100))
    msg = client.messages.create(
        model=cfg.get("model", "claude-sonnet-4-6"), max_tokens=2000, system=SYSTEM + _humanize_rules(),
        messages=[{"role": "user", "content": USER.format(
            title=data.get("title", ""), summary=summary, body=_body_digest(data),
            budget=f"{max(hard - 35, 60)}~{hard - 10}", hard=hard)}],
    )
    S = _split(msg.content[0].text.strip())
    scenes = []
    for part in re.split(r"^##\s+", S.get("대본", ""), flags=re.M):
        part = part.strip()
        if not part:
            continue
        head, _, rest = part.partition("\n")
        lines, narration_lines = [], []
        for l in rest.splitlines():
            l = l.strip()
            if not l:
                continue
            if l.startswith("[화면]"):
                lines = [x.strip() for x in l[4:].split("/") if x.strip()][:3]
            else:
                narration_lines.append(l)
        narration = " ".join(narration_lines)
        if narration:
            scenes.append({"heading": head.strip(), "narration": narration,
                           "lines": lines or _lines_from(narration)})
    if not scenes:
        raise RuntimeError("영상 대본 장면을 파싱하지 못했습니다.")
    scenes = _fit_budget(scenes, hard)
    scenes = _polish_script(scenes, hard, cfg)
    chars = sum(len(s["narration"]) for s in scenes)
    log(f"영상 대본 {len(scenes)}장면 / 나레이션 {chars}자 (상한 {hard}자 ≈ {hard // 7}초)")
    for m in _script_issues(scenes):
        log(f"대본 경고: {m}")
    if S.get("제목") and not S["제목"].rstrip().endswith("?"):
        log(f"대본 경고: 제목이 질문형이 아니다 — {S['제목'][:40]}")
    sources = []
    for blk in (data.get("news_blocks") or []):
        src = blk.get("source") or {}
        link = (src.get("real_link") or src.get("link") or "").strip()
        if link:
            sources.append({"title": src.get("title", ""), "link": link})
    return {
        "headline": S.get("헤드라인", "")[:30] or data.get("title", "")[:30],
        "title": S.get("제목", "")[:80] or data.get("title", "")[:80],
        "description": S.get("설명", ""),
        "scenes": scenes,
        "hashtags": [t for t in (data.get("tags") or []) if t][:10],
        "sources": sources[:6],
        # 쇼츠 띠 화면의 날짜 자리에 쓸 표시 — 글 제목의 마지막 토막(예: 'GeoAI 기초 13편')
        "label": _series_label(data.get("title", "")),
    }


def _series_label(title):
    """'산사태 위험지도는 어떻게 만드나 | GeoAI 기초 13편' → 'GeoAI 기초 13편'. 토막이 없으면 ""."""
    parts = [p.strip() for p in (title or "").split(" | ") if p.strip()]
    return parts[-1][:20] if len(parts) >= 2 else ""



def _humanize_rules():
    """사람이 쓴 것처럼 — 문체 규칙(2026-11-08 사용자 지정, shared/humanize_rules.py).
    2차 윤문은 _polish_script() 가 글자 수 상한 안에서만 한다(넘으면 원문)."""
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared.humanize_rules import HUMANIZE_KR
    return HUMANIZE_KR + "\n(위 규칙 중 '문장 길이를 섞는다'는 이 대본의 글자 수 상한 안에서만 적용한다.)"


def _polish_script(scenes, hard, cfg):
    """제작 전에 나레이션을 한 번 더 윤문한다(2026-11-09 사용자 지정: "대본도 한 번 더 윤문하고 제작").
    글자 수 상한(hard)을 넘거나 첫 문장 질문(?)이 사라지면 대본 전체를 원문으로 되돌린다 — 20초를 지키기 위해."""
    try:
        _humanize_rules()  # sys.path 준비
        from shared.humanize import polish_segments
        orig = [s["narration"] for s in scenes]
        new = polish_segments(orig, genre="숏츠 나레이션(짧게 읽히는 말)", cfg=cfg, max_change=0.35, log=log)
        first_q = lambda t: bool(re.match(r"[^.!?]*\?", t or ""))
        if sum(len(x) for x in new) > hard:
            log(f"대본 윤문 되돌림: {sum(len(x) for x in new)}자 > 상한 {hard}자")
            return scenes
        if first_q(orig[0]) and not first_q(new[0]):
            log("대본 윤문 되돌림: 첫 문장 질문형이 사라짐")
            return scenes
        out = []
        for s, n in zip(scenes, new):
            if n != s["narration"]:
                s = {**s, "narration": n}
                if not s.get("lines"):
                    s["lines"] = _lines_from(n)
            out.append(s)
        return out
    except Exception as e:  # noqa: BLE001 — 윤문 실패로 제작이 멈추지 않게
        log(f"대본 윤문 건너뜀: {type(e).__name__}: {str(e)[:80]}")
        return scenes


def _llm_client(cfg):
    """학교 AI 게이트웨이 → (실패 시) Anthropic 키. shared/llm.py 참고."""
    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared.llm import client
    return client(cfg)


if __name__ == "__main__":
    import glob, json, os, sys
    from common import POSTS_DIR
    path = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob(os.path.join(POSTS_DIR, "*.json")))[-1]
    print(json.dumps(make_payload(json.load(open(path, encoding="utf-8"))),
                     ensure_ascii=False, indent=2))
