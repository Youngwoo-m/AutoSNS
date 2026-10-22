"""블로거 토목시공기술사 하루 한 문제 4편(다짐·온도균열·SPT·말뚝재하시험)의 수식 GIF·수식 이미지 장면.
렌더: math_gif/render.sh blogger_civil.py GCompaction  (GIF)  /  수식 PNG 는 manim -s --transparent (README 참고)
"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, INK, GOLD = "#1F4E3D", "#143528", "#E8DCC2", "#2B2A26", "#FFD27A"


def M(tex, color=SAND, height=0.7):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=28, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Base(Scene):
    def construct(self):
        with register_font(FONT_FILE):
            self.camera.background_color = DEEP
            self.build()

    def head(self, s):
        t = T(s, 36).to_edge(UP, buff=0.35)
        self.play(FadeIn(t, shift=DOWN * 0.2), run_time=0.5)
        return t

    def step(self, label, tex, y, color=SAND, h=0.8):
        lab = T(label, 24, GOLD).move_to([-4.6, y, 0])
        lab.set_x(-5.3 + lab.width / 2)
        eq = MathTex(tex, color=color).scale(1.05 if color == GOLD else 0.95)
        if eq.width > 8.4:
            eq.set(width=8.4)
        eq.move_to([-3.5 + eq.width / 2, y, 0])
        self.play(FadeIn(lab, shift=RIGHT * 0.2), Write(eq), run_time=1.0)
        return eq


class GCompaction(Base):
    def build(self):
        self.head("다짐도 계산")
        self.step("건조밀도", r"\rho_d = \frac{\rho}{1+w}", 1.5)
        self.step("현장 값", r"\frac{2.016}{1+0.12} = 1.800\ \mathrm{Mg/m^3}", 0.15)
        self.step("다짐도", r"R_c = \frac{\rho_{d}}{\rho_{d,max}}\times 100", -1.2)
        r = self.step("결과", r"\frac{1.800}{1.900}\times 100 = 94.7\%", -2.5, GOLD, 0.85)
        self.play(Indicate(r, color=GOLD, scale_factor=1.05), run_time=0.9)
        self.wait(0.8)


class GSPT(Base):
    def build(self):
        self.head("SPT N값 보정 순서")
        self.step("측정 N", r"N = 18", 1.7)
        self.step("에너지", r"N_{60} = \frac{ER}{60}\,N = \frac{80}{60}\times 18 = 24.0", 0.45)
        self.step("상재압", r"C_N = 0.77\log_{10}\frac{20}{\sigma'_v} = 1.234", -0.85)
        r = self.step("최종", r"(N_1)_{60} = C_N\,N_{60} = 29.6 \approx 30", -2.2, GOLD, 0.8)
        self.play(Indicate(r, color=GOLD, scale_factor=1.05), run_time=0.9)
        self.wait(0.8)


class GThermal(Base):
    def build(self):
        self.head("온도균열지수")
        self.step("정의", r"I_{cr} = \frac{f_{sp}(t)}{\sigma_t(t)}", 1.5)
        self.step("간이식", r"I_{cr} = \frac{15}{\Delta T}", 0.0)
        self.step("ΔT = 12 °C", r"I_{cr} = \frac{15}{12} = 1.25", -1.3)
        r = self.step("목표 1.5", r"\Delta T_i \leq \frac{15}{1.5} = 10\,^{\circ}\mathrm{C}", -2.6, GOLD, 0.85)
        self.play(Indicate(r, color=GOLD, scale_factor=1.05), run_time=0.9)
        self.wait(0.8)


class GPile(Base):
    def build(self):
        self.head("Davisson 한계 침하량")
        self.step("한계선", r"s_{lim} = \frac{QL}{AE} + \left(4 + \frac{D}{120}\right)", 1.5, SAND, 0.9)
        self.step("단면적", r"A = \frac{\pi}{4}(508^2-484^2) \approx 18{,}699\ \mathrm{mm^2}", 0.15, SAND, 0.7)
        self.step("Q=2,500", r"s_{lim} = 13.37 + 8.23 = 21.60\ \mathrm{mm}", -1.1, SAND, 0.7)
        r = self.step("Q=3,000", r"s_{lim} = 16.04 + 8.23 = 24.28\ \mathrm{mm}", -2.3, GOLD, 0.7)
        self.play(Indicate(r, color=GOLD, scale_factor=1.05), run_time=0.9)
        self.wait(0.8)


class Formula(Scene):
    """수식 이미지(투명 배경, 짙은 글자). TEXS 환경변수 없이 클래스별로 아래 서브클래스를 쓴다."""
    LINES = []

    def construct(self):
        g = VGroup(*[MathTex(t, color=INK) for t in self.LINES]).arrange(DOWN, aligned_edge=LEFT, buff=0.35)
        self.add(g)


class FCompaction(Formula):
    LINES = [r"\rho_d = \dfrac{\rho}{1+w}", r"R_c\,(\%) = \dfrac{\rho_d}{\rho_{d,max}}\times 100",
             r"\rho_d = \dfrac{2.016}{1+0.12} = 1.800,\quad R_c = \dfrac{1.800}{1.900}\times100 = 94.7\%"]


class FSPT(Formula):
    LINES = [r"N_{60} = \dfrac{ER}{60\%}\,N", r"(N_1)_{60} = C_N\,N_{60},\quad C_N = 0.77\log_{10}\dfrac{20}{\sigma'_v}\ (\leq 2.0,\ \sigma'_v:\ \mathrm{tsf})",
             r"N' = 15 + \dfrac{1}{2}(N-15),\quad N>15"]


class FThermal(Formula):
    LINES = [r"I_{cr} = \dfrac{f_{sp}(t)}{\sigma_t(t)}", r"I_{cr} = \dfrac{15}{\Delta T}",
             r"\Delta T_i \leq \dfrac{15}{1.5} = 10\,^\circ\mathrm{C}"]


class FPile(Formula):
    LINES = [r"s_{lim} = \dfrac{QL}{AE} + \left(4 + \dfrac{D}{120}\right)\ [\mathrm{mm}]",
             r"A = \dfrac{\pi}{4}\left(D^2 - d^2\right) \approx 18{,}699\ \mathrm{mm^2}"]
