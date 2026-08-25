"""스레드(Threads) 게시. 카드뉴스 결과물을 요약 텍스트로 바꿔 올린다.

공식 Threads API 를 쓴다(셀레늄 아님). 발행은 2단계다.
  1) POST /{user_id}/threads          → 미디어 컨테이너 생성
  2) POST /{user_id}/threads_publish  → 컨테이너 게시
문서 권고대로 두 단계 사이를 잠깐 기다린다.

이미지를 붙이려면 image_url 이 '공개 URL' 이어야 한다. 스레드 API 는 파일
업로드를 받지 않으므로 로컬 카드 PNG 를 그대로 올릴 수 없다. 공개 URL 이
없으면 자동으로 텍스트 전용(TEXT)으로 게시한다.

사용법:
  python post_threads.py                 # 최신 카드뉴스로 게시(설정의 dry_run 따름)
  python post_threads.py --dry-run       # 올릴 문구만 출력하고 게시하지 않음
"""
import glob
import json
import os
import sys
import time

import requests

from common import POSTS_DIR, load_config, log
from threads_token import valid_token

API = "https://graph.threads.net/v1.0"
LIMIT = 500          # 게시글당 500자
WAIT_SEC = 30        # 컨테이너 생성 후 권고 대기(문서 기준 평균 30초)


def _latest_post():
    # 파일명 역순이 아니라 수정 시각 기준으로 골라야 한다.
    # (FESTIVAL_HEAT.json 같은 이름이 날짜 스탬프보다 뒤로 정렬돼 최신을 가린다)
    files = sorted(glob.glob(os.path.join(POSTS_DIR, "*.json")),
                   key=os.path.getmtime, reverse=True)
    for f in files:
        with open(f, encoding="utf-8") as fp:
            d = json.load(fp)
        if d.get("cards"):
            return d, f
    raise RuntimeError("게시할 카드뉴스 데이터를 posts/ 에서 찾지 못했습니다.")


def build_text(data, cfg=None):
    """캡션을 스레드용 500자 이내 문구로 줄이고 태그를 붙인다.

    지역 태그(local_tags)는 에디션과 무관하게 항상 들어가야 하므로 먼저 확보한 뒤
    남는 공간에만 일반 해시태그를 채운다.
    """
    cfg = cfg or load_config()
    body = (data.get("caption") or data.get("title") or "").strip()

    local = [t for t in (cfg.get("local_tags") or []) if t]
    # hashtags[0] 은 여러 태그가 한 줄에 붙어 있는 형태라 쪼개 쓴다.
    raw = []
    for h in (data.get("hashtags") or []):
        raw.extend(str(h).replace("#", " ").split())
    # 순서를 지키며 중복 제거(hashtags[0] 묶음과 개별 항목이 서로 겹친다)
    seen, general = set(local), []
    for t in raw:
        if t and t not in seen:
            seen.add(t)
            general.append(t)

    def tagline(tags):
        return " ".join("#" + t for t in tags)

    must = tagline(local)
    # 본문 + 줄바꿈 2 + 지역태그 가 500 안에 들어가도록 본문을 줄인다.
    room = LIMIT - len(must) - 2
    if room < 40:                       # 지역태그만으로 꽉 차는 비정상 상황
        return (body[:LIMIT]).strip()
    if len(body) > room:
        body = body[:room - 1].rstrip() + "…"

    text = f"{body}\n\n{must}" if must else body
    # 남는 자리에 일반 태그를 하나씩 더한다.
    for t in general:
        cand = f"{text} #{t}"
        if len(cand) > LIMIT:
            break
        text = cand
    return text


def _create_container(user_id, token, text, image_url=None):
    params = {"access_token": token, "text": text}
    if image_url:
        params["media_type"] = "IMAGE"
        params["image_url"] = image_url
    else:
        params["media_type"] = "TEXT"
    r = requests.post(f"{API}/{user_id}/threads", data=params, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"컨테이너 생성 실패({r.status_code}): {r.text[:300]}")
    return r.json()["id"]


def _publish(user_id, token, container_id):
    r = requests.post(f"{API}/{user_id}/threads_publish",
                      data={"access_token": token, "creation_id": container_id},
                      timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"게시 실패({r.status_code}): {r.text[:300]}")
    return r.json().get("id")


def post(data=None, dry_run=None, image_url=None):
    cfg = load_config()
    tcfg = cfg.get("threads") or {}
    if dry_run is None:
        dry_run = tcfg.get("dry_run", True)
    if data is None:
        data, src = _latest_post()
        log(f"게시 원본: {os.path.basename(src)}")

    text = build_text(data, cfg)
    image_url = image_url or tcfg.get("image_url") or None

    log(f"스레드 문구 {len(text)}자 / 이미지 {'있음' if image_url else '없음(텍스트 전용)'}")
    print("\n" + "─" * 56 + f"\n{text}\n" + "─" * 56 + "\n")

    if dry_run:
        log("DRY_RUN: 실제 게시하지 않고 문구만 출력했습니다. "
            "게시하려면 config 의 threads.dry_run 을 false 로.")
        return {"status": "dry_run", "text": text}

    token, user_id = valid_token()
    cid = _create_container(user_id, token, text, image_url)
    log(f"컨테이너 생성됨({cid}). {WAIT_SEC}초 대기 후 게시합니다.")
    time.sleep(WAIT_SEC)
    pid = _publish(user_id, token, cid)
    log(f"스레드 게시 완료: {pid}")
    return {"status": "published", "id": pid, "text": text}


if __name__ == "__main__":
    post(dry_run=True if "--dry-run" in sys.argv else None)
