"""토목 하루 한 문제 7일차 거푸집 해체 강도: 수식 PNG 2장 + 강도 발현·해체 기준선 GIF.
GIF : ./render.sh civil_day07.py Day07Gif
PNG : manim -qh -s -t --media_dir _media civil_day07.py Day07F1 Day07F2
점은 본문 가상 예시(현장양생 공시체 1일 3.2, 3일 9.5, 5일 14.4, 7일 18.6 MPa, fck 27 MPa)만 쓴다.
"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A"


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Day07F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"f_{c,\mathrm{field}}\ \ge\ \max\!\left(\tfrac{2}{3}f_{ck},\ 14\ \mathrm{MPa}\right)", color=GREEN).scale(1.4))


class Day07F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"\max\!\left(\tfrac{2}{3}\times 27,\ 14\right)=\max(18.0,\ 14)=18.0\ \mathrm{MPa}", color=GREEN)
        b = MathTex(r"t=5\,\mathrm{d}:\ 14.4<18.0\quad(\times)", color=GREEN)
        c = MathTex(r"t=7\,\mathrm{d}:\ 18.6\ge 18.0\quad(\checkmark)", color=GREEN)
        self.add(VGroup(a, b, c).arrange(DOWN, buff=0.45, aligned_edge=LEFT).scale(0.95))


class Day07Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("공시체 시험값으로 해체 시점을 확인한다 (가상 예시)", 32).to_edge(UP, buff=0.3)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)

        ox, oy = -5.2, -2.8
        sx, sy = 9.6 / 8, 5.0 / 22
        P = lambda d, f: np.array([ox + d * sx, oy + f * sy, 0])
        xa = Arrow(P(0, 0), P(8, 0), buff=0, color=SAND, stroke_width=4, tip_length=0.2)
        ya = Arrow(P(0, 0), P(0, 22), buff=0, color=SAND, stroke_width=4, tip_length=0.2)
        xl = T("재령(일)", 22).next_to(xa.get_end(), DOWN, buff=0.1)
        yl = M(r"f_c\ (\mathrm{MPa})", SAND, 0.3).next_to(ya.get_end(), RIGHT, buff=0.15)
        ticks = VGroup(*[M(str(d), SAND, 0.22).next_to(P(d, 0), DOWN, buff=0.1) for d in (1, 3, 5, 7)])
        self.play(Create(xa), Create(ya), Write(xl), Write(yl), FadeIn(ticks), run_time=1.0)

        side = DashedLine(P(0, 5), P(7.8, 5), color=SAND, stroke_width=3)
        sidel = T("측면 5 MPa", 22).next_to(P(7.8, 5), UP, buff=0.08).shift(LEFT * 0.6)
        slab = Line(P(0, 18), P(7.8, 18), color=GOLD, stroke_width=5)
        slabl = M(r"\max(\tfrac{2}{3}f_{ck},14)=18.0", GOLD, 0.32).next_to(P(0.2, 18), UP, buff=0.1, aligned_edge=LEFT)
        self.play(Create(side), FadeIn(sidel), run_time=0.7)
        self.play(Create(slab), Write(slabl), run_time=0.8)

        pts = [(0, 0), (1, 3.2), (3, 9.5), (5, 14.4), (7, 18.6)]
        curve = VMobject(color="#FFFFFF", stroke_width=5).set_points_smoothly([P(d, f) for d, f in pts])
        self.play(Create(curve), run_time=1.6)
        dots = VGroup(*[Dot(P(d, f), color="#FFFFFF", radius=0.07) for d, f in pts[1:]])
        labs = VGroup(*[M(f"{f}", "#FFFFFF", 0.24).next_to(P(d, f), RIGHT, buff=0.1).shift(DOWN * 0.15) for d, f in pts[1:-1]],
                      M("18.6", "#FFFFFF", 0.24).next_to(P(7, 18.6), UP, buff=0.3).shift(LEFT * 0.45))
        self.play(FadeIn(dots), FadeIn(labs), run_time=0.6)

        r1 = Circle(0.2, color=SAND, stroke_width=4).move_to(P(3, 9.5))
        t1 = T("3일: 측면 해체 가능", 24).next_to(P(3, 9.5), LEFT, buff=0.35).shift(UP * 0.35)
        self.play(Create(r1), FadeIn(t1), run_time=0.7)
        r2 = Circle(0.2, color=GOLD, stroke_width=4).move_to(P(5, 14.4))
        t2 = T("5일 14.4 < 18.0 아직", 24, GOLD).next_to(P(5, 14.4), RIGHT, buff=0.45).shift(DOWN * 0.55)
        self.play(Create(r2), FadeIn(t2), run_time=0.7)
        r3 = Circle(0.22, color=GOLD, stroke_width=5).move_to(P(7, 18.6))
        t3 = T("7일: 밑면 해체 가능", 26, GOLD).next_to(P(7, 18.6), DOWN, buff=0.4).shift(RIGHT * 0.2)
        self.play(Create(r3), FadeIn(t3), run_time=0.8)
        self.wait(1.4)
