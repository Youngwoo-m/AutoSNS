"""토목 하루 한 문제 18일차 방파제: Hudson 식 수식 PNG 2장 + 설계파고에 따른 소요중량(H³ 비례) GIF.
GIF : ./render.sh civil_day18.py Day18Gif
PNG : manim -qh -s -t --media_dir _media civil_day18.py Day18F1 Day18F2
값은 본문 가상 예시(테트라포드 제간부 비쇄파 KD 8.0, ρr 2.30 t/m³, ρw 1.03 t/m³, cotα 1.5)만 쓴다.
"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD, ICE, RUST = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A", "#9FD3E6", "#E08A6A"

RR, RW, COT, KD = 2.30, 1.03, 1.5, 8.0
SR = RR / RW


def w(h):
    return RR * h ** 3 / (KD * (SR - 1) ** 3 * COT)


def T(s, size=26, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Day18F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"W = \frac{\rho_r\, H^{3}}{K_D\,(S_r - 1)^{3}\,\cot\alpha}", color=GREEN)
        b = MathTex(r"S_r = \frac{\rho_r}{\rho_w}", color=GREEN)
        self.add(VGroup(a, b).arrange(RIGHT, buff=1.2).scale_to_fit_width(11))


class Day18F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        rows = [
            r"S_r = \frac{2.30}{1.03} \approx 2.233,\quad (S_r - 1)^{3} \approx 1.875",
            r"H = 4.0\ \text{m}:\ W = \frac{2.30 \times 4.0^{3}}{8.0 \times 1.875 \times 1.5} \approx 6.5\ \text{t}",
            r"H = 4.4\ \text{m}:\ W = 6.54 \times 1.1^{3} \approx 8.7\ \text{t}\quad(\times 1.33)",
        ]
        g = VGroup(*[MathTex(r, color=GREEN) for r in rows]).arrange(DOWN, buff=0.4, aligned_edge=LEFT)
        self.add(g.scale_to_fit_width(13))


class Day18Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("설계파고가 커지면 피복재 소요중량은 세제곱으로 커져요(가상 예시)", 25).to_edge(UP, buff=0.3)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)
        f = MathTex(r"W = \frac{\rho_r H^{3}}{K_D (S_r-1)^{3} \cot\alpha}", color=SAND).scale(0.8).next_to(title, DOWN, buff=0.25)
        self.play(Write(f), run_time=0.8)
        ax = Axes(x_range=[2, 6, 1], y_range=[0, 24, 4], x_length=7.5, y_length=3.3,
                  axis_config={"color": SAND, "include_tip": False, "font_size": 22},
                  x_axis_config={"numbers_to_include": [2, 3, 4, 5, 6]},
                  y_axis_config={"numbers_to_include": [0, 4, 8, 12, 16, 20, 24]}).shift(DOWN * 0.75)
        xl = T("설계파고 H (m)", 18).next_to(ax, DOWN, buff=0.15).shift(RIGHT * 2.6)
        yl = T("소요중량 W (t)", 18).next_to(ax, LEFT, buff=0.1).shift(UP * 1.6)
        self.play(Create(ax), FadeIn(xl), FadeIn(yl), run_time=0.7)
        curve = ax.plot(w, x_range=[2, 6], color=ICE)
        self.play(Create(curve), run_time=1.2)
        d1, d2 = Dot(ax.c2p(4.0, w(4.0)), color=GOLD), Dot(ax.c2p(4.4, w(4.4)), color=RUST)
        l1 = T(f"H 4.0 m → {w(4.0):.1f} t", 20, GOLD).next_to(d1, LEFT, buff=0.2)
        l2 = T(f"H 4.4 m(+10 %) → {w(4.4):.1f} t", 20, RUST).next_to(d2, RIGHT, buff=0.2).shift(DOWN * 0.2)
        self.play(FadeIn(d1), FadeIn(l1), run_time=0.6)
        self.wait(0.5)
        self.play(FadeIn(d2), FadeIn(l2), run_time=0.6)
        res = T("파고 10 % 증가 → 중량 약 33 % 증가 (1.1³ ≈ 1.33)", 24, GOLD).next_to(xl, DOWN, buff=0.15).set_x(0)
        self.play(FadeIn(res), run_time=0.6)
        self.wait(2.2)
