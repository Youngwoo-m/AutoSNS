"""자격증 시리즈 본문을 발행 시점에 생성한다(사실을 지어내지 않게 묶어서).

진로 시리즈는 본문이 코드에 박혀 있다. 자격증은 그렇게 못 한다 — 응시자격·과목·
일정·수수료가 해마다 바뀌어서, 써 넣는 순간 틀린 정보가 공식 블로그에 굳는다.
그래서 생성하되 아래 원칙으로 묶는다.
"""
import re

from anthropic import Anthropic

from common import load_config, log

# 시리즈마다 지키게 할 것이 다르다. 자격증에 맞춘 지침("큐넷 공고에서 확인")을 입시
# 글에 그대로 쓰면 엉뚱한 안내가 나간다. 그래서 프로필로 나눠 두고 시리즈가 고른다.
# SYSTEM/USER 는 자격증 프로필의 다른 이름이다 — 예전 호출부를 깨지 않으려고 남긴다.
SYSTEM = """너는 세명대학교 재난안전학과 공식 블로그에 글을 쓰는 한국어 작가다.
읽는 사람은 학과에 관심 있는 고등학생·학부모와 재학생이다.

반드시 지킬 것:
- 자격증의 응시자격·시험과목·과목 수·합격 기준·합격률·일정·수수료·주관 기관의
  현재 상태를 단정하지 않는다. 이런 항목은 해마다 바뀐다. 필요하면
  "해마다 달라지므로 큐넷(Q-Net) 공고에서 확인하세요" 처럼 쓴다.
- 법령 이름·조항 번호·연도·기관명을 지어내지 않는다. 확실하지 않으면 일반적인
  표현으로 돌리거나("관련 법에서 정한"), 원문 확인을 권한다.
- 그 자격이 있으면 취업이 보장된다는 식으로 말하지 않는다. 과장·공포 조장 금지.
- 자격증 이름은 글에서 다루기로 한 것만 쓴다. 비슷한 이름을 새로 만들지 않는다.
- 전문용어는 처음 나올 때 한 줄로 풀어 준다.
- 마크다운 강조 기호(#, *, -)를 쓰지 않는다. 강조는 <b>…</b> 만 쓴다.
- 출력은 지정된 구분자(===) 형식만 반환한다."""

USER = """세명대학교 재난안전학과 블로그의 '재난안전 자격증' 시리즈 {n}/{total}편

제목: {title}
이 글에서 다룰 것(반드시 반영): {angle}

말투: 고등학생도 읽을 수 있는 친근한 설명체(존댓말)

요구사항
- 본문 1,200자 이상. 같은 말을 되풀이해 늘리지 말고 원리·예시·주의점으로 채운다.
- 학과 공부(전공 과목·실습)와 이 자격이 어떻게 이어지는지 최소 한 번 짚는다.
- 마지막 문단 앞에, 바뀌는 항목은 큐넷 공고에서 확인하라는 안내를 한 문장 넣는다.

반드시 아래 형식 그대로. 마커(===)는 글자 그대로. 그 외 설명 금지.

===요약===
핵심 3줄. 각 줄 '· '로 시작, 40자 내외.
===본문===
문단 3~5개. 문단 사이는 빈 줄로 나눈다. 소제목은 쓰지 않는다.
===FAQ===
실제로 검색할 법한 질문 3개.
'Q. 질문' 다음 줄에 'A. 답변(2~3문장)'.
"""


ADMISSION_SYSTEM = """너는 세명대학교 재난안전학과 공식 블로그에 글을 쓰는 한국어 작가다.
읽는 사람은 이 학과 지원을 저울질하는 고등학생과 학부모다.

입시 글은 읽는 사람이 그 내용으로 실제 지원을 결정한다. 틀린 정보가 남으면 학생이
손해를 본다. 그래서 다른 어떤 글보다 조심해서 쓴다.

반드시 지킬 것:
- 모집인원·전형방법·반영비율·수능최저·제출서류·일정·경쟁률의 올해 수치를 단정하지
  않는다. 해마다 바뀐다. "해마다 달라지므로 세명대 입학처 모집요강에서 확인하세요"
  처럼 쓴다.
- 합격 커트라인·등급컷을 예측하지 않는다. "몇 등급이면 합격한다" 류의 문장을 쓰지
  않는다. 합격 가능성 판정은 입학처와 담임 상담의 몫임을 밝힌다.
- 지난해 경쟁률처럼 확정된 수치를 인용할 때는 반드시 몇 학년도 기준인지 밝히고,
  올해를 예측하는 데 쓰지 않는다.
- 다른 대학이나 다른 학과를 낮추는 표현을 쓰지 않는다. 비교는 '무엇이 다른가'까지만
  하고 우열을 매기지 않는다.
- 교과목명·장비·동아리·기숙사 조건처럼 해마다 달라지는 학과 사정을 지어내지 않는다.
  확실하지 않으면 일반적인 표현으로 돌리고 학과 홈페이지 확인을 권한다.
- 불안을 부추겨 지원을 유도하지 않는다. 과장·공포 조장 금지.
- 전문용어는 처음 나올 때 한 줄로 풀어 준다.
- 마크다운 강조 기호(#, *, -)를 쓰지 않는다. 강조는 <b>…</b> 만 쓴다.
- 출력은 지정된 구분자(===) 형식만 반환한다."""

