"""주제 한 줄 → 퀴즈·진로 숏폼 대본 초안 → (검토) → 렌더·예약표 등록.

퀴즈 24편은 12월 중순에 바닥나고(조용한 토요일마다 앞당겨 쓰므로), 진로 8편은 이미
끝났다. 사람이 문항을 하나하나 쓰지 않아도 되게 Claude 가 초안을 쓰되, 바로 발행하지
않고 초안 파일로 남긴다(2026-09-29 결정: '검토 후 등록'). 퀴즈 정답이 틀리면 학과
공식 채널에 틀린 안전 정보가 나가기 때문이다.

초안에는 장면별 실사 검색어(Pexels→Pixabay, 영어)도 함께 쓴다 — 사고·피해 장면이
아니라 상황만 보여주는 장면으로. 못 구한 장면은 일러스트 B롤로 채워진다.

사용:
  python script_pipeline.py quiz "지하주차장 침수 대피"       # 초안 → drafts/quiz_*.json
  python script_pipeline.py career "드론 조종 방재 전문가"     # 초안 → drafts/career_*.json
  python script_pipeline.py approve drafts/quiz_xxx.json      # 렌더 + 예약표 등록(발행은 화요일 슬롯)
"""
import datetime
import json
import os
import re
import sys

from common import BASE_DIR, load_config, log

DRAFT_DIR = os.path.join(BASE_DIR, "drafts")
QUIZ_PATH = os.path.join(BASE_DIR, "quiz_data.json")
SCHED_PATH = os.path.join(BASE_DIR, "publish_schedule.json")
BG_KEYS = ["01_hook", "02_impact", "03_biz", "04_geoai", "05_fire", "06_safety",
           "08_mgr", "09_smart"]

COMMON_RULES = """
- 실사 검색어(pexels)는 영어 2~4단어. 사고 순간·부상자·피해자·시신·구조 현장처럼
  실제 재난 피해를 보여주는 장면은 금지. 상황만 보여주는 일반 장면으로(예: 인파사고 →
  'crowd walking street', 물놀이 → 'lake swimming summer', CPR → 'cpr training mannequin').
- 특정 지역·날짜의 실제 사건을 언급하지 않는다(시간이 지나도 유효한 상식이어야 한다).
- 과장·공포 조장 금지. 확실하지 않은 수치는 쓰지 않는다.
- 출력은 JSON 하나만. 설명·마크다운 금지."""

QUIZ_PROMPT = """세명대학교 재난안전학과 유튜브·인스타 'O·X 재난안전 상식 퀴즈' 숏폼 한 편을 만든다.
주제: {topic}

반드시 행정안전부 국민재난안전포털 행동요령, 소방청, 질병관리청, 기상청 등 공식 지침으로
정답이 분명히 갈리는 문항만 만든다. 지침마다 말이 다르거나 상황에 따라 답이 바뀌는 문항은
만들지 말고 {{"error": "이유"}} 를 돌려준다.

이미 있는 문항(겹치지 않게): {existing}

JSON 형식:
{{"topic": "짧은 주제명", "answer": "O 또는 X",
  "hook": "화면 첫 줄 질문(22자 이내, ?로 끝남)",
  "statement": "O/X 를 가릴 진술 한 문장",
  "takeaway": ["정답 아래 핵심 1(14자 이내)", "핵심 2(14자 이내)"],
  "explanation": "나레이션. '정답은 오예요.' 또는 '정답은 엑스예요.'로 시작, 2~3문장, 근거와 올바른 행동",
  "source": "근거 기관·자료 이름(예: 행정안전부 국민재난안전포털 '지진 행동요령')",
  "bg_key": "{bg_keys} 중 하나",
  "pexels": ["1장면(문제) 검색어", "2장면(정답) 검색어"],
  "tags": ["해시태그 3~4개(# 없이)"],
  "season_note": "어울리는 계절(예: '여름 장마', 없으면 '연중')"}}
""" + COMMON_RULES

CAREER_PROMPT = """세명대학교 재난안전학과 유튜브·인스타 '재난안전학과 진로' 숏폼 한 편(30~40초)을 만든다.
직업·진로: {topic}

고등학생·학부모가 '이 학과를 나오면 이런 일을 한다'를 알 수 있게. 연봉·합격률처럼 해마다
바뀌거나 확인 안 된 수치는 쓰지 않는다. 자격증은 이름만 말하고 요건은 단정하지 않는다.

이미 다룬 진로(겹치지 않게): {existing}

JSON 형식:
{{"topic": "직업명", "title": "유튜브 제목 앞부분(직업명 + 하는 일 | 짧은 훅, 40자 이내)",
  "scenes": [
    {{"heading": "장면 제목(12자 이내)", "lines": ["자막 1(18자 이내)", "자막 2(18자 이내)"],
      "narration": "이 장면 나레이션 1~2문장", "pexels": "이 장면 실사 검색어"}}
    ... 4~5장면. 첫 장면은 궁금증을 여는 질문, 마지막 장면은 '세명대 재난안전학과에서 준비' 흐름
  ],
  "tags": ["해시태그 3~4개(# 없이)"]}}
""" + COMMON_RULES


