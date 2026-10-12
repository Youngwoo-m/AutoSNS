"""블로그 글 → 40초 이내 뉴스브리핑 영상 대본(장면별 나레이션)을 만든다.

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

USER = """아래 블로그 글을 40초 이내 뉴스 브리핑 영상 대본으로 바꿔줘.

제목: {title}
요약:
{summary}

본문 소제목과 발췌:
{body}

요구사항
- 장면 3~4개. 각 장면은 '## 장면제목' 한 줄과 나레이션 한 단락.
- 나레이션 전체 합계 {budget}자 안팎(한국어 기준). {hard}자를 절대 넘기지 말 것.
  짧은 영상이라 곁가지를 빼고 핵심만 남긴다. 장면마다 60~80자.
- 첫 장면 첫 문장은 시청자를 붙잡는 질문이나 상황 제시로 시작한다.
- 마지막 장면은 "자세한 내용은 블로그 재난안전과 지오에이아이에서 확인하실 수 있습니다"
  처럼, 블로그에서 더 볼 수 있다는 안내로 끝낸다(영문 약어는 소리 나는 대로 쓴다).
- 장면제목은 영상 화면에 큰 글씨로 뜨는 제목이다. 3~10자의 핵심어로 쓴다.
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
유튜브 제목(40자 이내). 사람들이 검색할 말을 앞에 둔다.
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
    hard = int((cfg.get("geoai") or {}).get("video_max_chars", 290))
    msg = client.messages.create(
        model=cfg.get("model", "claude-sonnet-4-6"), max_tokens=2000, system=SYSTEM,
        messages=[{"role": "user", "content": USER.format(
            title=data.get("title", ""), summary=summary, body=_body_digest(data),
            budget=f"{max(hard - 60, 120)}~{hard - 20}", hard=hard)}],
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
    chars = sum(len(s["narration"]) for s in scenes)
    log(f"영상 대본 {len(scenes)}장면 / 나레이션 {chars}자 (상한 {hard}자 ≈ 40초)")
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
    import glob, json, os, sys
    from common import POSTS_DIR
    path = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob(os.path.join(POSTS_DIR, "*.json")))[-1]
    print(json.dumps(make_payload(json.load(open(path, encoding="utf-8"))),
                     ensure_ascii=False, indent=2))
