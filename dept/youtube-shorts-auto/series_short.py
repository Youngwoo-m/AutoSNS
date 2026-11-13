"""학과 Blogger 시리즈(진로·자격증·입시) 한 편을 20초 숏츠로 만들어 학과 유튜브에 올린다.

2026-11-11 사용자 지정: 새로 넣은 시리즈 편(입시 14~17·자격증 19~23·진로 9~13)은 블로그에 올라갈 때
숏츠로도 함께 발행한다. career_series.py 가 Blogger 발행 직후 이 스크립트를 부른다.

만드는 순서(AutoSNS CLAUDE.md 영상 지침):
  1. 대본 — 블로그 본문에서 3장면(질문 → 핵심 → 블로그 안내), 공백 제외 60~85자. 글에 없는 사실·수치는 넣지 않는다.
  2. 윤문 — shared.humanize.polish_script 로 내레이션만 한 번 더(숫자 읽기는 tts_text 로 다시 맞춘다).
  3. 디오라마 2장(1·3장면, diorama_image.py, 장당 약 39 크레딧) + 2장면은 블로그 3줄 요약 카드(Pillow).
  4. 음성 — shorts_voice.py edge(장면별), 5. Remotion survey-short 렌더(20.0초 이하·1080×1920).
  6. 업로드 — publish_schedule.json 에 편을 넣고 publish_career.py --only 로 유튜브(+틱톡 대기열·재생목록·첫 댓글).
     인스타·쓰레드는 올리지 않는다(블로그 시리즈가 매일이라 부가 채널은 넘친다).

  python series_short.py ep.json            # 만들고 올린다
  python series_short.py ep.json --no-upload # 만들기만(시험)
ep.json: {"series": "admission", "label": "입시", "n": 14, "total": 17, "title": "...",
          "summary": ["..."], "paras": ["..."], "blog_url": "https://..."}
결과는 마지막 줄 JSON: {"status", "video", "seconds", "youtube", "message"}
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys

from common import BASE_DIR, load_config, log

ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
PY = sys.executable
RENDER = os.path.join(ROOT, "common", "remotion-shorts", "render_survey_short.py")
SCHED = os.path.join(BASE_DIR, "publish_schedule.json")
DISCLOSURE = "AI 생성 그림 · AI 합성 음성(TTS)"

PROMPT = """세명대학교 재난안전학과 유튜브 숏츠(20초 이하) 대본을 쓴다. 아래 블로그 글 한 편을 요약해 소개하는 영상이다.

시리즈: {label} {n}/{total}
글 제목: {title}
글 요약: {summary}
글 본문:
{body}

