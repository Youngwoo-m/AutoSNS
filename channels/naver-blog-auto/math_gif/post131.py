"""티스토리 131번 Davisson 오프셋 한계: 수식 PNG 2장 + 한계선 교점 GIF.
GIF : ./render.sh post131.py Post131Gif
PNG : manim -qh -s -t --media_dir _media post131.py Post131F1 Post131F2
점은 본문 학습용 가정값(2,500 kN→17.0 mm, 3,000 kN→26.0 mm)만 쓴다.
"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A"


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Post131F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"s_{\lim}=\frac{QL}{AE}+\left(4+\frac{D}{120}\right)\ [\mathrm{mm}]", color=GREEN).scale(1.3))


class Post131F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"s_{\lim}(2500\,\mathrm{kN})=13.37+8.23=21.60\ \mathrm{mm}", color=GREEN)
        b = MathTex(r"s_{\lim}(3000\,\mathrm{kN})=16.04+8.23=24.28\ \mathrm{mm}", color=GREEN)
        c = MathTex(r"Q_u=2500+500\times\frac{4.60}{4.60+1.72}\approx 2864\ \mathrm{kN}", color=GREEN)
        self.add(VGroup(a, b, c).arrange(DOWN, buff=0.45, aligned_edge=LEFT).scale(0.95))


class Post131Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("Davisson 오프셋 한계선과 만나는 하중 = 극한하중", 32).to_edge(UP, buff=0.3)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)

        # 축: 가로 하중 0~3500 kN, 세로 침하 0~30 mm (아래로 증가)
        ox, oy = -5.0, 2.3
        sx, sy = 9.6 / 3500, 4.6 / 30
        P = lambda q, s: np.array([ox + q * sx, oy - s * sy, 0])
        xa = Arrow(P(0, 0), P(3500, 0), buff=0, color=SAND, stroke_width=4, tip_length=0.2)
        ya = Arrow(P(0, 0), P(0, 30), buff=0, color=SAND, stroke_width=4, tip_length=0.2)
        xl = M(r"Q\ (\mathrm{kN})", SAND, 0.3).next_to(xa.get_end(), DOWN, buff=0.1)
        yl = M(r"s\ (\mathrm{mm})", SAND, 0.3).next_to(ya.get_end(), LEFT, buff=0.15)
        self.play(Create(xa), Create(ya), Write(xl), Write(yl), run_time=1.0)

        k = 20000 / 3.74e6  # mm per kN (L/AE, 본문 값)
        el = DashedLine(P(0, 0), P(3500, 3500 * k), color=SAND, stroke_width=3)
        ell = M(r"QL/AE", SAND, 0.3).next_to(P(3500, 3500 * k), DOWN, buff=0.1).shift(LEFT * 0.4)
        self.play(Create(el), Write(ell), run_time=0.9)

        off = 4 + 508 / 120
        lim = Line(P(0, off), P(3500, 3500 * k + off), color=GOLD, stroke_width=5)
        limlab = M(r"s_{\lim}=QL/AE+8.23", GOLD, 0.3).next_to(P(3500, 3500 * k + off), DOWN, buff=0.2).shift(RIGHT * 0.3)
        brace = BraceBetweenPoints(P(0, 0), P(0, off), LEFT, color=GOLD)
        offl = M(r"8.23", GOLD, 0.28).next_to(brace, LEFT, buff=0.08)
        self.play(Create(lim), Write(limlab), run_time=1.0)
        self.play(GrowFromCenter(brace), Write(offl), run_time=0.6)

        p1, p2 = P(2500, 17.0), P(3000, 26.0)
        seg = Line(p1, p2, color="#FFFFFF", stroke_width=5)
        d1, d2 = Dot(p1, color="#FFFFFF", radius=0.08), Dot(p2, color="#FFFFFF", radius=0.08)
        l1 = M(r"17.0", "#FFFFFF", 0.26).next_to(p1, LEFT, buff=0.12)
        l2 = M(r"26.0", "#FFFFFF", 0.26).next_to(p2, DOWN, buff=0.15).shift(LEFT * 0.35)
        self.play(FadeIn(d1), FadeIn(d2), Write(l1), Write(l2), Create(seg), run_time=1.1)

        qu = 2864
        pq = P(qu, qu * k + off)
        dq = Dot(pq, color=GOLD, radius=0.14)
        vl = DashedLine(pq, P(qu, 0), color=GOLD, stroke_width=3)
        ql = M(r"Q_u\approx 2860\ \mathrm{kN}", GOLD, 0.4).next_to(P(qu, 7), LEFT, buff=0.12)
        self.play(FadeIn(dq, scale=2), Create(vl), Write(ql), run_time=1.1)
        note = T("학습용 가정값 · 측정점 2개를 직선 보간", 24, SAND).to_edge(DOWN, buff=0.25)
        self.play(FadeIn(note), run_time=0.5)
        self.wait(1.0)
