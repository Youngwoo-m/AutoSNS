"""티스토리 120번(천문측량 시각 용어): 기본 관계식 PNG, 계산 예 PNG.
PNG : manim -qh -s -t --media_dir _media post120.py Post120F1 Post120F2  (이후 투명 여백 자르고 흰 바탕)
"""
from manim import *

GREEN = "#1F4E3D"


class Post120F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        eq = MathTex(
            r"\mathrm{LMT}&=\mathrm{GMT}+\lambda,\quad \mathrm{LST}=\mathrm{GST}+\lambda,\quad \mathrm{LHA}=\mathrm{GHA}+\lambda\\[6pt]"
            r"\mathrm{LHA}&=\mathrm{LST}-\alpha=\mathrm{GST}+\lambda-\alpha",
            color=GREEN,
        ).scale(0.9)
        self.add(eq)


class Post120F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        eq = MathTex(
            r"\mathrm{LST}&=1^{h}20^{m}+8^{h}30^{m}=9^{h}50^{m}\\[4pt]"
            r"\mathrm{LHA}&=9^{h}50^{m}-6^{h}45^{m}=3^{h}05^{m}=46^{\circ}15'\\[4pt]"
            r"\mathrm{GHA}&=1^{h}20^{m}-6^{h}45^{m}+24^{h}=18^{h}35^{m}=278^{\circ}45'\\[4pt]"
            r"\mathrm{GHA}+\lambda&=278^{\circ}45'+127^{\circ}30'-360^{\circ}=46^{\circ}15'=\mathrm{LHA}",
            color=GREEN,
        ).scale(0.8)
        self.add(eq)
