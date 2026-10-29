"""토목 하루 한 문제 9일차 숏크리트 리바운드: 수식 PNG 2장 + 반발률과 분사량 GIF.
GIF : ./render.sh civil_day09.py Day09Gif
PNG : manim -qh -s -t --media_dir _media civil_day09.py Day09F1 Day09F2
값은 본문 가상 예시(분사 11,500 kg 중 반발 1,380 kg / 부착 소요 220 m³, 반발률 16.8 %·9.8 %)만 쓴다.
"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD, ICE, RUST = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A", "#9FD3E6", "#E08A6A"


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Day09F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"RR = \frac{R_{sum}}{S_{sum}} \times 100\ (\%)", color=GREEN)
        b = MathTex(r"Y_{sum} = S_{sum} - R_{sum}\qquad V_{shot} = \frac{V_{need}}{1 - RR/100}", color=GREEN)
        self.add(VGroup(a, b).arrange(DOWN, buff=0.55, aligned_edge=LEFT).scale(1.0))


class Day09F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"S_{sum} = 5.0 \times 2300 = 11500\ \mathrm{kg}", color=GREEN)
        b = MathTex(r"RR = 1380 / 11500 \times 100 = 12.0\ \%", color=GREEN)
        c = MathTex(r"V_{shot} = 220 / (1 - 0.168) = 264.4\ \mathrm{m^3}", color=GREEN)
        d = MathTex(r"V_{shot} = 220 / (1 - 0.098) = 243.9\ \mathrm{m^3},\quad \Delta = 20.5\ \mathrm{m^3}", color=GREEN)
        self.add(VGroup(a, b, c, d).arrange(DOWN, buff=0.4, aligned_edge=LEFT).scale(0.85))


class Day09Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("반발률이 분사량을 바꾼다 (가상 예시)", 32).to_edge(UP, buff=0.3)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)

        # 위: 분사한 숏크리트 = 부착 + 반발
        W = 9.0
        x0 = -W / 2
        top = 1.6
        whole = Rectangle(width=W, height=0.7, color=SAND, fill_color=SAND, fill_opacity=0.25).move_to([0, top, 0])
        wl = T("분사량 S = 11,500 kg (5.0 m³ × 2,300 kg/m³)", 24).next_to(whole, UP, buff=0.12)
        self.play(FadeIn(whole), FadeIn(wl), run_time=0.8)
        rw = W * 0.12
        stick = Rectangle(width=W - rw, height=0.7, color=ICE, fill_color=ICE, fill_opacity=0.55).move_to([x0 + (W - rw) / 2, top, 0])
        reb = Rectangle(width=rw, height=0.7, color=RUST, fill_color=RUST, fill_opacity=0.85).move_to([x0 + W - rw / 2, top, 0])
        sl = T("부착 Y = 10,120 kg", 22, DEEP).move_to(stick)
        self.play(FadeIn(stick), FadeIn(reb), FadeIn(sl), run_time=0.9)
        rl = T("반발 R = 1,380 kg", 22, RUST).next_to(reb, DOWN, buff=0.12).shift(LEFT * 0.6)
        rr = M(r"RR = 1380/11500 \times 100 = 12.0\,\%", GOLD, 0.36).next_to(rl, DOWN, buff=0.12).shift(LEFT * 1.2)
        self.play(FadeIn(rl), Write(rr), run_time=1.0)
        self.wait(0.6)

        # 아래: 부착 소요 220 m³ 를 얻으려면 얼마나 쏘아야 하나
        base_y = -2.9
        sc = 2.1 / 264.4
        need = T("부착 소요 220 m³ 기준 분사량", 24).move_to([0, -0.15, 0])
        self.play(FadeIn(need), run_time=0.5)
        bars = []
        for i, (rate, vol, col, lab) in enumerate([(16.8, 264.4, RUST, "급결제 4 %: 반발률 16.8 %"),
                                                    (9.8, 243.9, ICE, "급결제 8 %: 반발률 9.8 %")]):
            x = -2.2 + i * 4.4
            h = vol * sc
            b = Rectangle(width=1.6, height=h, color=col, fill_color=col, fill_opacity=0.7)
            b.move_to([x, base_y + h / 2, 0])
            v = M(f"{vol}" + r"\ \mathrm{m^3}", col, 0.32).next_to(b, UP, buff=0.08)
            l = T(lab, 20, col).next_to(b, DOWN, buff=0.08)
            self.play(GrowFromEdge(b, DOWN), FadeIn(v), FadeIn(l), run_time=1.0)
            bars.append(b)
        ref = DashedLine([-3.6, base_y + 220 * sc, 0], [3.6, base_y + 220 * sc, 0], color=SAND, stroke_width=3)
        refl = T("부착 220", 18).next_to(ref, RIGHT, buff=0.1)
        self.play(Create(ref), FadeIn(refl), run_time=0.7)
        d = M(r"\Delta = 20.5\ \mathrm{m^3}", GOLD, 0.4).move_to([0, base_y + 1.2, 0])
        self.play(Write(d), run_time=0.7)
        self.wait(1.4)
