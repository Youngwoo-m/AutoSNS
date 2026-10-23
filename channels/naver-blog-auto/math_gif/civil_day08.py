"""토목 하루 한 문제 8일차 한중콘크리트: 수식 PNG 2장 + 적산온도 누적 GIF.
GIF : ./render.sh civil_day08.py Day08Gif
PNG : manim -qh -s -t --media_dir _media civil_day08.py Day08F1 Day08F2
값은 본문 가상 예시(품질기준강도 24 MPa, 기온보정 6 MPa, 10 ℃ 3일 + 5 ℃ 4일 보온양생)만 쓴다.
"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD, ICE = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A", "#9FD3E6"


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Day08F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"f_{cn} = f_{cq} + T_n\qquad (T_n = 6\ \mathrm{MPa},\ 0 \le \bar\theta_{28} < 4\ ^\circ\mathrm{C})", color=GREEN)
        b = MathTex(r"M = \sum (\theta + 10)\,\Delta t\quad [^\circ\mathrm{C}\cdot\mathrm{D}]", color=GREEN)
        self.add(VGroup(a, b).arrange(DOWN, buff=0.55, aligned_edge=LEFT).scale(1.0))


class Day08F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"f_{cn} = 24 + 6 = 30\ \mathrm{MPa}", color=GREEN)
        b = MathTex(r"W/B = 170/340 = 0.50 \le 0.60,\quad FA \le 0.15\times 340 = 51\ \mathrm{kg/m^3}", color=GREEN)
        c = MathTex(r"M = 3(10+10) + 4(5+10) = 60 + 60 = 120\ ^\circ\mathrm{C}\cdot\mathrm{D}", color=GREEN)
        d = MathTex(r"t_{20} = 120 / (20+10) = 4.0\ \mathrm{d}", color=GREEN)
        self.add(VGroup(a, b, c, d).arrange(DOWN, buff=0.4, aligned_edge=LEFT).scale(0.85))


class Day08Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("적산온도로 본 7일 보온양생 (가상 예시)", 32).to_edge(UP, buff=0.3)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)

        ox, oy = -5.0, -2.8
        sx, sy = 9.4 / 8, 5.0 / 220
        P = lambda d, m: np.array([ox + d * sx, oy + m * sy, 0])
        xa = Arrow(P(0, 0), P(8, 0), buff=0, color=SAND, stroke_width=4, tip_length=0.2)
        ya = Arrow(P(0, 0), P(0, 225), buff=0, color=SAND, stroke_width=4, tip_length=0.2)
        xl = T("양생 일수(일)", 22).next_to(xa.get_end(), DOWN, buff=0.1).shift(LEFT * 0.4)
        yl = M(r"M\ (^\circ\mathrm{C\cdot D})", SAND, 0.3).next_to(ya.get_end(), RIGHT, buff=0.15)
        ticks = VGroup(*[M(str(d), SAND, 0.22).next_to(P(d, 0), DOWN, buff=0.1) for d in (1, 2, 3, 4, 5, 6, 7)])
        self.play(Create(xa), Create(ya), Write(xl), Write(yl), FadeIn(ticks), run_time=1.0)

        ref = DashedLine(P(0, 0), P(7, 210), color=ICE, stroke_width=3)
        refl = T("20 ℃ 표준양생 (30/일)", 22, ICE).next_to(P(6.2, 186), LEFT, buff=0.2)
        self.play(Create(ref), FadeIn(refl), run_time=0.9)

        seg1 = Line(P(0, 0), P(3, 60), color=GOLD, stroke_width=6)
        l1 = T("10 ℃ 급열 3일: 20/일", 22, GOLD).next_to(P(1.5, 30), DOWN + RIGHT, buff=0.15)
        self.play(Create(seg1), FadeIn(l1), run_time=1.2)
        seg2 = Line(P(3, 60), P(7, 120), color="#FFFFFF", stroke_width=6)
        l2 = T("5 ℃ 4일: 15/일", 22).next_to(P(5.5, 97), DOWN + RIGHT, buff=0.1)
        self.play(Create(seg2), FadeIn(l2), run_time=1.4)

        dot = Dot(P(7, 120), color=GOLD, radius=0.08)
        v = M(r"M = 120", GOLD, 0.32).next_to(P(7, 120), RIGHT, buff=0.15)
        self.play(FadeIn(dot), Write(v), run_time=0.6)
        hl = DashedLine(P(7, 120), P(4, 120), color=GOLD, stroke_width=3)
        d4 = Dot(P(4, 120), color=ICE, radius=0.08)
        vl = DashedLine(P(4, 120), P(4, 0), color=ICE, stroke_width=3)
        t4 = T("20 ℃ 환산 4.0일", 26, ICE).next_to(P(4, 120), UP, buff=0.25).shift(LEFT * 0.6)
        self.play(Create(hl), FadeIn(d4), run_time=0.7)
        self.play(Create(vl), FadeIn(t4), run_time=0.7)
        self.wait(1.4)
