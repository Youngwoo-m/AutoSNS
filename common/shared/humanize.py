"""자동 발행 글 윤문 — 생성된 글을 한 번 더 읽고 '사람이 쓴 것처럼' 문체만 다듬는다(2026-11-08 사용자 지정).

humanize_rules.HUMANIZE_KR 는 글을 쓸 때 프롬프트에 붙이는 규칙이고, 이 모듈은 다 쓴 글을 다시 보는
두 번째 단계다. 규칙은 korean-humanize 스킬의 quick-rules(S1·S2)를 자동 발행용으로 줄였다.

안전장치(문단마다 따로 검사해, 어긋난 문단만 원문으로 되돌린다):
  - 숫자·날짜·주소(URL)·큰따옴표 인용이 원문과 하나라도 다르면 되돌린다.
  - 바뀐 글자 비율이 45%를 넘으면(과윤문) 되돌린다. 길이가 원문의 65~120%를 벗어나도 되돌린다(군더더기를 걷으면 짧아진다).
  - LLM 호출이 실패하면 글 전체를 그대로 쓴다 — 윤문 때문에 발행이 멈추지 않는다.

사용:
    from shared.humanize import polish_segments, polish
    paras = polish_segments(paras, genre="블로그")
    text = polish(text)
끄기: 각 프로젝트 config.json 에 "humanize": {"enabled": false}
"""
import difflib
import re

RULES = """너는 한국어 글을 사람이 쓴 것처럼 다듬는 편집자다. 내용은 그대로 두고 문체·리듬·표현만 고친다.

반드시 지킬 것
- 숫자·날짜·단위·고유명사(기관·지명·사람·제품)·큰따옴표 인용·URL·법령은 한 글자도 바꾸지 않는다.
- 사실·주장·가능성·추정·의무의 강도를 바꾸지 않는다. 없는 사례·수치·감정·교훈을 더하지 않는다.
- 말투(합니다/해요)와 장르는 원문 그대로 둔다. 원문이 이미 자연스러운 문장은 손대지 않는다.
- 문장을 잘게 쪼개 단문만 나열하지 않는다. 길이가 다른 문장이 섞이게 하고, 필요하면 인접 문장을 잇는다.

고칠 것(같은 뜻일 때만)
- 번역투: '~에 대해'→목적격, '~에 있어서'→'~에서', '~를 가지고 있다'→'~가 있다/~하다', '~되어진다'→'~된다',
  '~에 의해'→행위자를 주어로, '~와 관련하여'→'~에', '~에서의/~으로의' 같은 이중 조사는 풀어 쓴다.
- '~를 통해'는 한 문단에 세 번 넘을 때만 일부를 줄인다. '~것이다'는 연속으로 남발할 때만 줄인다.
- 문두 접속사(또한·따라서·즉·나아가·아울러·더욱이)와 '이는·이 점에서' 같은 메타 진입을 덜어낸다.
- '결론적으로·요약하면·이를 통해' 같은 결산 표현, '시사하는 바가 크다·주목할 만하다·본질적으로' 같은 빈 수사,
  '~할 때다·지금이야말로' 같은 결말 공식, 근거 없는 '획기적·강력한·압도적' 수식을 덜어낸다.
- 'A가 아니라 B' 수사적 대조와 'A인가, B인가' 공식은 한 번만 남긴다.
- '-성/-적/-화' 명사 나열과 '진행됩니다·제공됩니다·가능합니다' 피동 반복은 누가 무엇을 하는지 동사로 쓴다.
- 연결어미 뒤 쉼표('-고,' '-며,' '-지만,')는 쉼표만 뺀다.
- 따옴표 강조 남발, 괄호 영어 병기 반복(첫 등장만 남김)을 줄인다.
- (2026-11-19 사용자 지정) 꾸미는 수식어(매우·정말·다양한·효과적인·중요한·체계적인 같은 형용사·부사)는 쓰지 않는다. 수량·범위·조건처럼 뜻을 정하는 말은 남긴다.
- (2026-11-19 사용자 지정) 문맥으로 알 수 있는 주어(우리는·이것은·사용자는·이 방법은 등)는 뺀다.
- (2026-11-19 사용자 지정) 번역투는 남기지 않는다: '~하는 것이 가능하다'→'~할 수 있다', '~을 진행하다'→'~하다', '~에 위치한'→'~에 있는', '~로 인해'→'~ 때문에/~로'."""

