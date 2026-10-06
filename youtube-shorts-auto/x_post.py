"""X(트위터)에 숏폼 영상을 직접 첨부해 올린다 — X API v2, OAuth 1.0a 사용자 키.

2026-02 부터 X API 는 무료 등급이 없고 쓴 만큼 낸다(선불 크레딧): 글 1건 약 $0.015,
링크가 든 글은 약 $0.20. 그래서 유튜브 링크 대신 **영상을 직접 첨부**한다(10/6 결정) —
X 에서는 링크 글보다 영상 글이 더 멀리 퍼지기도 한다. 링크는 넣지 않는다.

절차(공식 문서 docs.x.com 'media upload chunked', 2026-10-06 확인):
  1) POST /2/media/upload/initialize   {media_type, total_bytes, media_category}
  2) POST /2/media/upload/{id}/append  multipart: segment_index, media(≤5MB)
  3) POST /2/media/upload/{id}/finalize
  4) GET  /2/media/upload?command=STATUS&media_id=…  (processing_info 가 있으면 끝날 때까지)
  5) POST /2/tweets  {text, media: {media_ids: [id]}}

인증(git 제외 파일):
  - OAuth 2.0(쓰는 방식): config.json "x": {"enabled", "username", "oauth2_client_id",
    "oauth2_client_secret"} + x_token.json(접근·갱신 토큰, 2시간마다 자동 갱신). 권한은
    tweet.read tweet.write users.read media.write offline.access 만(2026-10-06 승인).
  - 또는 OAuth 1.0a 키 4개: "api_key", "api_secret", "access_token", "access_secret"

부가 채널이라 실패해도 예외를 올리지 않는다 — 결과 dict 만 돌려준다(유튜브 발행은 그대로).
수동 시험:  python x_post.py <영상.mp4> "글"        (기본 dry-run: 업로드 없이 본문만 점검)
           python x_post.py <영상.mp4> "글" --go   (실제 게시)
"""
import json
import os
import re
import sys
import time

from common import load_config, log

API = "https://api.x.com/2"
CHUNK = 4 * 1024 * 1024          # 문서 상한 5MB 보다 조금 작게
MAX_WEIGHT = 280                 # X 글자 수(가중치) 상한


def _weight(text):
    """X 가 세는 글자 수. 한글·한자·가나 등은 2, 나머지는 1(URL 은 넣지 않는다)."""
    n = 0
    for ch in text:
        o = ord(ch)
        n += 2 if (0x1100 <= o <= 0x11FF or 0x2E80 <= o <= 0xA4CF or 0xAC00 <= o <= 0xD7AF
                   or 0xF900 <= o <= 0xFAFF or 0xFE30 <= o <= 0xFE4F or 0xFF00 <= o <= 0xFF60
                   or 0x1F300 <= o <= 0x1FAFF) else 1
    return n


def _fit(text, limit=MAX_WEIGHT):
    """가중치 상한 안으로 자른다(문장·줄 단위로 덜어 내고, 그래도 넘으면 글자 단위)."""
    text = text.strip()
    if _weight(text) <= limit:
        return text
    lines = text.split("\n")
    while len(lines) > 1 and _weight("\n".join(lines)) > limit:
        lines.pop(-2 if lines[-1].startswith("#") and len(lines) > 2 else -1)
    text = "\n".join(lines)
    while _weight(text) > limit - 1:
        text = text[:-1]
    return text.rstrip() + ("…" if _weight(text) < limit else "")


def compose(title, summary="", tags=()):
    """제목 + 요약 한 문장 + 해시태그 2~3개. 링크는 넣지 않는다(링크 글은 13배 비싸다)."""
    title = re.sub(r"\s*#\S+", "", title or "").strip()
    title = re.sub(r"\s*\|\s*세명대 재난안전학과.*$", "", title)       # 시리즈 꼬리표 정리
    tag_line = " ".join("#" + t.replace(" ", "") for t in list(tags)
                        if t and t.lower() != "shorts")
    tag_line = " ".join(tag_line.split()[:3])
    parts = [title, (summary or "").strip(), tag_line]
    return _fit("\n\n".join(p for p in parts if p))


TOKEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "x_token.json")


def _refresh_token(x, tok):
    """OAuth 2.0 접근 토큰(2시간)을 갱신 토큰으로 새로 받는다. 갱신 토큰도 매번 바뀌니 함께 저장한다
    — 저장을 놓치면 다음 갱신이 실패해 다시 브라우저 승인을 받아야 한다."""
    import requests
    r = requests.post(f"{API}/oauth2/token", data={
        "grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
        "client_id": x["oauth2_client_id"]},
        auth=(x["oauth2_client_id"], x["oauth2_client_secret"]), timeout=30)
    j = r.json() if r.content else {}
    if r.status_code >= 300 or not j.get("access_token"):
        raise RuntimeError(f"X 토큰 갱신 실패 http {r.status_code}: "
                           f"{ {k: v for k, v in j.items() if 'token' not in k} } — 브라우저 승인을 다시 받아야 함")
    tok = {"access_token": j["access_token"], "refresh_token": j.get("refresh_token") or tok["refresh_token"],
           "scope": j.get("scope", tok.get("scope", "")), "expires_in": j.get("expires_in", 7200),
           "saved_at": int(time.time())}
    tmp = TOKEN_PATH + ".part"
    with open(tmp, "w") as f:
        json.dump(tok, f, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, TOKEN_PATH)
    return tok


def _session(cfg):
    """OAuth 2.0 사용자 토큰(x_token.json, 자동 갱신)이 있으면 그것을, 없으면 OAuth 1.0a 키 4개를 쓴다."""
    x = cfg.get("x") or {}
    if os.path.exists(TOKEN_PATH) and x.get("oauth2_client_id"):
        import requests
        tok = json.load(open(TOKEN_PATH))
        if time.time() > tok.get("saved_at", 0) + int(tok.get("expires_in") or 7200) - 300:
            tok = _refresh_token(x, tok)
        s = requests.Session()
        s.headers["Authorization"] = f"Bearer {tok['access_token']}"
        return s
    from requests_oauthlib import OAuth1Session
    keys = [x.get(k) for k in ("api_key", "api_secret", "access_token", "access_secret")]
    if not all(keys):
        raise RuntimeError("X 인증 정보가 없습니다(x_token.json + oauth2_client_id, 또는 OAuth 1.0a 키 4개).")
    return OAuth1Session(*keys)


def _check(r, what):
    if r.status_code >= 300:
        raise RuntimeError(f"{what} 실패 http {r.status_code}: {r.text[:300]}")
    return r.json() if r.content else {}


def _upload_video(s, path):
    size = os.path.getsize(path)
    j = _check(s.post(f"{API}/media/upload/initialize", json={
        "media_type": "video/mp4", "total_bytes": size, "media_category": "tweet_video"}),
        "업로드 시작")
    mid = (j.get("data") or j).get("id") or (j.get("data") or j).get("media_id")
    if not mid:
        raise RuntimeError(f"media_id 없음: {str(j)[:200]}")
    with open(path, "rb") as f:
        seg = 0
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            _check(s.post(f"{API}/media/upload/{mid}/append",
                          data={"segment_index": str(seg)},
                          files={"media": ("chunk.mp4", chunk, "application/octet-stream")}),
                   f"조각 {seg} 올리기")
            seg += 1
    j = _check(s.post(f"{API}/media/upload/{mid}/finalize"), "업로드 마무리")
    info = (j.get("data") or j).get("processing_info")
    waited = 0
    while info and info.get("state") in ("pending", "in_progress") and waited < 300:
        wait = int(info.get("check_after_secs") or 5)
        time.sleep(wait)
        waited += wait
        j = _check(s.get(f"{API}/media/upload", params={"command": "STATUS", "media_id": mid}),
                   "처리 상태 확인")
        info = (j.get("data") or j).get("processing_info")
    if info and info.get("state") != "succeeded":
        raise RuntimeError(f"영상 처리 실패/시간 초과: {info}")
    return mid


