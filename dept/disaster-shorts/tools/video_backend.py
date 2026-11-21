"""장면 영상을 어디서 만들지 고른다(2026-11-21 사용자 지정).

게이트웨이 월 할당(구매 크레딧 제외)이 이번 편 장면을 모두 만들 만큼 남아 있으면 게이트웨이(veo_scene.py·image_scene.py),
아니면 로컬 Wan 2.2(wan_scene.py, 무료)를 쓴다. 할당은 매월 1일 다시 생기므로 자동으로 게이트웨이로 돌아간다.
config.json 의 "video_backend": "auto"(기본) | "gateway" | "wan" 으로 고정할 수 있다.

  python video_backend.py 3     # 8초 장면 3개를 만들 때 어느 쪽을 쓸지 보여 준다
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
_AXROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))).replace("\\", "/")
AUTOSNS = _AXROOT + "/channels/youtube-shorts-auto"


def clip_cost(seconds):
    return seconds / 4 * 200        # veo_clips._submit 과 같은 셈


def choose(clips, cfg=None):
    """clips: 만들 장면 영상의 초 목록. → ("gateway"|"wan", 이유)."""
    cfg = cfg or json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
    mode = cfg.get("video_backend", "auto")
    if mode in ("gateway", "wan"):
        return mode, f"config video_backend={mode}"
    if not clips:
        return "gateway", "만들 장면 없음"
    sys.path.insert(0, AUTOSNS)
    cwd = os.getcwd()
    try:
        os.chdir(AUTOSNS)
        import veo_clips as V
        from common import load_config
        g = load_config()["llm_gateway"]
        keys = [g["api_key"]] + list(g.get("extra_keys", []))
        # 장면마다 남은 할당이 넉넉한 키 하나를 쓰므로(veo_scene.py), 키별로 몇 장면을 맡을 수 있는지 센다
        left = []
        for k in keys:
            try:
                left.append(V.monthly_remaining(k))
            except Exception:  # noqa: BLE001
                left.append(0.0)
    except Exception as e:  # noqa: BLE001
        return "wan", f"게이트웨이 조회 실패({type(e).__name__}) → 로컬 Wan"
    finally:
        os.chdir(cwd)
    need = sorted((clip_cost(s) for s in clips), reverse=True)
    room = [x - V.MIN_MONTHLY for x in left]
    for c in need:                  # 큰 장면부터 남은 할당이 가장 많은 키에 배정
        i = max(range(len(room)), key=lambda j: room[j])
        if room[i] < c:
            return "wan", f"월 할당 부족(키별 남음 {[round(x) for x in left]}, 필요 {round(sum(need))}+예비 {V.MIN_MONTHLY}) → 로컬 Wan"
        room[i] -= c
    return "gateway", f"월 할당 충분(키별 남음 {[round(x) for x in left]}, 필요 {round(sum(need))})"


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    print(*choose([8] * n))
