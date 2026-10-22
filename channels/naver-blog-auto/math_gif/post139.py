"""티스토리 139번(Sterneck법): 위도 식 유도 PNG, 계산 예 PNG, 영점오차 상쇄 GIF.
GIF : math_gif/render.sh post139.py Post139Gif
PNG : manim -qh -s -t --media_dir _media post139.py Post139F1 Post139F2  (이후 투명 여백 자르고 흰 바탕)
"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A"


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Post139F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        eq = MathTex(
            r"z_s=\varphi-\delta_s,\qquad z_n=\delta_n-\varphi\\[6pt]"
            r"\varphi=\frac{\delta_s+\delta_n}{2}+\frac{z_s-z_n}{2}",
            color=GREEN,
        ).scale(0.95)
        self.add(eq)


class Post139F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        eq = MathTex(
            r"\frac{\delta_s+\delta_n}{2}&=37^{\circ}07'55'',\quad \frac{z_s-z_n}{2}=-0^{\circ}02'20''\\[6pt]"
            r"\varphi&=37^{\circ}07'55''-0^{\circ}02'20''=37^{\circ}05'35''",
            color=GREEN,
        ).scale(0.9)
        self.add(eq)


class Post139Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("영점오차는 두 별의 평균에서 상쇄된다", 34).to_edge(UP, buff=0.35)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)

        # 수직선: 37°05′ 에서 초 단위(20″~50″). 학습용 가정값
        x0, x1 = -5.0, 5.0
        sx = lambda v: x0 + (v - 15) / 40 * (x1 - x0)
        y = -0.6
        axis = Line(LEFT * 5.4 + UP * y, RIGHT * 5.4 + UP * y, color=SAND, stroke_width=3)
        ticks = VGroup(*[Line(UP * (y - 0.1) + RIGHT * sx(v), UP * (y + 0.1) + RIGHT * sx(v), color=SAND, stroke_width=3) for v in (20, 30, 40, 50)])
        tl = VGroup(*[M(rf"{v}''", SAND, 0.3).move_to(RIGHT * sx(v) + UP * (y - 0.45)) for v in (20, 30, 40, 50)])
        unit = T("φ  (37°05′ 에서 잰 초)", 22, SAND).next_to(axis, DOWN, buff=0.85)
        self.play(Create(axis), FadeIn(ticks), FadeIn(tl), FadeIn(unit), run_time=0.8)

        def dot(v, color, label):
            d = Dot(RIGHT * sx(v) + UP * y, radius=0.17, color=color)
            l = T(label, 26, color).next_to(d, UP, buff=0.35)
            return d, l

        ds, ls = dot(40, SAND, "남쪽 별 S")
        dn, ln = dot(30, SAND, "북쪽 별 N")
        self.play(FadeIn(ds), FadeIn(ls), FadeIn(dn), FadeIn(ln), run_time=0.8)
        mean = Dot(RIGHT * sx(35) + UP * y, radius=0.2, color=GOLD)
        mline = DashedLine(RIGHT * sx(35) + UP * (y + 2.2), RIGHT * sx(35) + UP * (y - 0.2), color=GOLD, stroke_width=3)
        self.play(GrowFromCenter(mean), Create(mline), run_time=0.7)
        self.wait(0.3)

        # 영점오차 +10″: 남쪽 +10″ (φ=δ+z), 북쪽 -10″ (φ=δ-z)
        note = T("영점오차 +10″ 가 천정거리에 똑같이 들어가면", 26, SAND).to_edge(DOWN, buff=1.0)
        self.play(FadeIn(note), run_time=0.5)
        self.play(
            ds.animate.move_to(RIGHT * sx(50) + UP * y),
            ls.animate.next_to(RIGHT * sx(50) + UP * y, UP, buff=0.35),
            dn.animate.move_to(RIGHT * sx(20) + UP * y),
            ln.animate.next_to(RIGHT * sx(20) + UP * y, UP, buff=0.35),
            run_time=1.4,
        )
        res = T("S 는 +10″, N 은 -10″ 어긋나도 평균은 그대로 35″", 26, GOLD).next_to(note, DOWN, buff=0.2)
        self.play(FadeIn(res), Indicate(mean, color=GOLD, scale_factor=1.4), run_time=1.0)
        self.wait(1.2)
