"""토목 하루 한 문제 12일차 보강토옹벽 붕괴: 수식 PNG 2장 + 배면수압 토압 비교 GIF.
GIF : ./render.sh civil_day12.py Day12Gif
PNG : manim -qh -s -t --media_dir _media civil_day12.py Day12F1 Day12F2
값은 본문 가상 예시(H 6 m, φ 30°, γt 19, γsat 20, γw 9.81 kN/m³, q 10 kPa)만 쓴다.
"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD, ICE, RUST = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A", "#9FD3E6", "#E08A6A"

H, KA, GT, GSUB, GW, Q = 6.0, 1 / 3, 19.0, 20.0 - 9.81, 9.81, 10.0


def M(tex, color=SAND, height=0.5):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=26, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Day12F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"K_a = \tan^{2}\!\left(45^\circ - \frac{\phi}{2}\right)", color=GREEN)
        b = MathTex(r"P_a = \frac{1}{2} K_a \gamma H^{2}", color=GREEN)
        c = MathTex(r"P_q = K_a q H", color=GREEN)
        d = MathTex(r"P_w = \frac{1}{2} \gamma_w H^{2}", color=GREEN)
        self.add(VGroup(a, b, c, d).arrange(RIGHT, buff=0.7).scale_to_fit_width(13))


class Day12F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        rows = [
            r"K_a = \tan^{2}(30^\circ) = 1/3",
            r"\text{dry: } P_a = \tfrac{1}{2}\cdot\tfrac{1}{3}\cdot 19 \cdot 6^{2} = 114.0,\quad P_q = \tfrac{1}{3}\cdot 10 \cdot 6 = 20.0\ \Rightarrow\ 134.0\ \text{kN/m}",
            r"\text{flooded: } \gamma' = 20 - 9.81 = 10.19,\quad P_a' = \tfrac{1}{2}\cdot\tfrac{1}{3}\cdot 10.19 \cdot 6^{2} = 61.1",
            r"P_w = \tfrac{1}{2}\cdot 9.81 \cdot 6^{2} = 176.6\ \Rightarrow\ 61.1 + 20.0 + 176.6 = 257.7\ \text{kN/m}\ (\approx 1.92\times)",
        ]
        g = VGroup(*[MathTex(r, color=GREEN) for r in rows]).arrange(DOWN, buff=0.35, aligned_edge=LEFT)
        self.add(g.scale_to_fit_width(13))


class Day12Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("배면에 물이 차면 벽이 받는 힘 (가상 예시, 높이 6 m)", 28).to_edge(UP, buff=0.3)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)

        s = 0.5                                   # 1 m = 0.5 단위
        def diagram(cx, wet):
            base = cx - 1.6
            top, bot = 2.0 * s + 0.2, -4.0 * s + 0.2 - 2.0 * s
            wall = Rectangle(width=0.18, height=H * s, color=SAND, fill_color=SAND, fill_opacity=0.9)
            wall.move_to([base, 0.2 - 1.5 * s + 0.5, 0])
            y0 = wall.get_top()[1]
            y1 = wall.get_bottom()[1]
            x0 = wall.get_right()[0]
            k = 0.022                             # kPa → 화면 폭
            soil = (GSUB if wet else GT) * KA * H
            surch = KA * Q
            poly_q = Polygon([x0, y0, 0], [x0 + surch * k, y0, 0], [x0 + surch * k, y1, 0], [x0, y1, 0],
                             color=GOLD, fill_color=GOLD, fill_opacity=0.55, stroke_width=2)
            poly_s = Polygon([x0 + surch * k, y0, 0], [x0 + surch * k, y1, 0], [x0 + (surch + soil) * k, y1, 0],
                             color=RUST, fill_color=RUST, fill_opacity=0.6, stroke_width=2)
            parts = [poly_q, poly_s]
            if wet:
                xs = x0 + (surch + soil) * k
                poly_w = Polygon([xs, y0, 0], [xs, y1, 0], [xs + GW * H * k, y1, 0],
                                 color=ICE, fill_color=ICE, fill_opacity=0.6, stroke_width=2)
                parts.append(poly_w)
            return wall, parts, y1

        dw, dparts, yb = diagram(-3.3, False)
        ww, wparts, _ = diagram(2.9, True)
        h1 = T("배수가 잘 될 때", 24, SAND).move_to([-2.6, 2.6, 0])
        h2 = T("배면이 물에 잠길 때", 24, ICE).move_to([3.4, 2.6, 0])
        self.play(FadeIn(dw), FadeIn(ww), FadeIn(h1), FadeIn(h2), run_time=0.6)
        self.play(*[GrowFromEdge(p, LEFT) for p in dparts], run_time=1.0)
        t1 = M(r"114.0 + 20.0 = 134.0\ \text{kN/m}", SAND, 0.38).move_to([-2.6, yb - 0.55, 0])
        self.play(Write(t1), run_time=0.7)
        self.play(*[GrowFromEdge(p, LEFT) for p in wparts[:2]], run_time=0.8)
        self.play(GrowFromEdge(wparts[2], LEFT), run_time=1.0)
        t2 = M(r"61.1 + 20.0 + 176.6 = 257.7\ \text{kN/m}", ICE, 0.38).move_to([3.4, yb - 0.55, 0])
        self.play(Write(t2), run_time=0.7)
        leg = VGroup(
            VGroup(Square(0.22, color=GOLD, fill_color=GOLD, fill_opacity=0.6), T("상재하중", 18)).arrange(RIGHT, buff=0.12),
            VGroup(Square(0.22, color=RUST, fill_color=RUST, fill_opacity=0.6), T("흙 토압", 18)).arrange(RIGHT, buff=0.12),
            VGroup(Square(0.22, color=ICE, fill_color=ICE, fill_opacity=0.6), T("수압", 18)).arrange(RIGHT, buff=0.12),
        ).arrange(RIGHT, buff=0.5).to_edge(DOWN, buff=0.25)
        self.play(FadeIn(leg), run_time=0.5)
        res = T("물이 빠지지 않으면 약 1.92배 — 배수가 대책의 핵심", 24, GOLD).move_to([0, 1.95, 0])
        self.play(FadeIn(res), run_time=0.7)
        self.wait(2.0)
