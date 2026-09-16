"""대본으로 유튜브 자막(SRT)을 만들어 올린다.

왜: 자동자막은 고유명사·지명(제천·방재안전직 등)을 자주 틀리고, 정확한 자막은
    검색 색인·답변형 검색·생성형 AI 요약이 내용을 읽는 통로가 된다. 대본이 이미
    있으므로 추가 비용 없이 정확한 자막을 붙일 수 있다.

타이밍:
  - 장면별 TTS mp3 가 있으면(카드 영상) 그 길이를 그대로 쓴다 → 정확.
  - 아나운서 영상은 하나의 음성이라 장면 음성이 없다. 이때는 영상 길이를
    장면별 글자 수 비율로 나눈다(연속 발화라 오차가 작다).

업로드: captions().insert — youtube.force-ssl 스코프 필요(이미 보유).
       같은 언어 자막이 이미 있으면 건너뛴다(중복 방지).
"""
import os
import re
import subprocess
import sys

import imageio_ffmpeg
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from common import BASE_DIR, log
from youtube_upload import _creds

LEAD = 0.15          # 자막을 아주 살짝 먼저 띄운다(읽는 시간 확보)
MIN_DUR = 1.2        # 한 자막의 최소 노출 시간(초)


def _duration(path):
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    out = subprocess.run([ff, "-i", path], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", out)
    if not m:
        return 0.0
    h, mm, ss = m.groups()
    return int(h) * 3600 + int(mm) * 60 + float(ss)


def _scene_durations(data, total):
    """장면별 길이(초). TTS mp3 가 있으면 실제 길이, 없으면 글자 수 비율."""
    scenes = data.get("scenes") or []
    stamp = data.get("stamp") or ""
    audio_dir = os.path.join(BASE_DIR, "posts", f"audio_{stamp}")
    mp3s = [os.path.join(audio_dir, f"{i+1:02d}.mp3") for i in range(len(scenes))]
    if all(os.path.exists(p) for p in mp3s) and mp3s:
        durs = [_duration(p) for p in mp3s]
        if all(d > 0 for d in durs):
            return durs
    weights = [max(len((s.get("narration") or "").strip()), 1) for s in scenes]
    tw = sum(weights)
    return [total * w / tw for w in weights]


def _ts(sec):
    sec = max(sec, 0)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)):03d}"


def build_srt(data, video_path=None):
    """대본 → SRT 문자열."""
    video = video_path or data.get("video")
    total = _duration(video) if video and os.path.exists(video) else 0.0
    scenes = data.get("scenes") or []
    if not scenes:
        return ""
    if total <= 0:                       # 영상이 없으면 낭독 속도로 추정(초당 6자)
        total = sum(len(s.get("narration") or "") for s in scenes) / 6.0
    durs = _scene_durations(data, total)
    out, t = [], 0.0
    for i, (sc, d) in enumerate(zip(scenes, durs), start=1):
        text = (sc.get("narration") or "").strip()
        if not text:
            t += d
            continue
        start = max(t - LEAD, 0)
        end = max(t + d, start + MIN_DUR)
        # 한 줄이 길면 문장 단위로 두 줄까지 접는다(세로 영상 가독성)
        if len(text) > 22:
            mid = text.rfind(" ", 0, len(text) // 2 + 6) or len(text) // 2
            text = text[:mid].strip() + "\n" + text[mid:].strip()
        out.append(f"{i}\n{_ts(start)} --> {_ts(end)}\n{text}\n")
        t += d
    return "\n".join(out)


def upload_caption(video_id, srt_text, language="ko", name="한국어(대본)", token_path=None):
    """SRT 를 유튜브 자막으로 올린다. 같은 언어 자막이 있으면 건너뛴다."""
    yt = build("youtube", "v3", credentials=_creds(token_path), cache_discovery=False)
    try:
        have = yt.captions().list(part="snippet", videoId=video_id).execute().get("items", [])
        # trackKind='asr' 은 유튜브가 만든 자동자막이다. 우리가 올린 정확한 자막으로
        # 덮어쓰는 게 목적이므로, 직접 올린 트랙이 있을 때만 건너뛴다.
        if any(c["snippet"]["language"] == language
               and c["snippet"].get("trackKind") != "asr" for c in have):
            log(f"자막 이미 있음 → 건너뜀({video_id})")
            return {"status": "exists"}
    except Exception as e:
        log(f"자막 목록 조회 실패({type(e).__name__}) — 업로드는 시도합니다")
    tmp = os.path.join(BASE_DIR, "posts", f"_caption_{video_id}.srt")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(srt_text)
    try:
        yt.captions().insert(
            part="snippet",
            body={"snippet": {"videoId": video_id, "language": language,
                              "name": name, "isDraft": False}},
            media_body=MediaFileUpload(tmp, mimetype="application/octet-stream")).execute()
        log(f"자막 업로드 완료({video_id})")
        return {"status": "uploaded"}
    except Exception as e:
        log(f"자막 업로드 실패({video_id}): {type(e).__name__}: {str(e)[:120]}")
        return {"error": str(e)[:200]}
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def attach(data, video_id=None, token_path=None):
    """발행 파이프라인에서 호출 — 대본으로 자막을 만들어 올린다(실패해도 무해).

    token_path: 학과 채널이 아닌 다른 채널(예: 개인 GeoAI 채널)에 붙일 때 그 토큰."""
    vid = video_id or data.get("video_id")
    if not vid:
        return {"skipped": "no video id"}
    srt = build_srt(data)
    if not srt.strip():
        return {"skipped": "no script"}
    return upload_caption(vid, srt, token_path=token_path)


if __name__ == "__main__":
    import json
    path = sys.argv[1]
    d = json.load(open(path, encoding="utf-8"))
    print(build_srt(d))
