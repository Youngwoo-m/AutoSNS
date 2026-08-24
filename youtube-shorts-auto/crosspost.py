"""유튜브 발행 후, 그 영상을 네이버 블로그 '동영상뉴스' 카테고리에도 함께 올린다.

네이버 로그인/프로필은 naver-blog-auto 에 있으므로, 그쪽 venv 로 post_video.py 를
서브프로세스 호출한다. 실패해도 유튜브 발행에는 영향 없다(예외를 안으로 삼킴).
"""
import json
import os
import subprocess

from common import BASE_DIR, load_config, log


def crosspost_naver_video(data, video_url, dry_run=False):
    ycfg = load_config().get("youtube", {})
    if not ycfg.get("crosspost_naver", False):
        return
    if not video_url:
        log("동영상뉴스: 유튜브 URL 이 없어 건너뜀")
        return

    naver_dir = os.path.join(os.path.dirname(BASE_DIR), "naver-blog-auto")
    py = os.path.join(naver_dir, ".venv", "bin", "python")
    script = os.path.join(naver_dir, "post_video.py")
    if not (os.path.exists(py) and os.path.exists(script)):
        log(f"동영상뉴스: naver-blog-auto 를 찾지 못해 건너뜀({naver_dir})")
        return

    payload = {
        "title": data.get("title", "재난안전 동영상 뉴스"),
        "body": data.get("description", ""),      # 유튜브 설명(사실 요약)
        "youtube_url": video_url,
        "sources": data.get("sources", []),
        "category": ycfg.get("crosspost_category", "동영상뉴스"),
        "dry_run": dry_run,
    }
    # 유튜브판의 SMUDS_EDITION 이 네이버 동영상글에 새지 않도록 제거하고 넘긴다
    env = {k: v for k, v in os.environ.items() if k != "SMUDS_EDITION"}
    try:
        r = subprocess.run([py, script], input=json.dumps(payload), text=True,
                           cwd=naver_dir, env=env, capture_output=True, timeout=900)
        tail = (r.stdout or "").strip().splitlines()[-1:] or [""]
        log(f"동영상뉴스 크로스포스트 종료(exit={r.returncode}) {tail[0][:80]}")
        if r.returncode != 0 and r.stderr:
            log(f"  stderr: {r.stderr.strip()[-200:]}")
    except Exception as e:
        log(f"동영상뉴스 크로스포스트 실패(유튜브는 정상): {type(e).__name__}")