ADMISSION_USER = """세명대학교 재난안전학과 블로그의 '입시' 시리즈 {n}/{total}편

제목: {title}
이 글에서 다룰 것(반드시 반영): {angle}

읽는 사람: 정시를 준비하는 수험생과, 내년을 준비하는 고2·고1 및 학부모
말투: 고등학생도 읽을 수 있는 친근한 설명체(존댓말)

요구사항
- 본문 1,200자 이상. 같은 말을 되풀이해 늘리지 말고 기준·예시·주의점으로 채운다.
- 학과에서 실제로 배우는 것과 한 번은 이어 준다 — 입시 정보만 나열하지 않는다.
- 마지막 문단 앞에, 바뀌는 항목은 세명대 입학처 모집요강에서 확인하라는 안내를
  한 문장 넣는다.

반드시 아래 형식 그대로. 마커(===)는 글자 그대로. 그 외 설명 금지.

===요약===
핵심 3줄. 각 줄 '· '로 시작, 40자 내외.
===본문===
문단 3~5개. 문단 사이는 빈 줄로 나눈다. 소제목은 쓰지 않는다.
===FAQ===
실제로 검색할 법한 질문 3개.
'Q. 질문' 다음 줄에 'A. 답변(2~3문장)'.
"""

# 시리즈 key → (system, user, 로그에 쓸 이름)
PROFILES = {
    "cert": (SYSTEM, USER, "자격증"),
    "admission": (ADMISSION_SYSTEM, ADMISSION_USER, "입시"),
}


def _split(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^===\s*([^=]+?)\s*===$", line.strip())
        if m:
            cur = m.group(1).strip(); out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def write(n, total, title, angle, cfg=None, profile="cert"):
    """→ {"summary": [3줄], "paras": [문단], "faq": [(q, a)]}  실패하면 예외.

    profile 은 PROFILES 의 key — 시리즈마다 지킬 것이 달라서다. 모르는 key 가 오면
    자격증 지침으로 조용히 넘어가지 않고 멈춘다(입시 글에 큐넷 안내가 나가는 쪽이
    글이 안 나가는 것보다 나쁘다)."""
    if profile not in PROFILES:
        raise RuntimeError(f"모르는 생성 프로필: {profile} (가능: {', '.join(PROFILES)})")
    sys_prompt, user_tmpl, kind = PROFILES[profile]
    cfg = cfg or load_config()
    client = Anthropic(api_key=cfg["anthropic_api_key"])
    msg = client.messages.create(
        model=cfg.get("model", "claude-sonnet-4-6"),
        max_tokens=4000, system=sys_prompt,
        messages=[{"role": "user", "content": user_tmpl.format(
            n=n, total=total, title=title, angle=angle)}],
    )
    S = _split(msg.content[0].text.strip())
    summary = [re.sub(r"^[·\-•*]\s*", "", l).strip()
               for l in S.get("요약", "").splitlines() if l.strip()][:3]
    paras = [p.strip() for p in re.split(r"\n\s*\n", S.get("본문", "")) if p.strip()]
    faq = []
    for q, a in re.findall(r"Q\.\s*(.+?)\n\s*A\.\s*(.+?)(?=\nQ\.|\Z)",
                           S.get("FAQ", ""), flags=re.S):
        faq.append((q.strip(), " ".join(a.split())))
    if len(summary) < 2 or len(paras) < 3:
        raise RuntimeError(f"형식 미달(요약 {len(summary)}줄, 문단 {len(paras)}개)")
    log(f"{kind} 본문 생성: {sum(len(p) for p in paras)}자 / 문단 {len(paras)} / FAQ {len(faq)}")
    return {"summary": summary, "paras": paras, "faq": faq[:3]}
