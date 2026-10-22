"""티스토리 34번: GNSS 코드 의사거리·반송파 위상 단순화 관측식, 이중차분 수식 PNG."""
from manim import *
GREEN = "#1F4E3D"

class Post34F1(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(
            r"P &= \rho + c(\delta t_r - \delta t^{s}) + T + I + \varepsilon_P \\[6pt]"
            r"L = \lambda\varphi &= \rho + c(\delta t_r - \delta t^{s}) + T - I + \lambda N + \varepsilon_L",
            color=GREEN).scale(0.8))

class Post34F2(Scene):
    def construct(self):
        self.camera.background_color = "#00000000"
        self.add(MathTex(
            r"\nabla\Delta L &= [L_{B}^{i}-L_{A}^{i}] - [L_{B}^{j}-L_{A}^{j}] \\[6pt]"
            r"&= \nabla\Delta\rho + \nabla\Delta T - \nabla\Delta I + \lambda\nabla\Delta N + \nabla\Delta\varepsilon",
            color=GREEN).scale(0.8))
