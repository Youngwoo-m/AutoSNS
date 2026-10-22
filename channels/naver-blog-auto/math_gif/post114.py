"""티스토리 114번 수식 PNG (+GIF). PNG: manim -qh -s -t --media_dir _media post114.py Post114F1 ... (이후 투명 여백 자르기)"""
from manim import *

FONT_FILE = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf"
FONT = "Pretendard"
GREEN, DEEP, SAND, GOLD = "#1F4E3D", "#143528", "#E8DCC2", "#FFD27A"


def M(tex, color=SAND, height=0.6):
    return MathTex(tex, color=color).set(height=height)


def T(s, size=30, color=SAND):
    return Text(s, font=FONT, font_size=size, color=color)


class Post114F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"\delta=a_N\,\Delta N+a_E\,\Delta E", color=GREEN).scale(1.2))


class Post114F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"H=h-N", color=GREEN).scale(1.4))


