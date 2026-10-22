"""측량 하루 한 문제 숏츠를 Remotion(src/survey-short)으로 렌더한다 — 클로드 자동 작업 survey-daily 용.

    python3 render_survey_short.py props.json short.mp4

props.json (그림·음성은 절대 경로로 적는다 — 이 스크립트가 임시 public 폴더로 모아 렌더한다):
  {"exam": "측량및지형공간정보기술사", "field": "측지학·좌표계 (학습용 분류) · 11일차",
   "source": "2023년 제131회 1교시 1번 기출", "footer": "자세한 답안·따라쓰기 PDF → 재난안전과 GeoAI 블로그",
   "disclosure": "학습용 예시 · AI 생성 그림 · AI 합성 음성(본인 목소리 복제)",
   "voice": "/abs/voice.wav (선택: 영상 전체 음성 한 개. 장면별로 나눴으면 scenes[].audio)",
   "scenes": [{"title": "…", "caption": "…", "image": "/abs/diorama1.png", "kind": "diorama",
               "audio": "/abs/voice-1.wav", "seconds": 4.2}, …]}
  kind 는 diorama | diagram | clip. clip 은 image 칸에 Manim 등으로 만든 mp4(980x900, 30fps, 무음)를 적는다.
  overlay(선택)는 장면 위에 얹는 투명 webm(HyperFrames 훅 제목 등, 1080x1920, 알파 포함).
  (Manim 샘플: manim/error_propagation.py ErrorPropagationBox — 디오라마 2~3장 규칙에는 세지 않는다)

지키는 것(CLAUDE.md 영상 지침·2026-10-17 숏츠 지침): 디오라마 장면 2~3장, 1080×1920, 전체 20.0초 이하.
결과는 마지막 줄 JSON: {"status": "ok"|"error", "video", "seconds", "size", "frames": [장면별 확인용 jpg], "message"}
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
MAX_SECONDS = 20.0


def out(status, **kw):
    print(json.dumps({"status": status, **kw}, ensure_ascii=False))
    return 0 if status == "ok" else 1


def main():
    if len(sys.argv) != 3:
        return out("error", message="사용법: render_survey_short.py props.json short.mp4")
    src, video = sys.argv[1], os.path.abspath(sys.argv[2])
    props = json.load(open(src, encoding="utf-8"))
    scenes = props.get("scenes") or []
    dio = sum(1 for s in scenes if s.get("kind") == "diorama" and s.get("image"))
    total = sum(round(float(s["seconds"]) * 30) for s in scenes) / 30
    problems = []
    if not 2 <= dio <= 3:
        problems.append(f"디오라마 장면이 {dio}장입니다 — 2~3장 넣을 것")
    if total > MAX_SECONDS:
        problems.append(f"장면 길이 합 {total:.2f}초 > {MAX_SECONDS}초 — 대본·장면을 줄일 것(배속 금지)")
    if props.get("voice") and not os.path.isfile(props["voice"]):
        problems.append(f"voice 파일이 없습니다: {props['voice']}")
    for i, s in enumerate(scenes, 1):
        for k in ("image", "audio", "overlay"):
            if s.get(k) and not os.path.isfile(s[k]):
                problems.append(f"장면 {i} {k} 파일이 없습니다: {s[k]}")
    if problems:
        return out("error", message=" / ".join(problems))

    from shared.fonts import DISPLAY, font_path
    with tempfile.TemporaryDirectory() as pub:
        shutil.copy(font_path(DISPLAY), os.path.join(pub, "Pretendard-Bold.otf"))
        if props.get("voice"):
            name = "voice" + os.path.splitext(props["voice"])[1]
            shutil.copy(props["voice"], os.path.join(pub, name))
            props["voice"] = name
        for i, s in enumerate(scenes, 1):
            for k in ("image", "audio", "overlay"):
                if s.get(k):
                    name = f"s{i}-{k}{os.path.splitext(s[k])[1]}"
                    shutil.copy(s[k], os.path.join(pub, name))
                    s[k] = name
        pj = os.path.join(pub, "_props.json")
        json.dump(props, open(pj, "w", encoding="utf-8"), ensure_ascii=False)
        r = subprocess.run(["npx", "remotion", "render", "src/survey-short/index.ts", "SurveyShort", video,
                            f"--props={pj}", f"--public-dir={pub}", "--log=error"],
                           cwd=HERE, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.isfile(video):
            return out("error", message=f"Remotion 렌더 실패: {(r.stderr or r.stdout).strip()[-400:]}")

    p = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height:format=duration", "-of", "json", video], capture_output=True, text=True)
    j = json.loads(p.stdout)
    sec = float(j["format"]["duration"])
    w, h = j["streams"][0]["width"], j["streams"][0]["height"]
    # 장면마다 가운데 프레임을 뽑아 눈으로 확인할 수 있게 한다
    frames, t = [], 0.0
    for i, s in enumerate(scenes, 1):
        mid = t + float(s["seconds"]) / 2
        t += float(s["seconds"])
        f = os.path.splitext(video)[0] + f"-frame{i}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{mid:.2f}", "-i", video, "-frames:v", "1", f])
        frames.append(f)
    if sec > MAX_SECONDS or (w, h) != (1080, 1920):
        return out("error", video=video, seconds=round(sec, 2), size=f"{w}x{h}", frames=frames,
                   message="렌더 결과가 20.0초 이하 1080×1920 이 아닙니다")
    return out("ok", video=video, seconds=round(sec, 2), size=f"{w}x{h}", frames=frames)


if __name__ == "__main__":
    sys.exit(main())
