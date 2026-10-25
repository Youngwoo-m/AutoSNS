"""샘플 (렌더: math_gif/render.sh soil_phase.py SoilPhase): 흙의 건조단위중량 γd = γt / (1 + w/100) — 3상 도식 + 수식 전개 (Manim -> GIF)"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, INK = "#1F4E3D", "#143528", "#E8DCC2", "#2B2A26"
WATER, AIR = "#4F8FBF", "#F4F1E8"


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class SoilPhase(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("흙의 건조단위중량", 38).to_edge(UP, buff=0.35)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)

        # 3상 도식(공기 / 물 / 흙)
        w, hs = 2.2, [0.9, 1.0, 1.6]
        names, cols = ["공기", "물", "흙 입자"], [AIR, WATER, "#8A6A45"]
        bar, y = VGroup(), 0
        for name, c, h in zip(names, cols, hs):
            r = Rectangle(width=w, height=h, fill_color=c, fill_opacity=1, stroke_color=SAND, stroke_width=3)
            bar.add(r)
        bar.arrange(DOWN, buff=0).to_edge(LEFT, buff=1.1).shift(DOWN * 0.35)
        labels = VGroup(*[T(n, 24, DEEP if i < 2 else SAND).move_to(r) for i, (n, r) in enumerate(zip(names, bar))])
        self.play(LaggedStart(*[FadeIn(r, shift=UP * 0.3) for r in bar], lag_ratio=0.25), run_time=1.2)
        self.play(FadeIn(labels), run_time=0.5)

        # 무게 표시(물·흙)
        ww = M(r"W_w = w\,W_s", SAND, 0.42).next_to(bar[1], RIGHT, buff=0.4)
        ws = M(r"W_s", SAND, 0.42).next_to(bar[2], RIGHT, buff=0.4)
        self.play(Write(ws), Write(ww), run_time=1.0)

        # 수식 전개
        e1 = M(r"\gamma_t = \frac{W}{V} = \frac{W_s + W_w}{V}", SAND, 0.95)
        e2 = M(r"\gamma_d = \frac{W_s}{V}", SAND, 0.95)
        e3 = M(r"\gamma_d = \frac{\gamma_t}{1 + \frac{w}{100}}", "#FFD27A", 1.25)
        col = VGroup(e1, e2, e3).arrange(DOWN, aligned_edge=LEFT, buff=0.55).to_edge(RIGHT, buff=0.8).shift(DOWN * 0.3)
        self.play(Write(e1), run_time=0.9)
        self.play(Write(e2), run_time=0.7)
        self.play(TransformFromCopy(VGroup(e1, e2), e3), run_time=1.4)
        self.play(Indicate(e3, color="#FFD27A", scale_factor=1.05), run_time=1.0)
        self.wait(0.8)
