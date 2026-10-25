"""티스토리 7번: GNSS 높이 변환 수식 PNG (H = h - N, 계산 예)."""
from manim import *
GREEN = "#1F4E3D"

class Post7F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"h \approx H + N \;\;\Rightarrow\;\; H \approx h - N", color=GREEN).scale(1.1))

class Post7F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"H = h - N = 125.430\ \mathrm{m} - (+25.120\ \mathrm{m}) = 100.310\ \mathrm{m}", color=GREEN).scale(0.9))

class Post7F3(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(r"\sigma_H^{2} \approx \sigma_h^{2} + \sigma_N^{2}", color=GREEN).scale(1.1))
