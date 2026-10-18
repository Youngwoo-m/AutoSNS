"""유튜브 영상의 정보와 한국어 자막(수동 자막 우선, 없으면 자동 자막)을 글자로 뽑는다 — 영상은 내려받지 않는다.
클로드 자동 작업(safekorea 12시 영상 소개 글 등)이 '영상에서 확인한 내용만' 쓰도록 근거를 주는 도구.

    ./.venv/bin/python yt_transcript.py https://www.youtube.com/watch?v=ID [--out 자막.txt]

결과는 마지막 줄에 JSON 한 줄:
  {"status": "ok"|"no_subs"|"error", "id", "title", "channel", "upload_date", "duration",
   "embeddable", "availability", "subs": "ko(자동)" 등, "chars", "out", "message"}
자막 본문은 --out 파일에 쓴다(없으면 표준오류에 앞부분만 보인다). 자동 자막은 음성 인식이라 고유명사·숫자가 틀릴 수 있다.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

YTDLP = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "yt-dlp")


def out(status, **kw):
    print(json.dumps({"status": status, **kw}, ensure_ascii=False))
    return 0 if status == "ok" else 1


def vtt_text(path):
    """VTT → 겹친 줄을 걷어 낸 평문(자동 자막은 같은 문장이 여러 번 되풀이된다)."""
    lines, last = [], ""
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if not ln or ln.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or "-->" in ln or ln.isdigit():
            continue
        ln = re.sub(r"<[^>]+>", "", ln).strip()
        if ln and ln != last:
            lines.append(ln)
            last = ln
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    r = subprocess.run([YTDLP, "-J", "--skip-download", a.url], capture_output=True, text=True)
    if r.returncode != 0:
        return out("error", message=(r.stderr.strip().splitlines() or ["yt-dlp 실패"])[-1][:300])
    j = json.loads(r.stdout)
    info = {"id": j.get("id"), "title": j.get("title"), "channel": j.get("channel"),
            "channel_url": j.get("channel_url"), "upload_date": j.get("upload_date"),
            "duration": j.get("duration"), "embeddable": j.get("playable_in_embed"),
            "availability": j.get("availability"),
            "description": (j.get("description") or "")[:500]}
    manual = [k for k in (j.get("subtitles") or {}) if k.startswith("ko")]
    auto = [k for k in (j.get("automatic_captions") or {}) if k == "ko" or k.startswith("ko-")]
    if not manual and not auto:
        return out("no_subs", message="한국어 자막이 없습니다 — 내용 확인 불가", **info)
    kind, langs = ("수동", manual) if manual else ("자동", auto)
    with tempfile.TemporaryDirectory() as td:
        cmd = [YTDLP, "--skip-download", "--sub-format", "vtt", "--sub-langs", langs[0],
               "-o", os.path.join(td, "s.%(ext)s"), a.url]
        cmd.insert(1, "--write-subs" if manual else "--write-auto-subs")
        s = subprocess.run(cmd, capture_output=True, text=True)
        files = [f for f in os.listdir(td) if f.endswith(".vtt")]
        if s.returncode != 0 or not files:
            return out("error", message=f"자막 내려받기 실패: {(s.stderr.strip().splitlines() or [''])[-1][:200]}", **info)
        text = vtt_text(os.path.join(td, files[0]))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        print(text[:1500], file=sys.stderr)
    return out("ok", subs=f"{langs[0]}({kind})", chars=len(text), out=a.out, **info)


if __name__ == "__main__":
    sys.exit(main())
