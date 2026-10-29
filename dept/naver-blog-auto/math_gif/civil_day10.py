"""토목 하루 한 문제 10일차 하천 제방 파괴원인과 방지대책: 수식 PNG 2장 + 파이핑 검토 GIF.
GIF : ./render.sh civil_day10.py Day10Gif
PNG : manim -qh -s -t --media_dir _media civil_day10.py Day10F1 Day10F2
값은 본문 가상 예시(Gs 2.65, e 0.65, 유출부 국부 동수경사 0.30 → 대책 후 0.20)만 쓴다.
"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD, ICE, RUST, SOIL = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A", "#9FD3E6", "#E08A6A", "#8C7A5B"


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Day10F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"i_{c} = \frac{G_{s} - 1}{1 + e}", color=GREEN)
        b = MathTex(r"F_{s} = \frac{i_{c}}{i_{exit}}", color=GREEN)
        self.add(VGroup(a, b).arrange(RIGHT, buff=1.2).scale(1.0))


class Day10F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"i_{c} = (2.65 - 1)/(1 + 0.65) = 1.65/1.65 = 1.00", color=GREEN)
        b = MathTex(r"F_{s} = 1.00 / 0.30 = 3.33\quad(3.0 \le F_{s} < 4.0)", color=GREEN)
        c = MathTex(r"F_{s} = 1.00 / 0.20 = 5.00\quad(F_{s} \ge 4.0)", color=GREEN)
        self.add(VGroup(a, b, c).arrange(DOWN, buff=0.4, aligned_edge=LEFT).scale(0.85))


class Day10Gif(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self._build()

    def _build(self):
        self.camera.background_color = DEEP
        title = T("홍수 때 제방 밑 침투와 파이핑 검토 (가상 예시)", 30).to_edge(UP, buff=0.3)
        self.play(FadeIn(title, shift=DOWN * 0.2), run_time=0.6)

        # 단면: 기초지반 + 사다리꼴 제체, 왼쪽 제외지(하천), 오른쪽 제내지
        gy = -0.4
        ground = Rectangle(width=12, height=1.6, color=SOIL, fill_color=SOIL, fill_opacity=0.45, stroke_width=0).move_to([0, gy - 0.8, 0])
        levee = Polygon([-3.0, gy, 0], [-0.8, gy + 1.6, 0], [0.8, gy + 1.6, 0], [3.0, gy, 0],
                        color=SAND, fill_color=SOIL, fill_opacity=0.85, stroke_width=3)
        lo = T("제외지(하천)", 20).move_to([-4.8, gy + 1.9, 0])
        li = T("제내지", 20).move_to([4.8, gy + 0.4, 0])
        self.play(FadeIn(ground), Create(levee), FadeIn(lo), FadeIn(li), run_time=1.0)

        wl = gy + 1.25
        water = Polygon([-6, gy, 0], [-3.0, gy, 0], [-3.0 + 2.2 * 1.25 / 1.6, wl, 0], [-6, wl, 0],
                        color=ICE, fill_color=ICE, fill_opacity=0.55, stroke_width=0)
        wtag = T("홍수위 상승", 20, ICE).move_to([-4.6, wl + 0.3, 0])
        self.play(FadeIn(water), FadeIn(wtag), run_time=0.8)

        # 기초지반 속 침투 화살표 → 제내지 비탈끝 유출(보일링)
        path = [[-4.2, gy - 0.35, 0], [-1.5, gy - 0.9, 0], [1.5, gy - 0.9, 0], [3.4, gy - 0.35, 0], [3.7, gy + 0.05, 0]]
        arrows = VGroup(*[Arrow(path[k], path[k + 1], buff=0.05, color=GOLD, stroke_width=5, max_tip_length_to_length_ratio=0.15)
                          for k in range(4)])
        self.play(LaggedStart(*[GrowArrow(a) for a in arrows], lag_ratio=0.3), run_time=1.4)
        boil = VGroup(*[Circle(radius=0.07 + 0.04 * k, color=GOLD).move_to([3.75, gy + 0.12 + 0.1 * k, 0]) for k in range(3)])
        btag = T("유출부 국부 동수경사 i = 0.30", 20, GOLD).move_to([3.6, gy - 1.6, 0])
        self.play(FadeIn(boil), FadeIn(btag), run_time=0.8)
        self.wait(0.4)

        # 아래쪽 계산
        eq1 = M(r"i_c = \frac{2.65-1}{1+0.65} = 1.00", SAND, 0.55).move_to([-3.3, -3.0, 0])
        self.play(Write(eq1), run_time=0.9)
        eq2 = M(r"F_s = 1.00/0.30 = 3.33", RUST, 0.42).move_to([2.6, -2.75, 0])
        self.play(Write(eq2), run_time=0.8)
        self.wait(0.6)

        # 대책: 앞비탈 기슭 차수벽 → 침투경로 길어짐, 동수경사 낮아짐
        wall = Rectangle(width=0.18, height=1.0, color=ICE, fill_color=ICE, fill_opacity=0.9).move_to([-2.6, gy - 0.5, 0])
        wtag2 = T("앞비탈 기슭 차수벽", 18, ICE).move_to([-4.6, gy - 0.25, 0])
        path2 = [[-4.2, gy - 0.35, 0], [-2.6, gy - 1.3, 0], [1.5, gy - 1.3, 0], [3.4, gy - 0.35, 0], [3.7, gy + 0.05, 0]]
        arrows2 = VGroup(*[Arrow(path2[k], path2[k + 1], buff=0.05, color=ICE, stroke_width=5, max_tip_length_to_length_ratio=0.15)
                           for k in range(4)])
        self.play(FadeIn(wall), FadeIn(wtag2), ReplacementTransform(arrows, arrows2), run_time=1.0)
        btag2 = T("대책 후 가정 i = 0.20", 20, ICE).move_to(btag)
        eq3 = M(r"F_s = 1.00/0.20 = 5.00", ICE, 0.42).move_to([2.6, -3.35, 0])
        self.play(Transform(btag, btag2), FadeOut(boil), Write(eq3), run_time=1.0)
        self.wait(1.6)
