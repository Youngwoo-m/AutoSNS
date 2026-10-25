"""Manim 샘플: 우연오차는 직각삼각형처럼 합쳐진다 (σz = √(σx²+σy²)).

렌더(세로 1080x1920, 투명 배경 없음):
  ~/.venvs/manim/bin/manim -qh --media_dir <출력폴더> remotion-shorts/manim/error_propagation.py ErrorPropagation
글꼴은 assets/FONTS/Pretendard-Bold.otf (영상 지침). LaTeX 없이 Text 만 쓴다.
"""
from pathlib import Path

import manimpango
from manim import *
import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
# 워크트리에는 assets/ 가 없을 수 있어 main 폴더도 찾는다.
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


class ErrorPropagation(Scene):
    def __init__(self, *a, **k):
        config.pixel_width, config.pixel_height = 1080, 1920
        config.frame_width, config.frame_height = 6.75, 12.0
        super().__init__(*a, **k)

    def construct(self):
        title = T("오차는 어떻게 합쳐질까?", 40)
        title.to_edge(UP, buff=0.9)
        self.play(FadeIn(title, shift=DOWN * 0.3), run_time=0.8)

        # 직각삼각형: 가로 σx=3, 세로 σy=4, 빗변 σz=5
        u = 0.75
        a = Point([-1.4, -1.2, 0])
        b = a.get_center() + RIGHT * 3 * u
        c = b + UP * 4 * u
        leg_x = Line(a.get_center(), b, color=BLUE, stroke_width=8)
        leg_y = Line(b, c, color=ORANGE, stroke_width=8)
        hyp = Line(a.get_center(), c, color=GREEN, stroke_width=8)
        lx = T("σx = 3", 34, BLUE).next_to(leg_x, DOWN, buff=0.25)
        ly = T("σy = 4", 34, ORANGE).next_to(leg_y, RIGHT, buff=0.25)
        lz = T("σz = ?", 40, GREEN).move_to(hyp.get_center() + LEFT * 1.35 + UP * 0.2)

        self.play(Create(leg_x), FadeIn(lx), run_time=0.8)
        self.play(Create(leg_y), FadeIn(ly), run_time=0.8)
        self.play(Create(hyp), FadeIn(lz), run_time=0.8)
        self.wait(0.4)

        # 단순 합 vs 제곱합
        wrong = T("3 + 4 = 7 ?", 36, SUB).move_to([0, -2.7, 0])
        cross = Line(wrong.get_left() + LEFT * 0.1, wrong.get_right() + RIGHT * 0.1, color="#F87171", stroke_width=6)
        self.play(FadeIn(wrong))
        self.play(Create(cross), run_time=0.5)

        formula = T("σz = √(σx² + σy²)", 38, INK).next_to(wrong, DOWN, buff=0.55)
        self.play(Write(formula), run_time=1.2)
        result = T("√(9 + 16) = 5", 44, GREEN).next_to(formula, DOWN, buff=0.5)
        self.play(
            Transform(lz, T("σz = 5", 40, GREEN).move_to(lz)),
            FadeIn(result, shift=UP * 0.2),
            run_time=1.0,
        )
        self.play(Indicate(hyp, color=GREEN, scale_factor=1.04), run_time=0.8)
        note = T("우연오차는 더하지 않고 제곱해서 합친다", 26, SUB).move_to([0, -5.5, 0])
        self.play(FadeIn(note))
        self.wait(1.0)


class ErrorPropagationBox(Scene):
    """Remotion 숏츠 그림 칸(980x900)에 들어가는 판. 제목·자막은 Remotion 이 얹으므로 도식만 그린다.

    렌더: manim -qh --fps 30 --media_dir <출력폴더> error_propagation.py ErrorPropagationBox
    """

    def __init__(self, *a, **k):
        config.pixel_width, config.pixel_height = 980, 900
        config.frame_height = 7.0
        config.frame_width = 7.0 * 980 / 900
        super().__init__(*a, **k)

    def construct(self):
        u = 0.55
        a = np.array([-1.0, -0.2, 0.0])
        b = a + RIGHT * 3 * u
        c = b + UP * 4 * u
        leg_x = Line(a, b, color=BLUE, stroke_width=8)
        leg_y = Line(b, c, color=ORANGE, stroke_width=8)
        hyp = Line(a, c, color=GREEN, stroke_width=8)
        lx = T("σx = 3", 30, BLUE).next_to(leg_x, DOWN, buff=0.2)
        ly = T("σy = 4", 30, ORANGE).next_to(leg_y, RIGHT, buff=0.2)
        lz = T("σz = ?", 34, GREEN).move_to(hyp.get_center() + LEFT * 1.1 + UP * 0.1)
        self.play(Create(leg_x), FadeIn(lx), run_time=0.7)
        self.play(Create(leg_y), FadeIn(ly), run_time=0.7)
        self.play(Create(hyp), FadeIn(lz), run_time=0.7)

        wrong = T("3 + 4 = 7 ?", 32, SUB).move_to([0, -1.45, 0])
        cross = Line(wrong.get_left() + LEFT * 0.1, wrong.get_right() + RIGHT * 0.1, color="#F87171", stroke_width=6)
        self.play(FadeIn(wrong))
        self.play(Create(cross), run_time=0.4)
        formula = T("σz = √(σx² + σy²)", 34, INK).move_to([0, -2.25, 0])
        self.play(Write(formula), run_time=1.0)
        result = T("√(9 + 16) = 5", 40, GREEN).move_to([0, -3.0, 0])
        self.play(
            Transform(lz, T("σz = 5", 34, GREEN).move_to(lz)),
            FadeIn(result, shift=UP * 0.2),
            run_time=0.9,
        )
        self.play(Indicate(hyp, color=GREEN, scale_factor=1.04), run_time=0.7)
        self.wait(0.8)
