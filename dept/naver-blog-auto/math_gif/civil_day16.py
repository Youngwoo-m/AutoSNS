"""토목 하루 한 문제 16일차 댐 기초 그라우팅: 루전값 수식 PNG 2장 + 그라우팅 전후 루전값 비교 GIF.
GIF : ./render.sh civil_day16.py Day16Gif
PNG : manim -qh -s -t --media_dir _media civil_day16.py Day16F1 Day16F2
값은 본문 가상 예시(시험구간 5 m, 시험압력 0.5 MPa, 주입량 12 → 2 L/min)만 쓴다.
"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD, ICE, RUST = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A", "#9FD3E6", "#E08A6A"

L, P, P0 = 5.0, 0.5, 1.0
Q_BEFORE, Q_AFTER = 12.0, 2.0


def lu(q):
    return q / L * P0 / P


def T(s, size=26, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Day16F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"Lu = \frac{Q}{L} \times \frac{P_0}{P}", color=GREEN)
        b = MathTex(r"P_0 = 1\ \text{MPa}\ (10\ \text{bar})", color=GREEN)
        c = MathTex(r"1\ Lu \approx 1 \times 10^{-7}\ \text{m/s}", color=GREEN)
        self.add(VGroup(a, b, c).arrange(RIGHT, buff=0.9).scale_to_fit_width(13))


class Day16F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        rows = [
            r"\text{before: } Lu = \frac{12}{5} \times \frac{1.0}{0.5} = 4.8\ Lu \;\Rightarrow\; k \approx 4.8 \times 10^{-7}\ \text{m/s}",
            r"\text{after: } Lu = \frac{2}{5} \times \frac{1.0}{0.5} = 0.8\ Lu \;\Rightarrow\; k \approx 8 \times 10^{-8}\ \text{m/s}",
            r"\text{reduction} = \frac{4.8 - 0.8}{4.8} \approx 83\ \%",
        ]
        g = VGroup(*[MathTex(r, color=GREEN) for r in rows]).arrange(DOWN, buff=0.4, aligned_edge=LEFT)
        self.add(g.scale_to_fit_width(13))


class Day16Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("그라우팅 전후 루전값(가상 예시: 시험구간 5 m, 시험압력 0.5 MPa)", 25).to_edge(UP, buff=0.3)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)
        f = MathTex(r"Lu = \frac{Q}{L} \times \frac{P_0}{P}", color=SAND).scale(0.9).next_to(title, DOWN, buff=0.3)
        self.play(Write(f), run_time=0.8)

        ax = Axes(x_range=[0, 3, 1], y_range=[0, 6, 1], x_length=7, y_length=3.6,
                  axis_config={"color": SAND, "include_tip": False},
                  y_axis_config={"numbers_to_include": [0, 1, 2, 3, 4, 5, 6], "font_size": 22}).shift(DOWN * 1.0)
        yl = T("루전값 (Lu)", 18).next_to(ax, LEFT, buff=0.15).shift(UP * 1.5)
        self.play(Create(ax), FadeIn(yl), run_time=0.7)

        def bar(x, v, col):
            p0, p1 = ax.c2p(x - 0.3, 0), ax.c2p(x + 0.3, v)
            return Rectangle(width=p1[0] - p0[0], height=p1[1] - p0[1], fill_color=col, fill_opacity=0.9,
                             stroke_width=0).move_to([(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, 0])

        b1, b2 = bar(0.9, lu(Q_BEFORE), RUST), bar(2.1, lu(Q_AFTER), ICE)
        l1 = T(f"그라우팅 전\nQ {Q_BEFORE:g} L/min → {lu(Q_BEFORE):.1f} Lu", 19, RUST).next_to(b1, UP, buff=0.12)
        l2 = T(f"그라우팅 후\nQ {Q_AFTER:g} L/min → {lu(Q_AFTER):.1f} Lu", 19, ICE).next_to(b2, UP, buff=0.12)
        self.play(GrowFromEdge(b1, DOWN), FadeIn(l1), run_time=1.0)
        self.wait(0.6)
        self.play(GrowFromEdge(b2, DOWN), FadeIn(l2), run_time=1.0)
        res = T("투수성이 약 83 % 줄어 개량 효과를 확인", 24, GOLD).next_to(ax, DOWN, buff=0.3)
        self.play(FadeIn(res), run_time=0.6)
        self.wait(2.2)
