"""티스토리 99번 흙의 다짐: 수식 PNG 2장 + 건조밀도 환산 GIF.
GIF : ./render.sh post99.py Post99Gif
PNG : manim -qh -s -t --media_dir _media post99.py Post99F1 Post99F2  (이후 투명 여백 자르기)
"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A"


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Post99F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"\rho_d=\frac{\rho}{1+w}", color=GREEN).scale(1.6))


class Post99F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"\rho_d=\frac{2.016}{1+0.12}=1.800\ \mathrm{Mg/m^{3}}", color=GREEN)
        b = MathTex(r"R_c=\frac{1.800}{1.900}\times 100=94.7\,\%", color=GREEN)
        self.add(VGroup(a, b).arrange(DOWN, buff=0.5).scale(1.1))


class Post99Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("습윤밀도에서 건조밀도로, 다시 다짐도로", 34).to_edge(UP, buff=0.35)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)

        base = LEFT * 4.4 + DOWN * 2.2
        W = 1.9
        soil = Rectangle(width=W, height=3.0, fill_color=SAND, fill_opacity=1, stroke_color=SAND).move_to(base + UP * 1.5 + RIGHT * W / 2 * 0)
        soil.align_to(base, DOWN)
        water = Rectangle(width=W, height=0.36, fill_color=GOLD, fill_opacity=1, stroke_color=GOLD)
        water.next_to(soil, UP, buff=0)
        ls = T("건조토 = 1", 26, DEEP).move_to(soil)
        lw = M(r"w=0.12", GOLD, 0.3).next_to(water, UP, buff=0.12)
        self.play(FadeIn(soil), Write(ls), run_time=0.8)
        self.play(FadeIn(water, shift=DOWN * 0.2), Write(lw), run_time=0.8)

        brace = Brace(VGroup(soil, water), RIGHT, color=GOLD)
        bl = M(r"1+w=1.12", GOLD, 0.36).next_to(brace, RIGHT, buff=0.12)
        self.play(GrowFromCenter(brace), Write(bl), run_time=0.9)

        e1 = M(r"\rho=2.016\ \mathrm{Mg/m^{3}}", SAND, 0.5)
        e2 = M(r"\rho_d=\frac{\rho}{1+w}=\frac{2.016}{1.12}=1.800\ \mathrm{Mg/m^{3}}", GOLD, 0.8)
        e3 = M(r"R_c=\frac{1.800}{1.900}\times 100=94.7\,\%", GOLD, 0.8)
        col = VGroup(e1, e2, e3).arrange(DOWN, buff=0.45, aligned_edge=LEFT)
        col.set(width=min(col.width, 6.2)).to_edge(RIGHT, buff=0.4).shift(UP * 0.2)
        self.play(Write(e1), run_time=0.8)
        self.play(Write(e2), run_time=1.3)
        self.play(Write(e3), run_time=1.3)
        note = T("가상 수치 · 함수비는 소수(0.12)로 대입", 24, SAND).to_edge(DOWN, buff=0.3)
        self.play(FadeIn(note), run_time=0.5)
        self.wait(1.0)
