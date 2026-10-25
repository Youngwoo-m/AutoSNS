"""Blogger 가 글을 거부했을 때(400 invalid argument) 원인을 찾을 수 있게 요청을 요약한다.

9/18·9/20 GeoAI 글이 400 으로 거부됐는데 오류 문구가 'Request contains an invalid
argument' 뿐이었고, 따로 저장해 둔 본문 파일은 나중에 지워져 원인을 못 찾았다. 그래서
로그 한 줄에 요청의 모양을 남긴다(로그는 남는다).

알려진 400 원인을 함께 점검한다:
  - 라벨 합계 길이 200자 초과, 라벨 안의 쉼표, 빈 라벨
  - 제목·본문의 제어 문자(\\x00~\\x1f, 줄바꿈·탭 제외)
  - 빈 제목/본문, 지나치게 긴 제목
"""
import re

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def describe(body):
    """요청 본문 요약 문자열(의심 항목은 ⚠ 표시)."""
    title = body.get("title") or ""
    content = body.get("content") or ""
    labels = list(body.get("labels") or [])
    lab_total = sum(len(x) for x in labels) + max(len(labels) - 1, 0)   # 쉼표로 이어 붙인 길이
    warn = []
    if not title.strip():
        warn.append("제목 비어 있음")
    if len(title) > 250:
        warn.append(f"제목 {len(title)}자")
    if not content.strip():
        warn.append("본문 비어 있음")
    if lab_total > 200:
        warn.append(f"라벨 합계 {lab_total}자>200")
    bad = [x for x in labels if not x.strip() or "," in x]
    if bad:
        warn.append(f"라벨 이상 {bad[:3]}")
    for name, text in (("제목", title), ("본문", content), ("라벨", " ".join(labels))):
        m = _CTRL.search(text)
        if m:
            warn.append(f"{name} 제어문자 U+{ord(m.group()):04X}@{m.start()}")
    loc = body.get("location") or {}
    s = (f"제목 {len(title)}자 · 본문 {len(content):,}자 · 라벨 {len(labels)}개/{lab_total}자"
         f"{' · 위치 ' + str(loc.get('name')) if loc else ''}")
    return s + (" · ⚠ " + "; ".join(warn) if warn else " · 알려진 원인 없음")