def _claude(prompt):
    from anthropic import Anthropic
    cfg = load_config()
    client = Anthropic(api_key=cfg["anthropic_api_key"])
    msg = client.messages.create(model=cfg.get("model", "claude-sonnet-4-6"), max_tokens=2000,
                                 messages=[{"role": "user", "content": prompt}])
    text = msg.content[0].text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError(f"JSON 을 찾지 못함: {text[:200]}")
    return json.loads(m.group(0))


def _check_quiz(d):
    probs = []
    if d.get("answer") not in ("O", "X"):
        probs.append("answer 가 O/X 가 아님")
    if len(d.get("hook", "")) > 24:
        probs.append(f"hook 이 김({len(d['hook'])}자)")
    if len(d.get("takeaway") or []) != 2 or any(len(t) > 16 for t in d.get("takeaway") or []):
        probs.append("takeaway 는 16자 이내 2줄")
    want = "정답은 오예요" if d.get("answer") == "O" else "정답은 엑스예요"
    if not (d.get("explanation") or "").startswith(want):
        probs.append(f"explanation 이 '{want}'로 시작하지 않음")
    if d.get("bg_key") not in BG_KEYS:
        probs.append(f"bg_key 가 목록 밖({d.get('bg_key')})")
    if len(d.get("pexels") or []) != 2:
        probs.append("pexels 검색어 2개 필요")
    if not d.get("source"):
        probs.append("근거(source) 없음")
    return probs


def draft(kind, topic):
    os.makedirs(DRAFT_DIR, exist_ok=True)
    if kind == "quiz":
        existing = "; ".join(f"{q['topic']}: {q['hook']}" for q in
                             json.load(open(QUIZ_PATH, encoding="utf-8")))
        d = _claude(QUIZ_PROMPT.format(topic=topic, existing=existing, bg_keys=", ".join(BG_KEYS)))
        if d.get("error"):
            raise RuntimeError(f"문항을 만들지 않음: {d['error']}")
        problems = _check_quiz(d)
    elif kind == "career":
        sched = json.load(open(SCHED_PATH, encoding="utf-8"))
        existing = "; ".join(e["title"].split("|")[0].strip() for e in sched
                             if e.get("series") == "career")
        d = _claude(CAREER_PROMPT.format(topic=topic, existing=existing))
        sc = d.get("scenes") or []
        problems = ([] if 4 <= len(sc) <= 5 else [f"장면 수 {len(sc)}(4~5 필요)"]) + \
                   [f"{i+1}장면 검색어 없음" for i, s in enumerate(sc) if not s.get("pexels")]
    else:
        raise SystemExit("kind 는 quiz 또는 career")
    d.update({"kind": kind, "request": topic, "status": "draft",
              "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
              "problems": problems})
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "_", d.get("topic", topic))[:24]
    path = os.path.join(DRAFT_DIR, f"{kind}_{datetime.datetime.now():%m%d_%H%M}_{slug}.json")
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"초안 저장: {path}" + (f"  ⚠ 확인 필요: {'; '.join(problems)}" if problems else ""))
    return path, d


def _with_credit(desc, credit):
    """설명의 해시태그 줄 바로 앞에 출처 한 줄을 넣는다(이미 있으면 그대로)."""
    if credit in desc:
        return desc
    lines = desc.rstrip().split("\n")
    if lines and lines[-1].lstrip().startswith("#"):
        return "\n".join(lines[:-1] + [credit, "", lines[-1]])
    return desc.rstrip() + "\n\n" + credit


def _next_no(sched, series):
    """시리즈의 다음 편 번호. 예약표 편수를 세면 안 된다 — 진로 1편은 예약표에 없어
    (2~8편만 있음) 7편을 세어 8을 붙였다가, 이미 있는 진로 8편과 겹쳤다(2026-09-29).
    제목·라벨에 적힌 번호의 최댓값 다음으로 잡는다."""
    nums = []
    for e in sched:
        if e.get("series") != series:
            continue
        for text in (e.get("label", ""), e.get("title", "")):
            nums += [int(x) for x in re.findall(r"\[(\d+)(?:/\d+)?\]|(?:퀴즈|진로) (\d+)", text)
                     for x in x if x]
    return max(nums, default=0) + 1


def _next_tuesday(sched):
    last = max(datetime.date.fromisoformat(e["date"]) for e in sched)
    d = last + datetime.timedelta(days=1)
    while d.weekday() != 1:
        d += datetime.timedelta(days=1)
    return d.isoformat()


