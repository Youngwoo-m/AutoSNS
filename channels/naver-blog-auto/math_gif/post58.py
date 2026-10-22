"""티스토리 58번: 폐합트래버스 좌표폐합차·Bowditch 보정 수식 PNG + 보정 배분 GIF."""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A"

class Post58F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"f_E=\sum \Delta E,\quad f_N=\sum \Delta N,\quad f=\sqrt{f_E^{2}+f_N^{2}},\quad K=\frac{\sum L}{f}", color=GREEN).scale(0.85))

class Post58F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"c_E(i)=-f_E\,\frac{L(i)}{\sum L},\qquad c_N(i)=-f_N\,\frac{L(i)}{\sum L}", color=GREEN).scale(0.95))

class Post58F3(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(
            r"f=\sqrt{0.040^{2}+(-0.030)^{2}}=0.050\ \mathrm{m},\quad \frac{1}{K}=\frac{0.050}{400}=\frac{1}{8000}",
            color=GREEN).scale(0.8))

class Post58F4(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(
            r"c_E=-0.040\times\frac{100}{400}=-0.010\ \mathrm{m},\qquad c_N=-(-0.030)\times\frac{100}{400}=+0.0075\ \mathrm{m}",
            color=GREEN).scale(0.75))


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)

def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)

class Post58Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("Bowditch 보정: 폐합차를 거리 비례로 나눠 닫는다", 32).to_edge(UP, buff=0.3)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)
        # 이상 루프(정사각형)와 계산 루프(폐합차 확대). 비축척 도식.
        A = np.array([-1.6, -1.2, 0.0]); side = 3.0
        ideal = [A, A + RIGHT * side, A + RIGHT * side + UP * side, A + UP * side, A]
        gap = np.array([0.9, -0.7, 0.0])  # 확대한 폐합차(fE>0 동, fN<0 북)
        raw = [ideal[0], ideal[1] + gap * 0.25, ideal[2] + gap * 0.5, ideal[3] + gap * 0.75, ideal[4] + gap]
        names = ["A", "B", "C", "D", "A'"]
        # 이상 루프 (옅게)
        ghost = VMobject(color=SAND, stroke_width=3, stroke_opacity=0.35).set_points_as_corners(ideal)
        path = VMobject(color=SAND, stroke_width=6).set_points_as_corners(raw)
        sub = T("비축척 · 폐합차는 확대해서 표시", 22, SAND).next_to(title, DOWN, buff=0.15)
        self.play(Create(ghost), FadeIn(sub), run_time=0.6)
        self.play(Create(path), run_time=1.6)
        dots = VGroup(*[Dot(p, color=SAND, radius=0.09) for p in raw])
        self.play(FadeIn(dots), run_time=0.3)
        flab = M(r"f=0.050\ \mathrm{m}", GOLD, 0.4)
        arrow = Arrow(raw[4], ideal[4], buff=0.05, color=GOLD, stroke_width=6, max_tip_length_to_length_ratio=0.3)
        flab.next_to(ideal[0], LEFT, buff=0.5)
        self.play(GrowArrow(arrow), Write(flab), run_time=0.9)
        note = T("각 변 L=100 m, ΣL=400 m → 각 변이 1/4 씩 부담", 24, SAND).to_edge(DOWN, buff=1.05)
        self.play(FadeIn(note), run_time=0.6)
        self.wait(0.6)
        # 보정: 점 k 를 -gap*k/4 만큼 이동
        fixed = [raw[k] - gap * (k / 4) for k in range(5)]
        newpath = VMobject(color=GOLD, stroke_width=6).set_points_as_corners(fixed)
        newdots = VGroup(*[Dot(p, color=GOLD, radius=0.09) for p in fixed])
        self.play(Transform(path, newpath), Transform(dots, newdots), FadeOut(arrow), FadeOut(flab), run_time=2.0)
        eq = M(r"\sum c_E=-f_E,\ \ \sum c_N=-f_N", GOLD, 0.5).to_edge(DOWN, buff=0.3)
        self.play(Write(eq), run_time=1.0)
        self.wait(1.0)
