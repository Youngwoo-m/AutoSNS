"""우연오차의 전파 (티스토리 121번): 수식 PNG 3장 + 제곱합의 제곱근 합성 GIF.
GIF : math_gif/render.sh err_prop.py ErrProp
PNG : manim -qh -s -t --media_dir _media err_prop.py FormulaGeneral FormulaArea FormulaLevel  (이후 투명 여백 자르기)
"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A"


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class FormulaGeneral(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"\sigma_y^{2}=\left(\frac{\partial f}{\partial x_1}\right)^{2}\sigma_1^{2}+\left(\frac{\partial f}{\partial x_2}\right)^{2}\sigma_2^{2}+\cdots+\left(\frac{\partial f}{\partial x_n}\right)^{2}\sigma_n^{2}", color=GREEN).scale(0.9))


class FormulaArea(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"\sigma_A=\sqrt{(30\times 0.03)^{2}+(60\times 0.02)^{2}}=\sqrt{0.81+1.44}=1.5\ \mathrm{m^{2}}", color=GREEN).scale(0.95))


class FormulaLevel(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"\sigma_{\mathrm{4km}}=\sigma_{\mathrm{1km}}\sqrt{4}=2\sqrt{4}=4\ \mathrm{mm}", color=GREEN).scale(1.0))


class ErrProp(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("우연오차는 제곱합의 제곱근으로 합성", 36).to_edge(UP, buff=0.35)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)

        # 직각삼각형 두 개: 3-4-5, 5-12-13 (학습용 가정값, mm)
        s = 0.22
        o = LEFT * 5.2 + DOWN * 1.6
        a = Line(o, o + RIGHT * 4 * s * 3, color=SAND, stroke_width=6)          # σ2=4 (가로)
        b = Line(a.get_end(), a.get_end() + UP * 3 * s * 3, color=SAND, stroke_width=6)  # σ1=3 (세로)
        h = Line(o, b.get_end(), color=GOLD, stroke_width=6)
        la = M(r"\sigma_2=4", SAND, 0.38).next_to(a, DOWN, buff=0.15)
        lb = M(r"\sigma_1=3", SAND, 0.38).next_to(b, RIGHT, buff=0.15)
        lh = M(r"5", GOLD, 0.4).move_to(h.get_center() + UP * 0.45 + LEFT * 0.45)
        self.play(Create(a), Write(la), run_time=0.8)
        self.play(Create(b), Write(lb), run_time=0.8)
        self.play(Create(h), Write(lh), run_time=0.8)

        # 두 번째 삼각형: 5(빗변)를 가로로 눕혀 σ3=12 를 세운다
        o2 = RIGHT * 0.6 + DOWN * 1.6
        c = Line(o2, o2 + RIGHT * 5 * s * 1.4, color=GOLD, stroke_width=6)
        d = Line(c.get_end(), c.get_end() + UP * 12 * s * 1.4, color=SAND, stroke_width=6)
        e = Line(o2, d.get_end(), color=GOLD, stroke_width=6)
        lc = M(r"5", GOLD, 0.38).next_to(c, DOWN, buff=0.15)
        ld = M(r"\sigma_3=12", SAND, 0.38).next_to(d, RIGHT, buff=0.15)
        le = M(r"13\ \mathrm{mm}", GOLD, 0.5).move_to(e.get_center() + UP * 0.2 + LEFT * 1.25)
        self.play(TransformFromCopy(h, c), Write(lc), run_time=0.9)
        self.play(Create(d), Write(ld), run_time=0.8)
        self.play(Create(e), Write(le), run_time=0.8)

        eq = M(r"\sqrt{3^{2}+4^{2}+12^{2}}=\sqrt{169}=13", GOLD, 0.7).to_edge(DOWN, buff=0.35)
        note = T("단순 합 19 mm 보다 작다 · 학습용 가정값", 24, SAND).next_to(eq, UP, buff=0.2)
        self.play(Write(eq), FadeIn(note), run_time=1.2)
        self.wait(1.0)