def approve(path):
    """초안을 렌더하고 예약표에 올린다. 발행은 화요일 슬롯(또는 조용한 토요일)이 한다."""
    d = json.load(open(path, encoding="utf-8"))
    if d.get("status") != "draft":
        raise SystemExit(f"이미 처리된 초안입니다({d.get('status')}).")
    sched = json.load(open(SCHED_PATH, encoding="utf-8"))
    tags = list(dict.fromkeys((d.get("tags") or []) + ["재난안전", "세명대학교", "재난안전학과", "Shorts"]))

    if d["kind"] == "quiz":
        quizzes = json.load(open(QUIZ_PATH, encoding="utf-8"))
        no = max(q["no"] for q in quizzes) + 1
        q = {k: d[k] for k in ("topic", "answer", "bg_key", "hook", "statement", "takeaway",
                               "explanation", "pexels")}
        q.update({"no": no, "source": d.get("source", "")})
        from quiz_make import render_one
        video = render_one(q)
        quizzes.append(q)
        json.dump(quizzes, open(QUIZ_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        n = _next_no(sched, "quiz")
        label = f"퀴즈 {n}"
        title = f"[재난안전 O·X] {q['hook']} | 세명대 재난안전학과 [{n}] #Shorts"
        desc = (f"{q['hook']}\n👉 {' · '.join(q['takeaway'])}\n재난안전 상식 O/X 퀴즈 [{n}]\n"
                f"근거: {q['source']}\n\n세명대학교 재난안전학과\n▶ https://www.semyung.ac.kr/smds.do"
                "\n\n" + " ".join("#" + t for t in tags))
        entry = {"no": no, "series": "quiz", "label": label}
    else:
        from pexels_broll import fetch_pair
        from render_frames import make_frames
        from tts import make_tts
        from make_video import make_video
        n = _next_no(sched, "career")
        stamp = f"CAREER{n:02d}_{datetime.datetime.now():%m%d%H%M}"
        data = {"stamp": stamp, "header_text": "세명대 재난안전학과 진로", "max_seconds": 45,
                "title": d["title"], "source_images": {}, "broll": {}, "bgm_kind": "career",
                "scenes": [{"heading": s["heading"], "lines": s["lines"], "narration": s["narration"]}
                           for s in d["scenes"]]}
        for i, s in enumerate(d["scenes"], start=1):
            try:
                a, b = fetch_pair(s["pexels"])          # b: 장면 절반에서 컷할 두 번째 클립
                data["broll"][str(i)] = a["path"]
                if b:
                    data.setdefault("broll_alt", {})[str(i)] = b["path"]
            except Exception as e:
                log(f"실사 B롤 실패({s['pexels']}) → 일러스트: {type(e).__name__}")
        make_frames(data); make_tts(data); make_video(data)
        video = data["video"]
        label = f"진로 {n}"
        title = f"{d['title']} | 세명대 재난안전학과 진로 [{n}] #Shorts"
        desc = (f"{d['scenes'][0]['narration']}\n\n세명대학교 재난안전학과 진로 시리즈\n"
                f"▶ https://www.semyung.ac.kr/smds.do\n\n" + " ".join("#" + t for t in tags))
        entry = {"no": n, "series": "career", "label": label}

    # 배경음악 출처(CC BY 4.0). 인스타 캡션도 이 설명에서 만들어지므로 여기에 넣는다.
    from make_video import bgm_track
    track = bgm_track(d["kind"], load_config().get("video", {}))
    if track:
        desc = _with_credit(desc, track["credit"])
        entry["bgm_credit"] = track["credit"]
    entry.update({"date": _next_tuesday(sched),
                  "video": os.path.relpath(video, BASE_DIR), "title": title[:100],
                  "description": desc, "tags": tags, "published": None})
    sched.append(entry)
    json.dump(sched, open(SCHED_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    d.update({"status": "approved", "video": entry["video"], "scheduled": entry["date"],
              "label": label})
    json.dump(d, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log(f"등록: [{label}] {title[:50]} → 예약 {entry['date']}, 영상 {entry['video']}")
    return entry


def _preview(d):
    if d["kind"] == "quiz":
        print(f"\n[{d['answer']}] {d['hook']}\n  진술: {d['statement']}\n  핵심: {' / '.join(d['takeaway'])}"
              f"\n  설명: {d['explanation']}\n  근거: {d.get('source')}\n  실사: {d.get('pexels')}")
    else:
        print(f"\n{d.get('title')}")
        for i, s in enumerate(d.get("scenes") or [], 1):
            print(f"  {i}. {s['heading']} | {' / '.join(s['lines'])}\n     {s['narration']}  [{s.get('pexels')}]")
    if d.get("problems"):
        print("  ⚠ 확인 필요:", "; ".join(d["problems"]))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    if sys.argv[1] == "approve":
        print(json.dumps(approve(sys.argv[2]), ensure_ascii=False, indent=1))
    else:
        p, d = draft(sys.argv[1], " ".join(sys.argv[2:]))
        _preview(d)
        print(f"\n초안: {p}\n괜찮으면: python script_pipeline.py approve {os.path.relpath(p, BASE_DIR)}")
