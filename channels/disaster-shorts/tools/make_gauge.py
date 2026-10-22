"""대본의 계기판 문구(scene["gauge"])로 계기판 영상을 만든다(anatomy 스킬 그림, 400×400, 8초, 30fps).

  .venv/bin/python make_gauge.py <편 폴더 이름> [장면 번호]     # 기본: gauge 가 있는 디오라마 장면 모두
결과: <편>/clips/scene<N>_gauge.mp4  — assemble.py(Remotion)가 오른쪽 위에 얹는다.
weekly.py 가 미리 만든 파일(anatomy/models/<날짜>_gauge.mp4)이 없을 때 부른다. 실패해도 제작은 계속(계기판만 빠짐).
"""
import json, os, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GAUGE_DIR = os.path.join(ROOT, "anatomy", "gauge")
DRIVE = "/Users/youngwoo/.claude/skills/anatomy/scripts/drive.mjs"
NODE = shutil.which("node") or "/usr/local/bin/node"           # launchd 는 PATH 가 짧다
FFMPEG = shutil.which("ffmpeg") or "/usr/local/bin/ffmpeg"
ENV = dict(os.environ, PATH="/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", ""))

# 계기 종류 고르기 — 앞에 있는 규칙이 먼저(예: '체온'은 온도계)
KINDS = [
    (r"진동|땅\s*울림|흔들림", "seismo"),
    (r"온도|기온|체온|한파|폭염", "thermo"),
    (r"우량|강수|빗물|비의\s*양|비\s*양", "rain"),
    (r"수위|물\s*높이|물이\s*차", "level"),
    (r"풍속|바람", "wind"),
    (r"습도|건조", "humid"),
    (r"압력|밀집|인파", "pressure"),
    (r"나침반|방향", "compass"),
]


def kind_of(text):
    t = text or ""
    if re.search(r"(늦게|나중에|\d초\s*(쯤|부터)).*(크게|강하게)", t) and re.search(r"진동|땅\s*울림", t):
        return "seismo2"                               # 처음엔 잔잔하다가 나중에 크게
    for pat, kind in KINDS:
        if re.search(pat, t):
            return kind
    return None


def render(kind, out):
    """계기판 페이지를 빌드하고 240프레임을 찍어 mp4 로."""
    r = subprocess.run([NODE, "build.mjs"], cwd=GAUGE_DIR, env=dict(ENV, GAUGE=kind), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("계기판 빌드 실패: " + (r.stderr or r.stdout)[-400:])
    page = os.path.join(GAUGE_DIR, f"gauge-{kind}.html")
    with tempfile.TemporaryDirectory(dir=GAUGE_DIR, prefix="fr-") as tmp:
        actions = [["wait", 300]]
        for f in range(240):
            actions += [["eval", f"window.__render({f / 30:.5f})"], ["shot", os.path.join(tmp, f"f{f:03d}.png"), ".iso-stage", 1]]
        ap = os.path.join(tmp, "actions.json"); json.dump(actions, open(ap, "w"))
        # 폭 600 미만이면 drive.mjs 가 모바일 모드로 페이지를 줄인다 → 1080 으로
        r = subprocess.run([NODE, DRIVE, page, "--width", "1080", "--height", "800", "--actions", ap], env=ENV, capture_output=True, text=True, timeout=900)
        if r.returncode != 0 or not os.path.exists(os.path.join(tmp, "f239.png")):
            raise RuntimeError("계기판 녹화 실패: " + (r.stderr or r.stdout)[-400:])
        subprocess.run([FFMPEG, "-v", "error", "-y", "-framerate", "30", "-i", os.path.join(tmp, "f%03d.png"),
                        "-vf", "crop=400:400:4:4,format=yuv420p", "-c:v", "libx264", "-crf", "18", "-r", "30", out], check=True, env=ENV)
    return out


def episode(ep, only=None):
    d = os.path.join(ROOT, ep)
    sc = json.load(open(os.path.join(d, "script.json"), encoding="utf-8"))
    made = []
    for s in sc["scenes"]:
        if only is not None and s["id"] != only:
            continue
        text = (s.get("gauge") or "").strip()
        if s.get("media") != "diorama" or not text:
            continue
        kind = kind_of(text)
        if not kind:
            print(f"장면 {s['id']}: 계기 종류를 모름 → 계기판 없이 ({text})")
            continue
        out = os.path.join(d, "clips", f"scene{s['id']}_gauge.mp4")
        render(kind, out)
        print(f"장면 {s['id']}: {kind} 계기판 → {out}")
        made.append(out)
    return made


if __name__ == "__main__":
    episode(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