def _x_ready(video):
    """X 가 받는 형식(H.264 + AAC, yuv420p)이 아니면 H.264 로 바꾼 사본 경로를, 맞으면 원본을 준다.

    유튜브에서 받은 영상 상당수가 AV1 이라 X 처리 단계가 99% 에서 'failed' 로 끝났다
    (2026-10-06 학과 소개 1편). 우리가 만든 숏폼은 원래 H.264 라 그대로 간다."""
    import subprocess
    ff = "/usr/local/bin/ffmpeg" if os.path.exists("/usr/local/bin/ffmpeg") else "ffmpeg"
    info = subprocess.run([ff, "-hide_banner", "-i", video], capture_output=True, text=True).stderr
    vline = next((l for l in info.splitlines() if "Video:" in l), "")
    aline = next((l for l in info.splitlines() if "Audio:" in l), "")
    # yuvj420p(전체 범위)도 X 가 받는다 — 우리 숏폼이 이 형식이고 시험 게시가 정상이었다.
    if " h264 " in vline and ("yuv420p" in vline or "yuvj420p" in vline) and (not aline or " aac " in aline):
        return video
    out = os.path.splitext(video)[0] + ".x264.mp4"
    if not (os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(video)):
        r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-i", video,
                            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                            "-profile:v", "high", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                            "-movflags", "+faststart", out], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"H.264 변환 실패: {r.stderr[-200:]}")
        log(f"X: H.264 로 변환 — {os.path.basename(video)} ({vline.split('Video:')[-1].split(',')[0].strip()})")
    return out


def post_video(text, video, dry_run=None, cfg=None):
    """영상 첨부 글을 올린다. {'status': 'published'|'dry_run'|'disabled'|'error', ...}"""
    cfg = cfg or load_config()
    x = cfg.get("x") or {}
    if dry_run is None:
        dry_run = not x.get("enabled", False)
    text = _fit(text)
    if not video or not os.path.exists(video):
        return {"status": "error", "error": f"영상 없음: {video}"}
    if dry_run:
        log(f"X[DRY]: 글 {_weight(text)}/{MAX_WEIGHT}자, 영상 {os.path.getsize(video) // 1024}KB — {text[:60]}")
        return {"status": "dry_run", "text": text}
    try:
        s = _session(cfg)
        t0 = time.time()
        mid = _upload_video(s, _x_ready(video))
        j = _check(s.post(f"{API}/tweets", json={"text": text, "media": {"media_ids": [str(mid)]}}),
                   "게시")
        tid = (j.get("data") or {}).get("id", "")
        user = x.get("username", "i")
        url = f"https://x.com/{user}/status/{tid}" if tid else ""
        log(f"X: 게시 완료({time.time() - t0:.0f}초) {url}")
        return {"status": "published", "id": tid, "url": url}
    except Exception as e:
        log(f"X: 게시 실패(유튜브는 정상): {type(e).__name__}: {str(e)[:200]}")
        return {"status": "error", "error": str(e)[:300]}


def crosspost(data, video=None, summary=None):
    """뉴스·퀴즈 data 에서 글을 만들어 영상과 함께 올린다. 설정이 꺼져 있으면 건너뛴다."""
    cfg = load_config()
    if not (cfg.get("x") or {}).get("enabled", False):
        return {"status": "disabled"}
    video = video or data.get("video")
    text = compose(data.get("title", ""), summary or "", data.get("hashtags") or data.get("tags") or [])
    return post_video(text, video, dry_run=False, cfg=cfg)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("사용: python x_post.py <영상.mp4> \"글\" [--go]")
    r = post_video(sys.argv[2], sys.argv[1], dry_run="--go" not in sys.argv)
    print(json.dumps(r, ensure_ascii=False))
