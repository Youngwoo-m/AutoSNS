"""옛 경로 호환 — 실제 구현은 shared/stock/photo.py. 이 이름으로 import 하면 같은 모듈 객체가 돌아온다."""
import importlib
import sys

sys.modules[__name__] = importlib.import_module("shared.stock.photo")