_NUM = re.compile(r"\d[\d,.]*")
_URL = re.compile(r"https?://\S+")
_QUOTE = re.compile(r"[\"“”]([^\"“”]{2,})[\"“”]")
_TAG = re.compile(r"<[^>]+>")


def _anchors(s):
    return (sorted(_NUM.findall(s)), sorted(_URL.findall(s)), sorted(_QUOTE.findall(s)), _TAG.findall(s))


def change_rate(a, b):
    return 1.0 - difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def _ok(orig, new, max_change, length=(0.65, 1.2)):
    if not new.strip():
        return False, "빈 결과"
    if _anchors(orig) != _anchors(new):
        return False, "숫자·주소·인용·태그가 달라짐"
    if not (length[0] <= len(new) / max(1, len(orig)) <= length[1]):
        return False, f"길이 {len(new)}/{len(orig)}"
    cr = change_rate(orig, new)
    if cr > max_change:
        return False, f"변경률 {cr:.0%}"
    return True, f"변경률 {cr:.0%}"


def _enabled(cfg):
    return ((cfg or {}).get("humanize") or {}).get("enabled", True)


def _parts(text):
    return dict((int(m.group(1)), m.group(2).strip())
                for m in re.finditer(r"\[\[(\d+)\]\]\s*\n?(.*?)(?=\n?\[\[\d+\]\]|\Z)", text, flags=re.S))


def polish_segments(segments, genre="블로그", cfg=None, max_change=0.45, log=None, length=(0.65, 1.2), note=""):
    """글 조각 목록을 한 번의 호출로 윤문한다. 같은 길이의 목록을 돌려준다(어긋난 조각은 원문).
    length: 원문 대비 허용 길이 비율. 영상 대본은 시간이 정해져 있어 (0.85, 1.1) 처럼 좁게 준다.
    note: 장르별 추가 지시(예: 소리 내어 읽는 내레이션)."""
    log = log or (lambda m: None)
    segs = [s if isinstance(s, str) else "" for s in (segments or [])]
    idx = [i for i, s in enumerate(segs) if len(s.strip()) >= 20]   # 짧은 제목·라벨은 건드리지 않는다
    if not idx:
        return segs
    cfg = cfg or {}
    try:
        if not _enabled(cfg):
            return segs
        from shared.llm import client
        body = "\n\n".join(f"[[{n}]]\n{segs[i]}" for n, i in enumerate(idx, 1))
        prompt = (f"{RULES}\n\n장르: {genre}\n{note}\n\n아래 [[번호]] 조각마다 다듬은 글을 같은 [[번호]] 머리표 아래에 쓴다. "
                  f"머리표 수와 순서를 그대로 두고, 설명·인사말은 쓰지 않는다. 고칠 것이 없으면 원문을 그대로 쓴다.\n\n{body}")
        def ask(c):
            msg = c.messages.create(model=cfg.get("model", "claude-sonnet-4-6"),
                                    max_tokens=max(2000, int(len(body) * 1.5)),
                                    messages=[{"role": "user", "content": prompt}])
            return _parts(msg.content[0].text), str(getattr(msg, "model", ""))
        parts, used = ask(client(cfg, task="polish"))   # 로컬 Ollama 먼저(2026-11-13 크레딧 절약)
        if used.startswith(("ollama:", "openrouter:")) and len(parts) < len(idx):
            log(f"윤문: 로컬 모델이 머리표를 {len(parts)}/{len(idx)}개만 지킴 → 원래 창구로 다시")
            parts, used = ask(client(cfg))
    except Exception as e:  # noqa: BLE001
        log(f"윤문 건너뜀(원문 그대로): {type(e).__name__}: {str(e)[:80]}")
        return segs
    out, kept, changed = list(segs), 0, []
    for n, i in enumerate(idx, 1):
        new = parts.get(n, "")
        if not re.search(r"\d [가-힣]", segs[i]):   # 로컬 qwen 이 '12 월 29 일'처럼 숫자 뒤에 빈칸을 넣는다(2026-11-13)
            new = re.sub(r"(\d) (?=[가-힣])", r"\1", new)
        good, why = _ok(segs[i], new, max_change, length)
        if good:
            out[i] = new
            if new != segs[i]:
                changed.append(change_rate(segs[i], new))
        else:
            kept += 1
            log(f"윤문 되돌림(조각 {n}): {why}")
    if changed:
        log(f"윤문: {len(changed)}/{len(idx)}개 조각 다듬음(평균 변경률 {sum(changed) / len(changed):.0%})"
            + (f", {kept}개 원문 유지" if kept else ""))
    return out


