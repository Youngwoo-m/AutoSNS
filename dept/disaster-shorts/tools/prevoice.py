"""다가오는 편의 대본을 쓰고 Voicebox 음성을 미리 만들어 둔다(시스템 부하가 적은 새벽에 launchd 로 실행).

  .venv/bin/python prevoice.py          # 대본 → 장면별 음성(voice/sceneN.wav)
  .venv/bin/python prevoice.py --check  # 무엇을 만들지 보여 주기만
weekly.py 는 대본·음성이 이미 있으면 건너뛰므로 저녁 제작 때는 영상·조립만 한다.
"""
import sys, os
sys.argv_orig = list(sys.argv)
import weekly


def main(check=False):
    e, ep = weekly.target()
    if not e:
        weekly.log("미리 만들 편 없음"); return
    weekly.log(f"대상: {e['date']} {e['type']}")
    if check:
        return
    if not os.path.exists("/Volumes/USB256"):
        raise RuntimeError("USB256 이 연결되어 있지 않습니다")
    weekly.step("대본", [weekly.PY, "write_script.py", e["date"]])
    weekly.step("음성(미리)", [weekly.PY, "voice.py", "--episode", ep])


if __name__ == "__main__":
    main("--check" in sys.argv)
