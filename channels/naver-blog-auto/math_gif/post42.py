"""티스토리 42번: 최소제곱조정·가중평균 수식 PNG + 가중평균 저울 GIF."""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A"

class Post42F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(
            r"l+v=Ax,\qquad \min\ v^{T}Pv \;\Rightarrow\; (A^{T}PA)\,x=A^{T}Pl,\qquad p_i\propto\frac{1}{\sigma_i^{2}}",
            color=GREEN).scale(0.8))

class Post42F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(
            r"\hat{x}=\frac{\sum p_i l_i}{\sum p_i}=\frac{4\times100.000+1\times100.010}{4+1}=100.002\ \mathrm{m}",
            color=GREEN).scale(0.85))

class Post42F3(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(
            r"4\times(+2)+1\times(-8)=0,\qquad \sigma_{\hat{x}}=\sqrt{\frac{1}{1/1^{2}+1/2^{2}}}=0.894\ \mathrm{mm}",
            color=GREEN).scale(0.85))


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)

def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)

class Post42Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("가중평균은 무게가 큰 쪽에 가까운 균형점", 34).to_edge(UP, buff=0.35)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)
        # 수직선: 100.000 m 기준 mm, 0~10 mm 를 x=-5..5 에 대응
        x0 = -5.0; sc = 1.0
        X = lambda mm: np.array([x0 + mm * sc, -0.5, 0.0])
        axis = Line(X(-0.5), X(10.5), color=SAND, stroke_width=4)
        ticks = VGroup(*[Line(X(k) + UP * 0.08, X(k) + DOWN * 0.08, color=SAND, stroke_width=3) for k in range(0, 11, 2)])
        tl = VGroup(*[T(f"{k}", 22).next_to(X(k), DOWN, buff=0.15) for k in range(0, 11, 2)])
        unit = T("100.000 m 에서의 차이 (mm)", 22).next_to(axis, DOWN, buff=0.6)
        self.play(Create(axis), FadeIn(ticks), FadeIn(tl), FadeIn(unit), run_time=0.8)
        # 관측값: 크기 = 가중치
        d1 = Circle(radius=0.6, color=GOLD, fill_color=GOLD, fill_opacity=0.85).move_to(X(0) + UP * 0.75)
        d2 = Circle(radius=0.3, color=SAND, fill_color=SAND, fill_opacity=0.85).move_to(X(10) + UP * 0.45)
        t1 = M(r"p_1=4", DEEP, 0.3).move_to(d1)
        t2 = M(r"1", DEEP, 0.26).move_to(d2)
        s1 = T("l₁  σ=1 mm", 22).next_to(d1, UP, buff=0.15)
        s2 = T("l₂  σ=2 mm · p₂=1", 22).next_to(d2, UP, buff=0.15)
        self.play(FadeIn(d1), FadeIn(t1), FadeIn(s1), run_time=0.7)
        self.play(FadeIn(d2), FadeIn(t2), FadeIn(s2), run_time=0.7)
        # 균형점 2 mm
        tri = Triangle(color=GOLD, fill_color=GOLD, fill_opacity=1).scale(0.22).move_to(X(2) + DOWN * 0.72)
        self.play(FadeIn(tri, shift=UP * 0.3), run_time=0.7)
        lab = M(r"\hat{x}=100.002\ \mathrm{m}\ (+2\ \mathrm{mm})", GOLD, 0.42).next_to(tri, DOWN, buff=1.05)
        self.play(Write(lab), run_time=0.9)
        eq = M(r"4\times 2 = 1\times 8", GOLD, 0.55).to_edge(DOWN, buff=0.3)
        self.play(Write(eq), run_time=0.9)
        self.wait(1.0)
