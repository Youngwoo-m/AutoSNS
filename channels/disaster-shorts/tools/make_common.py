"""인트로·아웃트로 아바타 영상(공통, 1회 제작)을 HeyGen 으로 만든다.

  python3 make_common.py            # common/intro_raw.mp4, common/outro_raw.mp4
내 목소리(Voicebox) wav → mp3 → HeyGen 오디오 자산 → 토킹포토 립싱크(가로 1920x1080).
요청 번호를 common/heygen_jobs.json 에 먼저 남겨, 도중에 끊겨도 다시 실행하면 이어 받는다
(크레딧은 요청 때 나간다).
"""
import json, os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
AUTOSNS = "/Volumes/USB256/devAPP/AutoSNS/channels/youtube-shorts-auto"
sys.path.insert(0, AUTOSNS); os.chdir(AUTOSNS)
import heygen_anchor as HG

COMMON = os.path.join(CFG["root"], "common")
JOBS = os.path.join(COMMON, "heygen_jobs.json")
TP = CFG["heygen"]["talking_photo_id"]


def _jobs():
    return json.load(open(JOBS)) if os.path.exists(JOBS) else {}


def make(kind):
    raw = os.path.join(COMMON, f"{kind}_raw.mp4")
    if os.path.exists(raw):
        print(f"{kind}: 이미 있음 → {raw}")
        return raw
    jobs = _jobs()
    if kind not in jobs:
        wav = os.path.join(COMMON, f"{kind}_voice.wav")
        mp3 = wav[:-4] + ".mp3"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", wav,
                        "-af", "loudnorm=I=-16", "-ar", "44100", "-b:a", "192k", mp3], check=True)
        aid = HG.upload_audio(mp3)
        res = HG.generate(TP, audio_asset_id=aid, wait=False, dimension={"width": 1920, "height": 1080},
                          meta={"title": f"재난 유형별 시리즈 {kind}"})
        jobs[kind] = res["video_id"]
        json.dump(jobs, open(JOBS, "w"), indent=1)
    got = HG.await_video(jobs[kind])
    shutil.copy(got["path"], raw)
    print(f"{kind}: 완료 → {raw}")
    return raw


if __name__ == "__main__":
    for k in (sys.argv[1:] or ["intro", "outro"]):
        make(k)
