"""티스토리 20번(GNSS OSR·SSR): 관측식 수식 PNG 1장.
PNG : manim -qh -s -t --media_dir _media post20.py Post20F1  (이후 투명 여백 자르고 흰 바탕)
"""
from manim import *

GREEN = "#1F4E3D"


class Post20F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        eq = MathTex(
            r"P&=\rho+c(\delta t_r-\delta t_s)+T+I+b_P+\varepsilon_P\\[4pt]"
            r"L&=\rho+c(\delta t_r-\delta t_s)+T-I+\lambda N+b_L+\varepsilon_L",
            color=GREEN,
        ).scale(0.9)
        self.add(eq)
