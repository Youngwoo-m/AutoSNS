"""토목 하루 한 문제 11일차 연약지반 성토 계측: 수식 PNG 2장 + 쌍곡선법 침하 예측 GIF.
GIF : ./render.sh civil_day11.py Day11Gif
PNG : manim -qh -s -t --media_dir _media civil_day11.py Day11F1 Day11F2
값은 본문 가상 예시(성토 완료 때 S0 0.80 m, 30일 0.20 m·90일 0.40 m 추가 침하)만 쓴다.
"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD, ICE, RUST = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A", "#9FD3E6", "#E08A6A"

S0, A, B = 0.80, 112.5, 1.25           # S0(m), α(일/m), β(1/m)


def M(tex, color=SAND, height=0.5):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=26, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Day11F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"S_{t} = S_{0} + \frac{t}{\alpha + \beta t}", color=GREEN)
        b = MathTex(r"\frac{t}{S_{t} - S_{0}} = \alpha + \beta t", color=GREEN)
        c = MathTex(r"S_{\infty} = S_{0} + \frac{1}{\beta}", color=GREEN)
        self.add(VGroup(a, b, c).arrange(RIGHT, buff=0.9).scale(0.95))


class Day11F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        rows = [
            r"\frac{30}{0.20} = 150,\qquad \frac{90}{0.40} = 225\ \ (\text{day/m})",
            r"\beta = \frac{225 - 150}{90 - 30} = 1.25\ \text{m}^{-1},\qquad \alpha = 150 - 1.25 \times 30 = 112.5",
            r"S_{\infty} = 0.80 + \frac{1}{1.25} = 1.60\ \text{m}",
            r"U = \frac{1.20}{1.60} = 0.75\ (75\%),\qquad S_{\infty} - S_{90} = 0.40\ \text{m}",
        ]
        g = VGroup(*[MathTex(r, color=GREEN) for r in rows]).arrange(DOWN, buff=0.35, aligned_edge=LEFT)
        self.add(g.scale_to_fit_width(12.5))


class Day11Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("쌍곡선법으로 최종침하량 추정 (가상 예시)", 30).to_edge(UP, buff=0.3)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)

        # 왼쪽: 침하-시간 곡선 (아래로 갈수록 침하)
        ax = Axes(x_range=[0, 300, 100], y_range=[0, 1.8, 0.4], x_length=5.6, y_length=3.6,
                  axis_config={"color": SAND, "include_numbers": True, "font_size": 20},
                  tips=False).move_to([-3.4, -0.2, 0])
        xl = T("성토 완료 후 경과일 t", 18).next_to(ax, DOWN, buff=0.25)
        yl = T("침하량 S (m)", 18).next_to(ax, UP, buff=0.1).align_to(ax, LEFT)
        self.play(Create(ax), FadeIn(xl), FadeIn(yl), run_time=0.9)
        s = lambda t: S0 + t / (A + B * t)
        curve = ax.plot(s, x_range=[0, 300], color=GOLD, stroke_width=4)
        pts = VGroup(*[Dot(ax.c2p(t, v), color=RUST, radius=0.08) for t, v in ((0, 0.80), (30, 1.00), (90, 1.20))])
        ptag = T("계측값", 18, RUST).next_to(pts[2], DOWN, buff=0.15)
        self.play(FadeIn(pts), FadeIn(ptag), run_time=0.7)

        # 오른쪽: t/(S−S0) – t 직선
        bx = Axes(x_range=[0, 120, 30], y_range=[0, 300, 100], x_length=4.4, y_length=3.6,
                  axis_config={"color": SAND, "include_numbers": True, "font_size": 20},
                  tips=False).move_to([3.6, -0.2, 0])
        bl = M(r"t/(S_t - S_0)", SAND, 0.32).next_to(bx, UP, buff=0.1).align_to(bx, LEFT)
        bxl = T("t (일)", 18).next_to(bx, DOWN, buff=0.25)
        self.play(Create(bx), FadeIn(bl), FadeIn(bxl), run_time=0.8)
        q = VGroup(*[Dot(bx.c2p(t, v), color=RUST, radius=0.08) for t, v in ((30, 150), (90, 225))])
        line = bx.plot(lambda t: A + B * t, x_range=[0, 120], color=ICE, stroke_width=4)
        self.play(FadeIn(q), run_time=0.5)
        self.play(Create(line), run_time=0.8)
        eqb = M(r"\beta = 1.25,\ \alpha = 112.5", ICE, 0.36).move_to([3.6, -3.65, 0])
        self.play(Write(eqb), run_time=0.8)

        # 최종침하 점근선
        asym = DashedLine(ax.c2p(0, 1.60), ax.c2p(300, 1.60), color=ICE)
        atag = M(r"S_\infty = 0.80 + 1/1.25 = 1.60\ \text{m}", ICE, 0.36).move_to([-3.4, -3.65, 0])
        self.play(Create(curve), Create(asym), Write(atag), run_time=1.4)
        utag = T("90일 침하량 기준 압밀도 1.20/1.60 = 75%", 22, GOLD).move_to([0, 2.75, 0])
        self.play(FadeIn(utag), run_time=0.7)
        self.wait(2.0)
