"""후킹(초반)·CTA(후반) 오버레이 — 완주율·구독 전환 개선용 공통 후처리.

아나운서/카드뉴스 두 파이프라인이 공유한다. config.overlays 로 켜고 끈다.
  "overlays": {
    "hook": true, "hook_seconds": 2.8, "hook_text": "지금 꼭 알아야 할 재난안전",
    "cta": true,  "cta_seconds": 3.2,
    "cta_text": "구독과 좋아요는 큰 힘이 됩니다!",
    "cta_sub": "세명대학교 재난안전학과 · 채널 구독하고 안전정보 받기"
  }
주의: KoPub 폰트에 이모지 글리프가 없어 이모지는 쓰지 않는다(두부문자 방지).
"""
import os
import sys
import subprocess

import imageio_ffmpeg

from common import BASE_DIR, POSTS_DIR, load_config, log

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.fonts import DOTUM_BOLD, default_font_dir, require_fonts  # noqa: E402

DEFAULTS = {
    "hook": True,
    "hook_seconds": 2.8,
    "hook_text": "지금 꼭 알아야 할 재난안전",
    "cta": True,
    "cta_seconds": 3.2,
    "cta_text": "구독과 좋아요는 큰 힘이 됩니다!",
    "cta_sub": "세명대학교 재난안전학과 · 구독하고 안전정보 받기",
}


def _font():
    import shutil
    f = os.path.join(POSTS_DIR, "_kopub_bold.otf")
    if not os.path.exists(f):
        d = require_fonts(default_font_dir(BASE_DIR), (DOTUM_BOLD,))
        shutil.copy(os.path.join(d, DOTUM_BOLD), f)
    return f


def _esc(t):
    return (t or "").replace("[", "").replace("]", "").replace("\\", "") \
        .replace(":", "\\:").replace("'", "").replace("%", "")


def _img_size(path):
    import re
    p = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", path],
                       capture_output=True, text=True)
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", p.stderr)
    return (int(m.group(1)), int(m.group(2))) if m else (1080, 1920)


def _duration(path):
    import re
    p = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", path],
                       capture_output=True, text=True)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr)
    return (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) if m else 30.0


def apply(video_in, out=None, dur=None):
    """video_in 에 후킹/CTA 오버레이를 입혀 out 으로 저장. 설정이 모두 꺼져 있으면 원본 경로 반환.

    out 을 생략하면 video_in 을 제자리 교체(임시파일 경유)한다.
    """
    cfg = dict(DEFAULTS)
    cfg.update(load_config().get("overlays", {}) or {})
    if not cfg.get("hook") and not cfg.get("cta"):
        return video_in
    fnt = _font()
    vw, vh = _img_size(video_in)
    if dur is None:
        dur = _duration(video_in)
    s = vw / 720.0

    def px(v):
        return int(round(v * s))

    parts = []
    # ---- 후킹: 초반 N초, 상단 빨간 배너(제목바 아래) — "이 영상 볼 이유"를 즉시 제시 ----
    if cfg.get("hook") and cfg.get("hook_text"):
        hs = float(cfg.get("hook_seconds", 2.8))
        parts.append(
            f"drawtext=fontfile='{fnt}':text='{_esc(cfg['hook_text'])}':fontcolor=white:"
            f"fontsize={px(46)}:box=1:boxcolor=0xE63946:boxborderw={px(18)}:"
            f"x=(w-text_w)/2:y=h*0.235:enable='between(t,0,{hs:.2f})'")
    # ---- CTA: 후반 N초, 화면 중앙 상단 네이비 배너 2줄 — 구독/좋아요 유도 ----
    if cfg.get("cta") and cfg.get("cta_text"):
        cs = float(cfg.get("cta_seconds", 3.2))
        t0 = max(dur - cs, 0.0)
        parts.append(
            f"drawtext=fontfile='{fnt}':text='{_esc(cfg['cta_text'])}':fontcolor=0xFFD24A:"
            f"fontsize={px(48)}:box=1:boxcolor=0x0B1C3A@0.92:boxborderw={px(20)}:"
            f"x=(w-text_w)/2:y=h*0.40:enable='between(t,{t0:.2f},{dur:.2f})'")
        if cfg.get("cta_sub"):
            parts.append(
                f"drawtext=fontfile='{fnt}':text='{_esc(cfg['cta_sub'])}':fontcolor=white:"
                f"fontsize={px(30)}:box=1:boxcolor=0x0B1C3A@0.92:boxborderw={px(14)}:"
                f"x=(w-text_w)/2:y=h*0.40+{px(78)}:enable='between(t,{t0:.2f},{dur:.2f})'")
    if not parts:
        return video_in

    replace = out is None
    dst = (out or os.path.join(os.path.dirname(video_in),
                               "_ovl_" + os.path.basename(video_in)))
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                    "-y", "-i", video_in, "-vf", ",".join(parts),
                    "-c:a", "copy", "-c:v", "libx264", "-preset", "veryfast",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst], check=True)
    if replace:
        os.replace(dst, video_in)
        dst = video_in
    log(f"후킹·CTA 오버레이 적용: {os.path.basename(dst)}")
    return dst


if __name__ == "__main__":
    import sys
    a = sys.argv[1:]
    print(apply(a[0], a[1] if len(a) > 1 else None))
