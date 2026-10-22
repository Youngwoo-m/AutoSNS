"""티스토리 123번 SPT N값 보정: 수식 PNG 2장 (GIF 없음).
PNG : manim -qh -s -t --media_dir _media post123.py Post123F1 Post123F2
"""
from manim import *

GREEN = "#1F4E3D"


class Post123F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"N_{60}=\frac{ER}{60\%}\,N", color=GREEN)
        b = MathTex(r"(N_1)_{60}=C_N\,N_{60},\quad C_N=0.77\log_{10}\frac{20}{\sigma'_v}<2.0\ \ (\sigma'_v:\ \mathrm{tsf})", color=GREEN)
        self.add(VGroup(a, b).arrange(DOWN, buff=0.6).scale(1.0))


class Post123F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"N_{60}=\frac{80}{60}\times 18=24.0", color=GREEN)
        b = MathTex(r"C_N=0.77\log_{10}\frac{20}{0.5}=0.77\times1.602=1.234", color=GREEN)
        c = MathTex(r"(N_1)_{60}=1.234\times 24.0=29.6\approx 30", color=GREEN)
        self.add(VGroup(a, b, c).arrange(DOWN, buff=0.45).scale(1.0))
