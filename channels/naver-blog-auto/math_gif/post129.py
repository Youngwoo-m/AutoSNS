"""티스토리 129번 수식 PNG (+GIF). PNG: manim -qh -s -t --media_dir _media post129.py Post129F1 ... (이후 투명 여백 자르기)"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A"


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Post129F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"d=\frac{v\,t}{2},\qquad v=\frac{c}{\sqrt{\varepsilon_r}}", color=GREEN).scale(1.2))


class Post129F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"v=\frac{0.3}{\sqrt{9}}=0.1\ \mathrm{m/ns},\quad d=\frac{0.1\times 20}{2}=1.0\ \mathrm{m}", color=GREEN).scale(0.95))


class Post129Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("GPR 심도: 왕복시간의 절반 × 전파속도", 34).to_edge(UP, buff=0.35)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)
        ground = Line(LEFT * 5.5 + UP * 1.2, RIGHT * 5.5 + UP * 1.2, color=SAND, stroke_width=5)
        lg = T("지표", 24, SAND).next_to(ground, UP, buff=0.1).align_to(ground, LEFT)
        pipe = Circle(radius=0.3, color=GOLD, stroke_width=6).move_to([0, -1.4, 0])
        lp = T("관 상단", 24, GOLD).next_to(pipe, RIGHT, buff=0.3)
        ant = Rectangle(width=0.9, height=0.35, color=SAND, fill_color=SAND, fill_opacity=1).move_to([0, 1.4, 0])
        self.play(Create(ground), FadeIn(lg), Create(pipe), FadeIn(lp), FadeIn(ant), run_time=1.0)
        top = [0, -1.1, 0]
        down = Arrow([-0.35, 1.2, 0], [-0.35, -1.1, 0], color=SAND, buff=0, stroke_width=5)
        up = Arrow([0.35, -1.1, 0], [0.35, 1.2, 0], color="#9BD0A8", buff=0, stroke_width=5)
        self.play(GrowArrow(down), run_time=0.9)
        self.play(GrowArrow(up), run_time=0.9)
        t = VGroup(M(r"t=20\ \mathrm{ns}", SAND, 0.4), T("(왕복시간)", 22, SAND)).arrange(DOWN, buff=0.12).move_to([-3.6, 0.0, 0])
        v = M(r"v=\frac{0.3}{\sqrt{9}}=0.1\ \mathrm{m/ns}", GOLD, 1.0).move_to([3.6, 0.0, 0])
        self.play(Write(t), Write(v), run_time=1.2)
        dd = M(r"d=\frac{0.1\times 20}{2}=1.0\ \mathrm{m}", GOLD, 0.95).to_edge(DOWN, buff=0.3)
        note = T("학습용 가정 수치 (비유전율 9)", 24, SAND).next_to(dd, UP, buff=0.15)
        self.play(Write(dd), FadeIn(note), run_time=1.2)
        self.wait(1.2)
