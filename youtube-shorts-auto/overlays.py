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
    "cta_text": "지금 구독하기",
    "cta_sub": "매주 제천·충북 재난안전 정보 · 좋아요·알림도 힘이 됩니다",
    "cta_mid": True,
    "cta_mid_text": "구독",
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


def apply(video_in, out=None, dur=None, hook_y=None, cta_y=None, cta_panel=None):
    """video_in 에 후킹/CTA 오버레이를 입혀 out 으로 저장. 설정이 모두 꺼져 있으면 원본 경로 반환.

    hook_y·cta_y 는 글자 윗변 위치(1920 높이 기준 px). 주지 않으면 예전 자리(h*0.235, h*0.37).
    띠 화면(band_layout)은 제목·장면·자막을 가리지 않는 자리를 넘긴다.
    cta_panel=(y, 높이)(1920 기준 px)를 주면 구독 유도가 뜨는 동안 그 띠를 네이비로 덮는다 —
    구독 문구가 제목 글자 위에 겹쳐 지저분해지지 않게.

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

    # 1920 기준 px → 이 영상 높이로. 없으면 예전 비율 자리.
    hy = f"{hook_y * vh / 1920:.0f}" if hook_y is not None else "h*0.235"
    cy = f"{cta_y * vh / 1920:.0f}" if cta_y is not None else "h*0.37"
    cy_box = f"{cta_y * vh / 1920:.0f}" if cta_y is not None else "ih*0.37"

    parts = []
    # ---- 후킹: 초반 N초, 상단 빨간 배너(제목바 아래) — "이 영상 볼 이유"를 즉시 제시 ----
    if cfg.get("hook") and cfg.get("hook_text"):
        hs = float(cfg.get("hook_seconds", 2.8))
        parts.append(
            f"drawtext=fontfile='{fnt}':text='{_esc(cfg['hook_text'])}':fontcolor=white:"
            f"fontsize={px(46)}:box=1:boxcolor=0xE63946:boxborderw={px(18)}:"
            f"x=(w-text_w)/2:y={hy}:enable='between(t,0,{hs:.2f})'")
    # ---- CTA: 후반 N초, 빨간 '구독' 버튼 + 깜빡이는 밑줄 + 서브. 완주 전 이탈자를 위한
    #      중반 미리보기 칩(우상단)도 함께 띄워 구독 노출 기회를 늘린다. ----
    if cfg.get("cta") and cfg.get("cta_text"):
        cs = float(cfg.get("cta_seconds", 3.2))
        t0 = max(dur - cs, 0.0)
        en = f"between(t,{t0:.2f},{dur:.2f})"
        if cta_panel:                          # (0) 제목 자리를 덮는 바탕 — 글자끼리 겹치지 않게
            py, ph = (v * vh / 1920 for v in cta_panel)
            parts.append(f"drawbox=x=0:y={py:.0f}:w=iw:h={ph:.0f}:color=0x0B1C3A:t=fill:"
                         f"enable='{en}'")
        # (1) 빨간 유튜브식 '구독' 버튼 — 크고 눈에 띄게(구독 전환 최우선)
        parts.append(
            f"drawtext=fontfile='{fnt}':text='{_esc(cfg['cta_text'])}':fontcolor=white:"
            f"fontsize={px(56)}:box=1:boxcolor=0xE60000:boxborderw={px(26)}:"
            f"x=(w-text_w)/2:y={cy}:enable='{en}'")
        # (2) 깜빡이는 노란 밑줄 — 시선 유도(0.7s 주기 점멸).
        #     drawbox 좌표식은 입력크기 변수 iw/ih 를 쓴다(w/h 는 박스 자신이라 순환참조 에러).
        parts.append(
            f"drawbox=x=iw*0.17:y={cy_box}+{px(108)}:w=iw*0.66:h={px(9)}:color=0xFFD24A:t=fill:"
            f"enable='{en}*lt(mod(t,0.7),0.35)'")
        # (3) 서브 라인(네이비) — 좋아요/알림 등 보조 유도
        if cfg.get("cta_sub"):
            parts.append(
                f"drawtext=fontfile='{fnt}':text='{_esc(cfg['cta_sub'])}':fontcolor=white:"
                f"fontsize={px(30)}:box=1:boxcolor=0x0B1C3A@0.92:boxborderw={px(14)}:"
                f"x=(w-text_w)/2:y={cy}+{px(132)}:enable='{en}'")
        # (4) 중반 미리보기 칩 — 끝까지 안 보고 이탈하는 시청자에게도 구독 노출
        if cfg.get("cta_mid", True) and dur > 12:
            m0 = dur * 0.42
            parts.append(
                f"drawtext=fontfile='{fnt}':text='{_esc(cfg.get('cta_mid_text','구독'))}':"
                f"fontcolor=white:fontsize={px(28)}:box=1:boxcolor=0xE60000:boxborderw={px(13)}:"
                f"x=w-text_w-{px(22)}:y={px(214)}:enable='between(t,{m0:.2f},{m0 + 1.6:.2f})'")
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
