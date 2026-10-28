"""카드 PNG → 릴 mp4 를 Remotion(remotion-shorts/src/insta-reel)으로 렌더한다.

make_reel.py 가 먼저 부르고, 실패하면 예전 ffmpeg 합성으로 돌아간다(2026-10-23).
편집(카드 등장·진행 점·끝 화면·디오라마)은 Remotion, ffmpeg 는 쓰지 않는다.

디오라마 그림(CLAUDE.md 영상 지침)은 크레딧을 쓰므로 기본은 끈다.
  reel.diorama.paths   : 이미 있는 그림 파일 경로 0~3개(크레딧 안 씀)
  reel.diorama.scenes  : 영어 장면 설명 0~3개 + reel.diorama.generate=true 일 때만 게이트웨이로 새로 만든다
그림이 하나라도 들어가면 화면 아래에 AI 생성 그림 고지가 붙는다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

from common import BASE_DIR, POSTS_DIR, load_config, log

ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
SHORTS = os.path.join(ROOT, "remotion-shorts")
sys.path.insert(0, ROOT)


def _dioramas(rcfg, work):
    d = rcfg.get("diorama") or {}
    paths = [p if os.path.isabs(p) else os.path.join(BASE_DIR, p) for p in d.get("paths") or []]
    paths = [p for p in paths if os.path.isfile(p)]
    if paths or not (d.get("generate") and d.get("scenes")):
        return paths[:3]
    gen = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "channels", "youtube-shorts-auto", "diorama_image.py")
    made = []
    for i, scene in enumerate(d["scenes"][:3], 1):
        o = os.path.join(work, f"diorama{i}.png")
        r = subprocess.run([sys.executable, gen, "--scene", scene, "--out", o], capture_output=True, text=True)
        if r.returncode == 0 and os.path.isfile(o):
            made.append(o)
        else:
            log(f"디오라마 {i}번 생성 실패 — 건너뜀: {(r.stdout or r.stderr).strip()[-120:]}")
    return made


def render_reel(data, images, audio, out, rcfg, title=None):
    """성공하면 out 경로, 실패하면 예외."""
    if not os.path.isdir(os.path.join(SHORTS, "node_modules")):
        raise RuntimeError("remotion-shorts/node_modules 가 없습니다(npm install 필요)")
    from shared.fonts import DISPLAY, font_path
    work = os.path.join(POSTS_DIR, f"reel_{data.get('stamp') or 'tmp'}")
    os.makedirs(work, exist_ok=True)
    dios = _dioramas(rcfg, work)
    with tempfile.TemporaryDirectory() as pub:
        try:
            font_dir = (load_config().get("local_render", {}) or {}).get("font_dir") or None
        except SystemExit:   # config.json 이 없는 환경(시험)
            font_dir = None
        shutil.copy(font_path(DISPLAY, font_dir), os.path.join(pub, "Pretendard-Bold.otf"))
        cards = []
        for i, p in enumerate(images, 1):
            n = f"card{i:02d}.png"
            shutil.copy(p, os.path.join(pub, n))
            cards.append(n)
        dn = []
        for i, p in enumerate(dios, 1):
            n = f"dio{i}{os.path.splitext(p)[1]}"
            shutil.copy(p, os.path.join(pub, n))
            dn.append(n)
        shutil.copy(audio, os.path.join(pub, "bgm.mp3"))
        props = {
            "title": title or data.get("title") or "이번 주 재난안전 뉴스",
            "cards": cards, "dioramas": dn, "bg": "", "audio": "bgm.mp3",
            "endText": rcfg.get("end_text", "재난안전 소식\n팔로우하고 받아보세요"),
            "account": rcfg.get("account", "@smu_ds_official"),
            "secondsPerCard": float(rcfg.get("seconds_per_card", 3.5)),
            "stats": rcfg.get("stats") or [],
            "gapSeconds": float(rcfg.get("gap_seconds", 1.2)),
        }
        pj = os.path.join(pub, "_props.json")
        json.dump(props, open(pj, "w", encoding="utf-8"), ensure_ascii=False)
        r = subprocess.run(["npx", "remotion", "render", "src/insta-reel/index.ts", "InstaReel", out,
                            f"--props={pj}", f"--public-dir={pub}", "--log=error"],
                           cwd=SHORTS, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.isfile(out):
        raise RuntimeError(f"Remotion 렌더 실패: {(r.stderr or r.stdout).strip()[-400:]}")
    return out
