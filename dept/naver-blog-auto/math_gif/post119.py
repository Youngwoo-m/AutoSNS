"""티스토리 119번 온도균열지수: 수식 PNG 2장 (GIF 없음).
PNG : manim -qh -s -t --media_dir _media post119.py Post119F1 Post119F2
"""
from manim import *

GREEN = "#1F4E3D"


class Post119F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"I_{cr}=\frac{f_{sp}(t)}{\sigma_t(t)}", color=GREEN)
        b = MathTex(r"I_{cr}=\frac{15}{\Delta T_i}", color=GREEN)
        self.add(VGroup(a, b).arrange(RIGHT, buff=1.2).scale(1.3))


class Post119F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        a = MathTex(r"\Delta T_i=12\ ^\circ\mathrm{C}:\quad I_{cr}=\frac{15}{12}=1.25", color=GREEN)
        b = MathTex(r"I_{cr}\geq 1.5\ \Rightarrow\ \Delta T_i\leq \frac{15}{1.5}=10\ ^\circ\mathrm{C}", color=GREEN)
        self.add(VGroup(a, b).arrange(DOWN, buff=0.5).scale(1.1))
