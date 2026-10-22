"""티스토리 108번 수식 PNG (+GIF). PNG: manim -qh -s -t --media_dir _media post108.py Post108F1 ... (이후 투명 여백 자르기)"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A"


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Post108F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"N=h-H\ \ (\mathrm{m})", color=GREEN).scale(1.3))


class Post108Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("한 점에서 h 와 H 를 알면 N 이 나온다", 34).to_edge(UP, buff=0.35)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)
        ell = Line(LEFT * 5.5 + DOWN * 2.2, RIGHT * 5.5 + DOWN * 2.0, color=SAND, stroke_width=5)
        geo = Line(LEFT * 5.5 + DOWN * 1.0, RIGHT * 5.5 + DOWN * 0.7, color=GOLD, stroke_width=5)
        lell = T("타원체", 26, SAND).next_to(ell, DOWN, buff=0.1).align_to(ell, LEFT)
        lgeo = T("지오이드", 26, GOLD).next_to(geo, DOWN, buff=0.1).align_to(geo, LEFT).shift(UP * 0.0)
        self.play(Create(ell), FadeIn(lell), Create(geo), FadeIn(lgeo), run_time=1.0)
        x = 1.5
        ye = ell.point_from_proportion((x + 5.5) / 11)[1]
        yg = geo.point_from_proportion((x + 5.5) / 11)[1]
        yp = 1.2
        pt = Dot([x, yp, 0], color=SAND, radius=0.12)
        lp = T("기준점", 26, SAND).next_to(pt, UP, buff=0.12)
        self.play(FadeIn(pt), FadeIn(lp), run_time=0.6)
        ah = DoubleArrow([x + 1.3, ye, 0], [x + 1.3, yp, 0], color=SAND, buff=0, stroke_width=5)
        aH = DoubleArrow([x - 1.3, yg, 0], [x - 1.3, yp, 0], color=GOLD, buff=0, stroke_width=5)
        aN = DoubleArrow([x + 0.0, ye, 0], [x + 0.0, yg, 0], color="#9BD0A8", buff=0, stroke_width=5)
        for a in (ah, aH, aN):
            pass
        self.play(GrowFromCenter(ah), Write(M("h", SAND, 0.4).next_to(ah, RIGHT, buff=0.15)), run_time=0.8)
        self.play(GrowFromCenter(aH), Write(M("H", GOLD, 0.4).next_to(aH, LEFT, buff=0.15)), run_time=0.8)
        self.play(GrowFromCenter(aN), Write(M("N", "#9BD0A8", 0.4).next_to(aN, LEFT, buff=0.12).shift(RIGHT*0.0)), run_time=0.8)
        eq = M(r"h=H+N\ \Rightarrow\ N=h-H", GOLD, 0.6).to_edge(DOWN, buff=0.3)
        self.play(Write(eq), run_time=1.0)
        self.wait(1.0)