규칙
- 장면 3개. 1장면 질문(시청자가 궁금해할 한 문장), 2장면 핵심(글의 핵심 한두 문장), 3장면 마무리(한 문장 + "자세한 내용은 학과 블로그에서 확인하세요" 취지).
- narration 세 개를 합쳐 공백 제외 60~85자. 문장은 짧게. 친근한 존댓말.
- 글에 없는 사실·수치·기관명을 새로 넣지 않는다. 날짜·숫자는 꼭 필요할 때만, 글에 있는 그대로.
- narration 은 화면 자막으로도 그대로 쓰인다. tts_text 는 narration 을 소리 내어 읽을 때의 표기(숫자·기호를 한글 읽기로, 예: "2027. 1. 4." → "이천이십칠년 일월 사일"). 숫자가 없으면 narration 과 같게.
- title 은 장면 위 큰 글자(12자 안팎, 줄바꿈은 \\n 한 번까지).
- diorama: 1·3장면에 그릴 아이소메트릭 미니어처 디오라마 장면을 영어로 한 문장(글자·간판·숫자 없는 장면, 사고 순간·부상자 없이 대비·공부·대응 장면). 2장면은 "".
- camera: 1장면 "establishing", 3장면 "tiltshift".
- yt_title: 질문형 유튜브 제목 40자 이내(끝에 붙일 시리즈 표기·#Shorts 는 빼고).
- hook: 설명란 첫 줄 한 문장. hashtags: 한국어 해시태그 5개(# 없이).

JSON 하나만 출력:
{{"scenes": [{{"title": "", "narration": "", "tts_text": "", "diorama": "", "camera": ""}}, ...],
 "yt_title": "", "hook": "", "hashtags": []}}"""


def out(status, **kw):
    print(json.dumps({"status": status, **kw}, ensure_ascii=False))
    return 0 if status == "ok" else 1


def _llm(prompt, cfg):
    from shared.llm import client
    r = client(cfg).messages.create(model=cfg.get("model", "claude-sonnet-4-6"), max_tokens=2000,
                                    messages=[{"role": "user", "content": prompt}])
    t = r.content[0].text
    m = re.search(r"\{.*\}", t, re.S)
    return json.loads(m.group(0))


def _chars(scenes):
    return sum(len(re.sub(r"\s", "", s["narration"])) for s in scenes)


def write_script(ep, cfg, tries=2):
    body = "\n".join(ep.get("paras") or [])[:3500]
    prompt = PROMPT.format(label=ep["label"], n=ep["n"], total=ep["total"], title=ep["title"],
                           summary=" / ".join(ep.get("summary") or []), body=body)
    for i in range(tries):
        s = _llm(prompt, cfg)
        if len(s.get("scenes") or []) == 3 and 50 <= _chars(s["scenes"]) <= 95:
            return s
        log(f"숏츠 대본 형식·길이 미달({_chars(s.get('scenes') or [])}자) — 다시 씀")
        prompt += "\n\n(앞 시도는 길이나 장면 수가 맞지 않았다. 장면 3개, 공백 제외 60~85자를 꼭 지킨다.)"
    raise RuntimeError("숏츠 대본을 규칙에 맞게 쓰지 못했습니다")


def polish(script, cfg):
    """2026-11-09 사용자 지정: 제작 대본도 한 번 더 윤문. 실패하면 원래 대본."""
    try:
        from shared.humanize import polish_script
        before = [dict(s) for s in script["scenes"]]
        polish_script(script["scenes"], field="narration", tts_field="tts_text", cfg=cfg, log=log)
        if not 50 <= _chars(script["scenes"]) <= 95:
            script["scenes"] = before
    except Exception as e:  # noqa: BLE001
        log(f"숏츠 대본 윤문 건너뜀: {type(e).__name__}")
    return script


def summary_card(lines, path):
    """2장면 그림: 블로그 3줄 요약을 큰 글자로(980×900, 흰 바탕 — survey-short 'diagram' 칸)."""
    from PIL import Image, ImageDraw, ImageFont
    from shared.fonts import DISPLAY, font_path
    W, H = 980, 900
    im = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype(font_path(DISPLAY), 50)
    fh = ImageFont.truetype(font_path(DISPLAY), 40)
    d.text((60, 60), "블로그 글 핵심", font=fh, fill="#1e6fb8")
    y = 160
    for ln in lines[:3]:
        words, cur, rows = ln.split(), "", []
        for w in words:
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) > W - 170 and cur:
                rows.append(cur)
                cur = w
            else:
                cur = t
        rows.append(cur)
        d.ellipse((60, y + 18, 80, y + 38), fill="#1e6fb8")
        for r in rows[:2]:
            d.text((105, y), r, font=f, fill="#102030")
            y += 68
        y += 50
    im.save(path)
    return path


def _run_json(cmd, cwd=None, timeout=900):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=timeout)
    for ln in reversed((r.stdout or "").strip().splitlines()):
        if ln.startswith("{"):
            return json.loads(ln)
    raise RuntimeError(f"결과 JSON 없음: {(r.stderr or r.stdout).strip()[-300:]}")


PAD = 0.35        # 장면마다 음성 뒤 여유
TARGET = 19.6     # 렌더 상한 20초보다 조금 짧게


def make(ep, workdir, cfg):
    os.makedirs(workdir, exist_ok=True)
    script = polish(write_script(ep, cfg), cfg)
    json.dump(script, open(os.path.join(workdir, "script.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    def voices(rate):
        secs = []
        for i, sc in enumerate(script["scenes"], 1):
            txt = os.path.join(workdir, f"voice{i}.txt")
            open(txt, "w", encoding="utf-8").write(sc.get("tts_text") or sc["narration"])
            v = _run_json([PY, os.path.join(BASE_DIR, "shorts_voice.py"), "--backend", "edge", "--rate", rate,
                           "--text-file", txt, "--out", os.path.join(workdir, f"voice{i}.wav")],
                          cwd=BASE_DIR, timeout=180)
            if v.get("status") != "ok":
                raise RuntimeError(f"음성 {i} 실패: {v.get('message')}")
            secs.append(float(v["seconds"]))
        return secs

    # 렌더는 20초를 넘으면 거부한다(배속 금지). 2026-11-13 입시 15편이 21.7초로 실패했다 —
    # 넘으면 말 속도를 필요한 만큼만 올려(+10% 기본, 최대 +30%) 음성을 다시 만든다.
    rate, secs = "+10%", None
    secs = voices(rate)
    total = sum(s + PAD for s in secs)
    if total > TARGET:
        need = 1.10 * sum(secs) / (TARGET - PAD * len(secs))
        pct = min(30, int(-(-(need - 1) * 100 // 1)) + 1)
        if pct > 10:
            log(f"장면 합 {total:.2f}초 > {TARGET}초 → 말 속도 +{pct}% 로 음성 다시 만듦")
            rate = f"+{pct}%"
            secs = voices(rate)
    scenes = []
    for i, sc in enumerate(script["scenes"], 1):
        wav = os.path.join(workdir, f"voice{i}.wav")
        v = {"seconds": secs[i - 1]}
        img, kind = "", "diorama"
        if sc.get("diorama"):
            png = os.path.join(workdir, f"diorama{i}.png")
            cmd = [PY, os.path.join(BASE_DIR, "diorama_image.py"), "--scene", sc["diorama"], "--out", png]
            if sc.get("camera"):
                cmd += ["--camera", sc["camera"]]
            d = _run_json(cmd, cwd=BASE_DIR, timeout=300)
            if d.get("status") != "ok":
                raise RuntimeError(f"디오라마 {i} 실패: {d.get('message')}")
            img = png
        else:
            img, kind = summary_card(ep.get("summary") or [sc["narration"]],
                                     os.path.join(workdir, f"card{i}.png")), "diagram"
        scenes.append({"title": sc["title"].replace("\\n", "\n"), "caption": sc["narration"], "image": img,
                       "kind": kind, "audio": wav, "seconds": round(float(v["seconds"]) + PAD, 2)})
    props = {"exam": "세명대 재난안전학과", "field": f"{ep['label']} 시리즈 {ep['n']}/{ep['total']}",
             "source": "", "footer": "자세한 내용 → 학과 블로그(설명란 링크)", "disclosure": DISCLOSURE,
             "scenes": scenes}
    pj = os.path.join(workdir, "props.json")
    json.dump(props, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    video = os.path.join(workdir, "short.mp4")
    r = _run_json([PY, RENDER, pj, video], timeout=900)
    if r.get("status") != "ok":
        raise RuntimeError(f"렌더 실패: {r.get('message')}")
    return script, video, r


def schedule_entry(ep, script, video):
    """publish_schedule.json 에 넣을 편. 설명 끝 줄은 해시태그(publish_career 가 링크를 그 위에 끼운다)."""
    tags = [re.sub(r"^#", "", t).replace(" ", "") for t in script.get("hashtags") or []]
    tags = [t for t in dict.fromkeys(tags) if t and t not in ("재난안전학과", "세명대학교", "Shorts")][:5]
    title = f"{script['yt_title']} | 세명대 재난안전학과 {ep['label']} [{ep['n']}/{ep['total']}] #Shorts"
    desc = "\n\n".join(x for x in [
        script.get("hook", ""),
        f"▶ 블로그에서 자세히 읽기: {ep['blog_url']}" if ep.get("blog_url") else "",
        "세명대학교 재난안전학과 " + ep["label"] + " 시리즈 — " + ep["title"],
        "※ " + DISCLOSURE,
        " ".join("#" + t for t in tags + ["재난안전학과", "세명대학교", "Shorts"]),
    ] if x)
    return {"series": "blogseries", "label": f"{ep['label']} {ep['n']}", "date": dt.date.today().isoformat(),
            "video": os.path.relpath(video, BASE_DIR).replace("\\", "/"), "title": title[:100],
            "description": desc, "tags": tags + ["재난안전학과", "세명대학교", "Shorts"],
            "blog_series": ep["series"], "blog_n": ep["n"], "published": None}


def main(argv):
    if not argv or argv[0].startswith("--"):
        return out("error", message="사용법: series_short.py ep.json [--no-upload]")
    ep = json.load(open(argv[0], encoding="utf-8"))
    cfg = load_config()
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    workdir = os.path.join(BASE_DIR, "posts", f"series_{ep['series']}{ep['n']:02d}_{stamp}")
    try:
        script, video, r = make(ep, workdir, cfg)
    except Exception as e:  # noqa: BLE001
        log(f"시리즈 숏츠 제작 실패 [{ep['label']} {ep['n']}]: {type(e).__name__}: {str(e)[:200]}")
        return out("error", message=f"{type(e).__name__}: {str(e)[:300]}", workdir=workdir)
    log(f"시리즈 숏츠 제작: [{ep['label']} {ep['n']}/{ep['total']}] {r['seconds']}초 → {video}")
    if "--no-upload" in argv:
        return out("ok", video=video, seconds=r["seconds"], frames=r.get("frames"), youtube="", message="업로드 안 함(시험)")
    entry = schedule_entry(ep, script, video)
    sched = json.load(open(SCHED, encoding="utf-8"))
    if any(e.get("blog_series") == ep["series"] and e.get("blog_n") == ep["n"] for e in sched):
        return out("error", message="이미 일정에 있는 편입니다(중복 업로드 방지)", video=video)
    entry["no"] = max([e.get("no", 0) for e in sched if isinstance(e.get("no"), int)] + [0]) + 1
    sched.append(entry)
    json.dump(sched, open(SCHED, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    p = subprocess.run([PY, os.path.join(BASE_DIR, "publish_career.py"), "--only", entry["label"],
                        "--no-ig", "--no-threads"], cwd=BASE_DIR, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    sched = json.load(open(SCHED, encoding="utf-8"))
    pub = next((e.get("published") for e in sched if e.get("label") == entry["label"]
                and e.get("blog_series") == ep["series"]), None)
    if not pub:
        return out("error", video=video, message="유튜브 업로드 실패 — 일정에 남겨 두어 주간 작업이 다시 올린다: "
                   + (p.stderr or p.stdout).strip()[-200:])
    return out("ok", video=video, seconds=r["seconds"], youtube=pub.get("youtube"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