_BLOCK = re.compile(r"(<(p|li|blockquote)\b[^>]*>)(.*?)(</\2>)", re.S | re.I)


def polish_html(html, genre="블로그", cfg=None, max_change=0.45, log=None):
    """HTML 원고의 <p>·<li>·<blockquote> 안쪽 글만 윤문한다. 제목·표·코드·그림은 건드리지 않는다.
    안쪽 태그(<a>·<strong> 등)는 그대로 남아야 하고, 달라지면 그 문단은 원문으로 둔다."""
    if not html:
        return html
    pre = [(m.start(), m.end()) for m in re.finditer(r"<(pre|code|table)\b.*?</\1>", html, re.S | re.I)]
    hits = [m for m in _BLOCK.finditer(html) if not any(a <= m.start() < b for a, b in pre)]
    if not hits:
        return html
    new = polish_segments([m.group(3) for m in hits], genre=genre, cfg=cfg, max_change=max_change, log=log)
    out, last = [], 0
    for m, inner in zip(hits, new):
        out += [html[last:m.start(3)], inner]
        last = m.end(3)
    out.append(html[last:])
    return "".join(out)


def polish(text, genre="블로그", cfg=None, max_change=0.45, log=None):
    """긴 글 하나 — 빈 줄 기준 문단으로 나눠 윤문한다."""
    paras = re.split(r"(\n\s*\n)", text or "")
    body_idx = [i for i in range(0, len(paras), 2)]
    new = polish_segments([paras[i] for i in body_idx], genre=genre, cfg=cfg, max_change=max_change, log=log)
    for i, s in zip(body_idx, new):
        paras[i] = s
    return "".join(paras)


NARR_NOTE = ("소리 내어 읽는 영상 내레이션이다. 귀로 듣기 쉽게 고치되 문장 수·순서·길이는 거의 그대로 둔다"
             "(영상 길이가 정해져 있다). 행동 수칙의 조건('~일 때만')과 단정의 강도를 바꾸지 않는다.")


def _num_map(orig, spoken):
    """narration(숫자 표기)과 tts_text(한글로 읽기)의 차이 = 숫자 읽기 치환 목록. 숫자 말고 다른 차이가 있으면 None."""
    import difflib as _d
    out = []
    for tag, i1, i2, j1, j2 in _d.SequenceMatcher(None, orig, spoken, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        a, b = orig[i1:i2], spoken[j1:j2]
        if tag != "replace" or not any(c.isdigit() for c in a):
            return None
        out.append((a, b))
    return sorted(out, key=lambda x: -len(x[0]))


def polish_script(scenes, field="narration", tts_field=None, cfg=None, log=None,
                  max_change=0.3, length=(0.85, 1.1)):
    """영상 대본 장면들의 내레이션을 윤문한다(2026-11-09 사용자 지정: 제작 대본도 한 번 더 윤문).
    tts_field(예: tts_text)가 있으면 숫자 읽기 치환을 다시 적용해 함께 맞춘다. 맞출 수 없으면 그 장면은 원문 유지."""
    origs = [s.get(field, "") or "" for s in scenes]
    new = polish_segments(origs, genre="영상 내레이션", cfg=cfg, max_change=max_change, log=log,
                          length=length, note=NARR_NOTE)
    for s, o, n in zip(scenes, origs, new):
        if n == o:
            continue
        if tts_field and s.get(tts_field):
            t = s[tts_field]
            if t == o:
                s[tts_field] = n
            else:
                m = _num_map(o, t)
                if m is None:
                    continue
                nt = n
                for a, b in m:
                    nt = nt.replace(a, b)
                if any(c.isdigit() for c in nt):
                    continue
                s[tts_field] = nt
        s[field] = n
    return scenes
