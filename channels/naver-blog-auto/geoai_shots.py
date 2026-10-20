"""사람이 직접 찍은 화면 캡처를 글의 '따라하기' 칸에 넣는다.

geoai_steps.py 가 그리는 것은 도식이다 — 실제 프로그램 화면이 아니다. QGIS 나 AI 도구의
진짜 화면은 사람이 띄워서 찍어야 하므로, 찍어 둔 파일을 여기에 두면 발행할 때 알아서
들어가게 한다.

두는 곳:  shots/<slug>/
  cover.png            → 단계 목록 맨 위(도식 대신 쓴다)
  01 레이어 추가.png     → 1단계 밑에 붙는다. 파일 이름의 숫자 뒤 글자가 설명이 된다.
  02.png               → 설명 없이 2단계 밑에만 붙는다

  · 번호는 따라하기 단계 순서와 맞춘다. 단계 글은 글을 만들 때 정해지므로 미리 알 수
    없다 — 순서만 맞추면 된다. 단계보다 많은 번호는 무시한다.
  · png·jpg·jpeg·webp 를 받는다. 없으면 도식이 그대로 쓰인다(있으면 더 좋은 것이지
    발행 조건이 아니다).
  · 이미 나간 글에 뒤늦게 넣으려면:  ./.venv/bin/python geoai_shots.py apply <slug>

찍을 때: 개인정보·내부자료가 화면에 나오지 않게 하고, 타사 화면을 쓸 때는 설명에
필요한 범위만 담는다.
"""
import os
import re
import sys

from common import BASE_DIR, load_config, log

SHOTS_DIR = os.path.join(BASE_DIR, "shots")
EXTS = (".png", ".jpg", ".jpeg", ".webp")


def _entries(slug):
    """shots/<slug>/ 안의 파일을 (번호, 설명, 경로) 로. cover 는 번호 0."""
    d = os.path.join(SHOTS_DIR, slug)
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d)):
        stem, ext = os.path.splitext(name)
        if ext.lower() not in EXTS or name.startswith("."):
            continue
        path = os.path.join(d, name)
        if stem.lower() in ("cover", "0", "00"):
            out.append((0, "", path))
            continue
        m = re.match(r"^(\d{1,2})\s*[._-]?\s*(.*)$", stem)
        if m:
            out.append((int(m.group(1)), m.group(2).strip(), path))
        else:                               # 번호 없이 낱말만 쓴 파일도 받는다
            out.append((None, stem.strip(), path))
    return sorted(out, key=lambda e: (e[0] is None, e[0] or 0, e[2]))


def find(slug):
    """→ {"cover": 경로|None, "steps": {번호: (설명, 경로)}, "loose": [(설명, 경로)]}

    loose 는 번호 없이 낱말만 적은 파일이다 — 단계를 낱말로 찾아 붙인다."""
    cover, steps, loose = None, {}, []
    for no, cap, path in _entries(slug):
        if no == 0:
            cover = path
        elif no is None:
            loose.append((cap, path))
        else:
            steps[no] = (cap, path)
    return {"cover": cover, "steps": steps, "loose": loose}


# ─── 낱말로 단계 찾기 ────────────────────────────────────────────────────────
# 번호만으로 붙이면 글이 다시 생성돼 단계 순서가 바뀔 때 캡처가 엉뚱한 자리에 간다
# (따라하기 단계는 발행 시점에 정해진다). 그래서 파일 이름의 낱말을 단계 글과
# 맞춰 보고, 잘 맞는 단계에 붙인다. 낱말로 못 찾으면 번호를 그대로 쓴다.
_PARTICLES = ("에서", "으로", "에게", "까지", "부터", "하기", "하는", "한다",
              "을", "를", "이", "가", "은", "는", "의", "에", "로", "와", "과", "도")


def _tokens(text):
    """낱말 토막. 조사·어미를 대충 떼어 비교가 헐렁하게 되도록 한다."""
    out = set()
    for w in re.split(r"[^0-9A-Za-z가-힣]+", (text or "")):
        if len(w) < 2:
            continue
        out.add(w.lower())
        for p in _PARTICLES:                # 조사를 뗀 형태도 후보로
            if w.endswith(p) and len(w) - len(p) >= 2:
                out.add(w[: -len(p)].lower())
    return out


def _overlap(a, b):
    """한쪽이 다른 쪽에 들어가기만 해도 맞은 것으로 센다('테이블에서' ↔ '테이블')."""
    n = 0
    for x in a:
        if any(x == y or (len(x) >= 2 and len(y) >= 2 and (x in y or y in x))
               for y in b):
            n += 1
    return n


def _score(caption, step_name, step_desc):
    cap = _tokens(caption)
    if not cap:
        return 0
    flat = lambda t: re.sub(r"\s+", "", t or "")
    s = 0
    if step_name and flat(step_name) in flat(caption):
        s += 10                              # 단계 이름이 통째로 들어 있으면 확실하다
    s += 3 * _overlap(cap, _tokens(step_name))
    s += 1 * _overlap(cap, _tokens(step_desc))
    return s


