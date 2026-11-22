"""디오라마 그림·클립을 게이트웨이로 만들지 로컬(FLUX 그림, Wan 2.2 영상)로 만들지 고른다(2026-11-23 사용자 지정).

매번 키별 월 할당(구매 크레딧 제외)을 조회해, 이번 요청을 감당할 키가 있으면 게이트웨이, 없으면 로컬을 쓴다.
할당은 매월 1일 다시 생기므로(다음: 2026-12-01) 그날부터 저절로 게이트웨이로 돌아간다.
고정하려면 환경변수 AX_DIORAMA_BACKEND=gateway|wan (기본 auto).
로컬 생성은 재난숏츠 wan_scene.py 의 검증된 설정(FLUX.1 schnell 그림, Wan 2.2 TI2V 5B 448x800 24fps)을 그대로 쓴다.

    python diorama_backend.py 39      # 39 크레딧짜리 요청이면 어느 쪽인지 보여 준다
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WAN_TOOLS = os.path.normpath(os.path.join(BASE_DIR, "..", "disaster-shorts", "tools"))


def key_for(cost, reserve):
    """(키 번호 또는 None, 이유). 월 할당이 cost+reserve 이상 남은 첫 키를 고른다."""
    mode = os.environ.get("AX_DIORAMA_BACKEND", "auto")
    if mode == "wan":
        return None, "AX_DIORAMA_BACKEND=wan"
    sys.path.insert(0, BASE_DIR)
    import veo_clips as V
    from common import load_config
    g = load_config()["llm_gateway"]
    keys = [g["api_key"]] + list(g.get("extra_keys", []))
    left = []
    for i, k in enumerate(keys):
        try:
            r = V.monthly_remaining(k)
        except Exception:  # noqa: BLE001
            r = 0.0
        left.append(round(r))
        if r >= cost + reserve:
            return i, f"게이트웨이 키{i} 월 할당 {round(r)} 남음"
    if mode == "gateway":
        return None, f"AX_DIORAMA_BACKEND=gateway 인데 월 할당 부족(키별 {left})"
    return None, f"월 할당 부족(키별 남음 {left}, 필요 {round(cost + reserve)}) → 로컬"


def wan():
    """재난숏츠 wan_scene 모듈(로컬 ComfyUI)."""
    if WAN_TOOLS not in sys.path:
        sys.path.insert(0, WAN_TOOLS)
    import wan_scene
    return wan_scene


_SIZES = {"9:16": (576, 1024), "1:1": (1024, 1024), "16:9": (1024, 576), "4:5": (832, 1024), "3:4": (768, 1024)}


def local_image(prompt, dst, aspect="9:16"):
    """FLUX.1 schnell 로 그림 한 장. 끝나면 그래픽카드 메모리를 비운다."""
    import random
    W = wan()
    W.SW, W.SH = _SIZES.get(aspect, _SIZES["9:16"])
    W.ensure_comfy()
    W.still(prompt, dst, random.randint(1, 2**31 - 1), free=True)
    return dst


def local_clip(prompt, seconds, dst):
    """FLUX 그림에서 시작하는 Wan 2.2 영상(448x800, 24fps). 끝나면 메모리를 비운다."""
    W = wan()
    try:
        W.run(prompt, seconds, dst)
    finally:
        W.free_vram()
    return dst


if __name__ == "__main__":
    c = float(sys.argv[1]) if len(sys.argv) > 1 else 39
    print(*key_for(c, 150))
