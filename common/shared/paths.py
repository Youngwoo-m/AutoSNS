"""AutoSNS 저장소 루트 경로 — shared/ 의 모듈들이 각자 계산하던 것을 한 곳에 둔다.

    from shared.paths import ROOT, ROOT_DIR     # ROOT 는 pathlib.Path, ROOT_DIR 는 같은 값의 문자열
sys.path 비교·os.path.join 처럼 문자열이 필요한 곳은 ROOT_DIR 를 쓴다.

`python3 shared/xxx.py` 처럼 직접 실행하는 모듈(axlock·diskguard·secret_get 등)은 sys.path 맨 앞이
shared/ 라서 `shared.paths` 를 못 찾으므로 각자 ROOT 를 계산한 채 둔다.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = str(ROOT)