MIN_SCORE = 3          # 이름 낱말이 최소 하나는 맞아야 낱말 매칭으로 인정한다


def match_steps(slug, steps):
    """캡처를 따라하기 단계에 붙인다. → {단계번호: (설명, 경로)}

    steps: [(단계이름, 설명)] — 이번 글의 실제 따라하기 단계.
    낱말이 잘 맞는 쌍부터 차례로 자리를 잡고, 낱말로 못 찾은 파일은 번호를 쓴다."""
    got = find(slug)
    files = [(cap, path, no) for no, (cap, path) in sorted(got["steps"].items())]
    files += [(cap, path, None) for cap, path in got["loose"]]
    if not steps:
        return {no: (cap, path) for cap, path, no in files if no}

    cand = []
    for i, (cap, path, no) in enumerate(files):
        for j, (name, desc) in enumerate(steps, start=1):
            sc = _score(cap, name, desc)
            if sc >= MIN_SCORE:
                cand.append((sc, i, j))
    cand.sort(reverse=True)

    out, used_file, used_step = {}, set(), set()
    for sc, i, j in cand:                    # 점수 높은 쌍부터 자리를 잡는다
        if i in used_file or j in used_step:
            continue
        cap, path, no = files[i]
        out[j] = (cap, path)
        used_file.add(i)
        used_step.add(j)
        if no and no != j:
            log(f"캡처 '{os.path.basename(path)}' → 낱말로 {j}단계에 붙입니다"
                f"(파일 번호는 {no}).")
    for i, (cap, path, no) in enumerate(files):   # 남은 것은 번호대로
        if i in used_file or not no or no in used_step:
            continue
        out[no] = (cap, path)
        used_step.add(no)
    return out


def upload_for(slug, cfg=None, steps=None):
    """캡처를 CDN 에 올려 주소로 바꾼다. → {"cover": url, "steps": {단계번호: (설명, url)}}

    steps 를 주면 파일 이름의 낱말로 단계를 찾아 붙인다(번호는 못 찾을 때만 쓴다)."""
    got = find(slug)
    matched = match_steps(slug, steps)
    if not got["cover"] and not matched:
        return {"cover": "", "steps": {}}
    cfg = cfg or load_config()
    order = ([("cover", 0, "", got["cover"])] if got["cover"] else []) + \
            [("step", no, cap, path) for no, (cap, path) in sorted(matched.items())]
    try:
        from geoai_assets import upload
        urls = upload([p for _, _, _, p in order], f"shots/{slug}", cfg)
    except Exception as e:
        log(f"화면 캡처 업로드 건너뜀(글은 정상): {type(e).__name__}: {str(e)[:120]}")
        return {"cover": "", "steps": {}}
    if len(urls) != len(order):
        log(f"화면 캡처 {len(order)}장 중 {len(urls)}장만 올라갔습니다 — 번호가 밀릴 수 "
            f"있어 이번 글에는 캡처를 넣지 않습니다.")
        return {"cover": "", "steps": {}}
    out = {"cover": "", "steps": {}}
    for (kind, no, cap, _), url in zip(order, urls):
        if kind == "cover":
            out["cover"] = url
        else:
            out["steps"][no] = (cap, url)
    log(f"화면 캡처 {len(urls)}장 사용: {slug} "
        f"(표지 {'있음' if out['cover'] else '없음'}, 단계 {len(out['steps'])}장)")
    return out


def _cli_list():
    if not os.path.isdir(SHOTS_DIR):
        print(f"아직 없습니다: {SHOTS_DIR}\n먼저 만드세요:  mkdir -p shots/<slug>")
        return
    slugs = sorted(d for d in os.listdir(SHOTS_DIR)
                   if os.path.isdir(os.path.join(SHOTS_DIR, d)))
    if not slugs:
        print(f"{SHOTS_DIR} 에 아직 캡처 폴더가 없습니다.")
        print("주제 slug 로 폴더를 만들고 그 안에 캡처를 넣으세요. 예:")
        print("  mkdir -p shots/qgis-start")
        print("  cp ~/Desktop/캡처.png 'shots/qgis-start/01 레이어 추가.png'")
        print("slug 목록:  ./.venv/bin/python geoai_series.py --plan")
        return
    for slug in slugs:
        g = find(slug)
        nos = ", ".join(str(n) for n in sorted(g["steps"]))
        extra = f"  낱말만 {len(g['loose'])}장" if g["loose"] else ""
        print(f"{slug:24} 표지 {'O' if g['cover'] else '-'}  번호 [{nos or '없음'}]{extra}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        _cli_list()
    elif cmd == "apply" and len(sys.argv) > 2:
        from geoai_shots_apply import apply_to_published
        apply_to_published(sys.argv[2])
    else:
        print(__doc__)
        print("사용법:\n  geoai_shots.py list\n  geoai_shots.py apply <slug>")
