"""Manim 숏츠 장면: SPT N값을 기준 효율 60% 로 보정 — N60 = (ER/60) × N.

Remotion 숏츠 그림 칸(980x900)용. 제목·자막은 Remotion 이 얹으므로 도식만 그린다. LaTeX 없이 Text 만.
렌더: ~/.venvs/manim/bin/manim -ql --fps 30 --disable_caching --media_dir <출력폴더>/manim spt_n60.py SptN60Box
출처: WSDOT Geotechnical Design Manual 5장(M 46-03) — 학습용 예시.
"""
from pathlib import Path

import manimpango
from manim import *

_ROOT = Path(__file__).resolve().parents[2]
FONT_FILE = next(
    p for p in (_ROOT / "assets/FONTS/Pretendard-Bold.otf",
                Path("/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"))
    if p.exists()
)
manimpango.register_font(str(FONT_FILE))
FONT = "Pretendard"
config.background_color = "#0B1220"
INK, SUB = "#F1F5F9", "#94A3B8"
BLUE, ORANGE, GREEN = "#60A5FA", "#FB923C", "#4ADE80"


def T(s, size, color=INK):
    return Text(s, font=FONT, font_size=size, color=color)


class SptN60Box(Scene):
    def __init__(self, *a, **k):
        config.pixel_width, config.pixel_height = 980, 900
        config.frame_height = 7.0
        config.frame_width = 7.0 * 980 / 900
        super().__init__(*a, **k)

    def construct(self):
        # 8.2초 = 대본 음성 4.6~12.8초 구간(장면 2). 타이밍은 음성에 맞춤.
        base = T("기준 효율 60%", 38, SUB).move_to([0, 3.0, 0])
        self.play(FadeIn(base), run_time=0.4)
        formula = T("N60 = (ER / 60%) × N", 50, INK).move_to([0, 2.0, 0])
        self.play(Write(formula), run_time=1.2)
        self.wait(0.4)                                   # 2.0s
        er = T("ER 75%", 40, ORANGE).move_to([-2.0, 0.7, 0])
        n = T("N = 12", 40, BLUE).move_to([2.0, 0.7, 0])
        self.play(FadeIn(er, shift=UP * 0.2), FadeIn(n, shift=UP * 0.2), run_time=0.6)
        self.wait(0.6)                                   # 3.2s
        step1 = T("N60 = 75 / 60 × 12", 44, INK).move_to([0, -0.5, 0])
        self.play(FadeIn(step1, shift=UP * 0.2), run_time=0.6)
        self.wait(1.5)                                   # 5.3s
        step2 = T("= 1.25 × 12", 48, INK).move_to([0, -1.5, 0])
        self.play(FadeIn(step2, shift=UP * 0.2), run_time=0.6)
        self.wait(1.5)                                   # 7.4s
        res = T("= 15", 80, GREEN).move_to([0, -2.6, 0])
        self.play(FadeIn(res, scale=1.3), run_time=0.7)
        self.wait(TOTAL - 8.1)


TOTAL = 8.2
