"""저장된 토큰(tiktok_token.json)으로 틱톡 Content Posting API 에 세로 mp4 를 게시한다.

흐름: 토큰 자동 갱신 → creator_info 조회(허용 공개범위 확인) → video/init(FILE_UPLOAD)
     → upload_url 로 영상 PUT → status 폴링.

★ 심사(audit) 전(샌드박스)에는 privacy_level 이 SELF_ONLY(본인만) 로만 게시된다.
  공개(PUBLIC_TO_EVERYONE) 는 앱 심사 통과 후 creator_info 의 허용 목록에 나타난다.

★ 안전장치(다른 업로더와 동일 철학):
  - 수동 실행(python tiktok_upload.py)은 기본 dry_run → 게시하지 않고 준비상태만 출력.
  - 실제 게시는 run_weekly.py(스케줄)에서 dry_run=False 로만 일어난다.
  - 실제 게시를 본인만보기로 테스트하려면:  python tiktok_upload.py --selfonly
"""
import json
import os
import sys
import time

import requests

from common import POSTS_DIR, TIKTOK_TOKEN_PATH, load_config, log

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
CREATOR_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


def _token_store():
    """토큰은 암호화 저장소에 있다(shared/token_store.py)."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    from shared import token_store
    return token_store


def _load_token():
    tok = _token_store().read_json(TIKTOK_TOKEN_PATH)
    if not tok:
        raise RuntimeError(
            "틱톡 토큰(TIKTOK_TOKEN)이 없습니다. 먼저 tiktok_login_setup.py 로 1회 로그인하세요.")
    return tok


def _save_token(tok):
    _token_store().write_json(TIKTOK_TOKEN_PATH, tok)


def _access_token(cfg):
    tok = _load_token()
    obtained = tok.get("_obtained_at", 0)
    expires = tok.get("expires_in", 0)
    # 만료 5분 전이면 갱신
    if time.time() >= obtained + expires - 300:
        r = requests.post(TOKEN_URL, headers={
            "Content-Type": "application/x-www-form-urlencoded"
        }, data={
            "client_key": cfg["client_key"],
            "client_secret": cfg["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": tok["refresh_token"],
        }, timeout=30)
        new = r.json()
        if "access_token" not in new:
            raise RuntimeError(f"틱톡 토큰 갱신 실패: {new}")
        new["_obtained_at"] = int(time.time())
        _save_token(new)
        log("틱톡 토큰 자동 갱신됨.")
        return new["access_token"]
    return tok["access_token"]


def _headers(access_token):
    return {"Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8"}


def _build_caption(data, cfg):
    parts = [(data.get("title") or "").strip()]
    homepage = cfg.get("homepage_url", "").strip() if isinstance(cfg, dict) else ""
    if homepage:
        parts.append(f"🏫 세명대학교 재난안전학과 {homepage}")
    tags = data.get("hashtags") or []
    tags = [t for t in tags if t.lower() != "shorts"]  # 틱톡엔 Shorts 불필요
    if tags:
        parts.append(" ".join("#" + t for t in tags))
    cap = "\n".join(p for p in parts if p)
    return cap[:2150]  # 틱톡 캡션 여유 상한


def upload(data, dry_run=None, privacy=None):
    cfg = load_config()
    tk = cfg.get("tiktok", {})
    if dry_run is None:
        dry_run = tk.get("dry_run", True)
    if privacy is None:
        privacy = tk.get("privacy_level", "SELF_ONLY")

    video_path = data.get("video")
    if not video_path or not os.path.exists(video_path):
        raise RuntimeError("업로드할 mp4 가 없습니다. 먼저 make_video.py 를 실행하세요.")
    caption = _build_caption(data, cfg.get("youtube", {}))
    size = os.path.getsize(video_path)

    if dry_run:
        log("DRY_RUN(틱톡): 게시하지 않습니다. 아래 준비 상태만 확인하세요.")
        log(f"  영상: {video_path} ({size/1_000_000:.1f}MB, {data.get('video_seconds','?')}s)")
        log(f"  캡션: {caption[:60]}...")
        log("  실제 게시는 run_weekly.py(스케줄), 본인만보기 테스트는 "
            "'python tiktok_upload.py --selfonly'.")
        return {"status": "dry_run", "video": video_path}

    if not tk.get("client_key") or tk.get("client_key", "").startswith("..."):
        raise RuntimeError("config.tiktok.client_key/secret 미입력. README 참고.")

    access = _access_token(tk)

    # 1) creator_info: 허용 공개범위 확인
    ci = requests.post(CREATOR_URL, headers=_headers(access), json={}, timeout=30).json()
    ci_data = ci.get("data", {})
    allowed = ci_data.get("privacy_level_options") or []
    if allowed and privacy not in allowed:
        log(f"요청 공개범위 {privacy} 불가(허용: {allowed}). "
            f"{'SELF_ONLY' if 'SELF_ONLY' in allowed else allowed[0]} 로 대체.")
        privacy = "SELF_ONLY" if "SELF_ONLY" in allowed else allowed[0]

    # 2) init (FILE_UPLOAD, 단일 청크 = 파일 전체)
    body = {
        "post_info": {
            "title": caption,
            "privacy_level": privacy,
            "disable_comment": bool(tk.get("disable_comment", False)),
            "disable_duet": bool(tk.get("disable_duet", False)),
            "disable_stitch": bool(tk.get("disable_stitch", False)),
            "video_cover_timestamp_ms": 1000,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": size,
            "total_chunk_count": 1,
        },
    }
    init = requests.post(INIT_URL, headers=_headers(access), json=body, timeout=30).json()
    if init.get("error", {}).get("code") not in (None, "ok"):
        raise RuntimeError(f"틱톡 init 실패: {init.get('error')}")
    idata = init.get("data", {})
    publish_id = idata.get("publish_id")
    upload_url = idata.get("upload_url")
    if not (publish_id and upload_url):
        raise RuntimeError(f"틱톡 init 응답 이상: {init}")

    # 3) 영상 바이트 PUT 업로드
    with open(video_path, "rb") as f:
        raw = f.read()
    put = requests.put(upload_url, headers={
        "Content-Type": "video/mp4",
        "Content-Length": str(size),
        "Content-Range": f"bytes 0-{size-1}/{size}",
    }, data=raw, timeout=120)
    if put.status_code not in (200, 201, 206):
        raise RuntimeError(f"틱톡 업로드 PUT 실패: {put.status_code} {put.text[:200]}")
    log(f"틱톡 업로드 전송 완료(publish_id={publish_id}). 처리 상태 확인 중...")

    # 4) 상태 폴링(최대 ~60초)
    final = "PROCESSING"
    for _ in range(20):
        time.sleep(3)
        st = requests.post(STATUS_URL, headers=_headers(access),
                           json={"publish_id": publish_id}, timeout=30).json()
        final = st.get("data", {}).get("status", "PROCESSING")
        if final in ("PUBLISH_COMPLETE", "FAILED"):
            break
    log(f"틱톡 게시 상태: {final} (privacy={privacy})")
    return {"status": final, "publish_id": publish_id, "privacy": privacy}


def _latest_data():
    """영상이 실제로 렌더링된 것 중 가장 최근 대본을 돌려준다.

    파일명 정렬은 쓰지 않는다 — 재난안전판(20260921_...)과 GeoAI판(geoai_20260921_...)은
    이름 규칙이 달라 사전순으로는 시간 순서가 뒤집힌다. 또 그날 아침 대본만 만들어지고
    렌더링 전인 json 이 맨 뒤에 올 수 있어(video 가 비어 있다) 그런 건 건너뛴다.
    """
    paths = [os.path.join(POSTS_DIR, f) for f in os.listdir(POSTS_DIR) if f.endswith(".json")]
    for path in sorted(paths, key=os.path.getmtime, reverse=True):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        v = data.get("video")
        if v and os.path.exists(v):
            return data
    raise SystemExit("먼저 파이프라인(generate_script→...→make_video)을 실행하세요.")


if __name__ == "__main__":
    data = _latest_data()
    if "--selfonly" in sys.argv:
        print(upload(data, dry_run=False, privacy="SELF_ONLY"))
    elif "--public" in sys.argv:
        print(upload(data, dry_run=False, privacy="PUBLIC_TO_EVERYONE"))
    else:
        print(upload(data, dry_run=True))
