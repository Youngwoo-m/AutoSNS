"""토목 하루 한 문제 15일차 저토피 터널 지표침하: 수식 PNG 2장 + 토피에 따른 침하곡선 변화 GIF.
GIF : ./render.sh civil_day15.py Day15Gif
PNG : manim -qh -s -t --media_dir _media civil_day15.py Day15F1 Day15F2
값은 본문 가상 예시(D 10 m, 체적손실 1.0 %, K 0.5, z0 15 m / 10 m)만 쓴다.
"""
import math
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD, ICE, RUST = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A", "#9FD3E6", "#E08A6A"

D, VL, K = 10.0, 0.01, 0.5
VS = VL * math.pi * D * D / 4


def smax(z0):
    return VS / (math.sqrt(2 * math.pi) * K * z0)


def T(s, size=26, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Day15F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"S(x) = S_{max}\, e^{-x^{2}/2i^{2}}", color=GREEN)
        b = MathTex(r"V_s = \sqrt{2\pi}\, i\, S_{max} = V_L \cdot \frac{\pi D^{2}}{4}", color=GREEN)
        c = MathTex(r"i = K z_0", color=GREEN)
        self.add(VGroup(a, b, c).arrange(RIGHT, buff=0.8).scale_to_fit_width(13))


class Day15F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        rows = [
            r"V_s = 0.01 \times \frac{\pi \times 10^{2}}{4} = 0.785\ \text{m}^{3}/\text{m}",
            r"z_0 = 15\ \text{m}:\ i = 7.5\ \text{m},\ S_{max} = \frac{0.785}{2.507 \times 7.5} = 0.0418\ \text{m} \approx 42\ \text{mm}",
            r"z_0 = 10\ \text{m}:\ i = 5.0\ \text{m},\ S_{max} = \frac{0.785}{2.507 \times 5.0} = 0.0627\ \text{m} \approx 63\ \text{mm}",
        ]
        g = VGroup(*[MathTex(r, color=GREEN) for r in rows]).arrange(DOWN, buff=0.4, aligned_edge=LEFT)
        self.add(g.scale_to_fit_width(13))


class Day15Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("토피가 얕아지면 침하곡선은? (가상 예시, D 10 m, 체적손실 1 %, K 0.5)", 25).to_edge(UP, buff=0.3)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)

        ax = Axes(x_range=[-25, 25, 5], y_range=[-80, 0, 20], x_length=11, y_length=4.2,
                  axis_config={"color": SAND, "include_tip": False},
                  x_axis_config={"numbers_to_include": [-20, -10, 0, 10, 20], "font_size": 22},
                  y_axis_config={"numbers_to_include": [-80, -60, -40, -20], "font_size": 22}).shift(DOWN * 0.4)
        xl = T("터널 중심에서 거리 x (m)", 18).next_to(ax, DOWN, buff=0.15)
        yl = T("침하 (mm)", 18).next_to(ax, LEFT, buff=0.1).shift(UP * 1.6)
        self.play(Create(ax), FadeIn(xl), FadeIn(yl), run_time=0.8)

        z = ValueTracker(15.0)

        def curve():
            i = K * z.get_value(); s = smax(z.get_value()) * 1000
            col = GOLD if z.get_value() > 12.5 else RUST
            return ax.plot(lambda x: -s * math.exp(-x * x / (2 * i * i)), x_range=[-25, 25, 0.25], color=col, stroke_width=6)

        c = always_redraw(curve)
        ghost = ax.plot(lambda x: -smax(15) * 1000 * math.exp(-x * x / (2 * 7.5 ** 2)), x_range=[-25, 25, 0.25],
                        color=GOLD, stroke_width=2, stroke_opacity=0.5)
        val = always_redraw(lambda: T(f"z₀ = {z.get_value():.1f} m   i = {K * z.get_value():.2f} m   S max = {smax(z.get_value()) * 1000:.1f} mm",
                                      22, SAND).next_to(title, DOWN, buff=0.25))
        self.add(c, val)
        self.wait(1.0)
        self.add(ghost)
        self.play(z.animate.set_value(10.0), run_time=2.4, rate_func=smooth)
        res = T("같은 체적손실에서도 폭은 좁고 깊어져 42 → 63 mm", 24, GOLD).next_to(ax, DOWN, buff=0.6)
        self.play(FadeIn(res), run_time=0.6)
        self.wait(2.2)
