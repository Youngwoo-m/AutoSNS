"""티스토리 61번 수식 PNG (+GIF). PNG: manim -qh -s -t --media_dir _media post61.py Post61F1 ... (이후 투명 여백 자르기)"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A"


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Post61F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"\mathrm{GSD}=\frac{H\times p}{f}=\frac{H\,S}{f\,N_x}", color=GREEN).scale(1.1))


class Post61F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"\mathrm{GSD}=\frac{100\ \mathrm{m}\times 2.4\ \mu\mathrm{m}}{24\ \mathrm{mm}}=0.01\ \mathrm{m}=1\ \mathrm{cm}", color=GREEN).scale(0.95))


class Post61F3(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"\mathrm{RMSE}_E=\sqrt{\frac{\sum_{i=1}^{n} e_{E,i}^{2}}{n}}", color=GREEN).scale(1.1))


