"""토목 하루 한 문제 14일차 비탈면 붕괴: 수식 PNG 2장 + 지하수위 상승에 따른 안전율 변화 GIF.
GIF : ./render.sh civil_day14.py Day14Gif
PNG : manim -qh -s -t --media_dir _media civil_day14.py Day14F1 Day14F2
값은 본문 가상 예시(무한사면, z 2 m, β 30°, c' 5 kPa, φ' 35°, γt 18, γsat 19, γw 9.81 kN/m³)만 쓴다.
"""
import math
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD, ICE, RUST = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A", "#9FD3E6", "#E08A6A"

Z, B, C, PHI, GT, GS, GW = 2.0, math.radians(30), 5.0, math.radians(35), 18.0, 19.0, 9.81


def fs(m):
    g = (1 - m) * GT + m * GS
    cb2 = math.cos(B) ** 2
    return (C + (g * Z * cb2 - m * GW * Z * cb2) * math.tan(PHI)) / (g * Z * math.sin(B) * math.cos(B))


def T(s, size=26, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Day14F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"F_s = \frac{c' + \left(\gamma z \cos^{2}\beta - u\right)\tan\phi'}{\gamma z \sin\beta \cos\beta}", color=GREEN)
        b = MathTex(r"u = m\,\gamma_w z \cos^{2}\beta \quad (0 \le m \le 1)", color=GREEN)
        self.add(VGroup(a, b).arrange(RIGHT, buff=0.9).scale_to_fit_width(13))


class Day14F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        rows = [
            r"m = 0:\ F_s = \frac{5 + 18\cdot 2\cdot 0.75\cdot \tan 35^\circ}{18\cdot 2\cdot 0.5\cdot 0.866} = \frac{23.91}{15.59} = 1.53",
            r"m = 0.5:\ \gamma = 18.5,\ u = 7.36\ \text{kPa} \Rightarrow F_s = \frac{19.28}{16.02} = 1.20",
            r"m = 1:\ \gamma = 19,\ u = 14.72\ \text{kPa} \Rightarrow F_s = \frac{14.65}{16.45} = 0.89",
        ]
        g = VGroup(*[MathTex(r, color=GREEN) for r in rows]).arrange(DOWN, buff=0.4, aligned_edge=LEFT)
        self.add(g.scale_to_fit_width(13))


class Day14Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("비가 스며 지하수위가 오르면 안전율은? (가상 예시, 토층 2 m, 경사 30°)", 26).to_edge(UP, buff=0.3)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)

        # 왼쪽: 비탈 단면(토층 두께 과장)
        ang = 30 * DEGREES
        L = 5.2
        p0 = np.array([-6.3, -2.6, 0]); d = np.array([math.cos(ang), math.sin(ang), 0])
        n = np.array([-math.sin(ang), math.cos(ang), 0])
        th = 1.1
        top0, top1 = p0 + n * th, p0 + d * L + n * th
        bed0, bed1 = p0, p0 + d * L
        soil = Polygon(bed0, bed1, top1, top0, color=SAND, fill_color="#C9B48E", fill_opacity=0.9, stroke_width=2)
        rock = Polygon(bed0, bed1, bed1 + np.array([0, -1.0, 0]), bed0 + np.array([0, -1.0, 0]),
                       color=GRAY, fill_color="#5E646A", fill_opacity=0.9, stroke_width=0)
        slip = Line(bed0, bed1, color=RUST, stroke_width=6)
        lab = T("활동면", 18, RUST).next_to(slip.point_from_proportion(0.55), DOWN + RIGHT, buff=0.15)
        self.play(FadeIn(rock), FadeIn(soil), Create(slip), FadeIn(lab), run_time=0.8)

        m = ValueTracker(0.0)
        water = always_redraw(lambda: Polygon(
            bed0, bed1, bed1 + n * th * max(m.get_value(), 0.001), bed0 + n * th * max(m.get_value(), 0.001),
            color=ICE, fill_color=ICE, fill_opacity=0.55, stroke_width=0))
        self.add(water)

        # 오른쪽: 안전율 막대와 기준선
        x0, y0, hs = 1.2, -2.6, 2.6               # Fs 1.0 = 2.6 단위
        axis = Line([x0 - 0.2, y0, 0], [x0 + 3.4, y0, 0], color=SAND)
        def hline(v, txt, col):
            y = y0 + v * hs
            return VGroup(DashedLine([x0 - 0.2, y, 0], [x0 + 3.4, y, 0], color=col, dash_length=0.12),
                          T(txt, 17, col).move_to([x0 + 4.2, y, 0]))
        l15 = hline(1.5, "건기 1.5", GOLD); l12 = hline(1.2, "우기 1.2", ICE); l10 = hline(1.0, "1.0", RUST)
        self.play(Create(axis), FadeIn(l15), FadeIn(l12), FadeIn(l10), run_time=0.7)
        bar = always_redraw(lambda: Rectangle(width=1.2, height=max(fs(m.get_value()), 0.01) * hs,
                                              color=GOLD if fs(m.get_value()) >= 1.5 else (ICE if fs(m.get_value()) >= 1.0 else RUST),
                                              fill_opacity=0.75, stroke_width=0)
                            .move_to([x0 + 1.4, y0 + fs(m.get_value()) * hs / 2, 0]))
        val = always_redraw(lambda: T(f"m = {m.get_value():.2f}   Fs = {fs(m.get_value()):.2f}", 22, SAND)
                            .move_to([x0 + 1.4, y0 - 0.45, 0]))
        self.add(bar, val)
        self.wait(0.6)
        self.play(m.animate.set_value(0.5), run_time=1.6, rate_func=linear)
        self.wait(0.6)
        self.play(m.animate.set_value(1.0), run_time=1.6, rate_func=linear)
        res = T("같은 비탈면도 물이 차면 1.53 → 0.89 — 배수가 첫 대책", 24, GOLD).move_to([0, 2.55, 0])
        self.play(FadeIn(res), run_time=0.6)
        self.wait(2.0)
