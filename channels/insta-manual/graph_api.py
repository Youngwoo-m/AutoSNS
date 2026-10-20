"""Instagram Graph API 로 캐러셀을 발행한다. (공식 방식 — 브라우저 불필요)

Selenium 방식과 달리 Chrome 도 CAPTCHA 도 필요 없고, 서버에 올려두고 쓸 수 있다.
대신 준비물이 있다:
  - 인스타 **프로페셔널**(비즈니스/크리에이터) 계정 + 페이스북 페이지 연결
  - Meta 개발자 앱 + instagram_basic, instagram_content_publish 권한
  - 장기 액세스 토큰과 IG 사용자 ID

★ 이미지는 파일 업로드가 아니라 **공개 HTTPS URL** 로 넘긴다. Meta 서버가 그 주소로
  직접 받아가므로, 발행하는 순간 인증 없이 접근 가능해야 한다.
★ JPEG 만 지원한다. PNG 는 미리 변환해야 한다(prepare_jpeg 참고).

발행 절차(3단계):
  1) 이미지마다 컨테이너 생성  POST /{ig_id}/media  (is_carousel_item=true)
  2) 캐러셀 컨테이너 생성      POST /{ig_id}/media  (media_type=CAROUSEL, children=...)
  3) 발행                      POST /{ig_id}/media_publish  (creation_id=...)
"""
import time

import requests
from PIL import Image

from core import log

GRAPH_BASE = "https://graph.facebook.com"
DEFAULT_VERSION = "v23.0"
MAX_ITEMS = 10
TIMEOUT = 30


class GraphError(RuntimeError):
    """Meta 가 돌려준 오류를 사람이 읽을 수 있게 감싼다."""


def _url(version, path):
    return f"{GRAPH_BASE}/{version}/{path}"


def _call(method, url, params, what):
    try:
        r = requests.request(method, url, data=params if method == "POST" else None,
                             params=None if method == "POST" else params, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise GraphError(f"{what}: 네트워크 오류 — {e}") from e
    try:
        body = r.json()
    except ValueError:
        raise GraphError(f"{what}: 예상 못 한 응답({r.status_code}) — {r.text[:200]}")
    if "error" in body:
        e = body["error"]
        msg = e.get("error_user_msg") or e.get("message") or str(e)
        raise GraphError(f"{what}: {msg} (code={e.get('code')})")
    if not r.ok:
        raise GraphError(f"{what}: HTTP {r.status_code} — {str(body)[:200]}")
    return body


# ------------------------------------------------------------------ 이미지 준비
def prepare_jpeg(src_path, dst_path, max_edge=1440, quality=88):
    """Graph API 는 JPEG 만 받는다. PNG 등을 변환하고 너무 큰 이미지는 줄인다.

    투명 배경은 흰색으로 합성한다(JPEG 은 투명을 표현할 수 없다).
    """
    with Image.open(src_path) as im:
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        if max(im.size) > max_edge:
            r = max_edge / max(im.size)
            im = im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))),
                           Image.LANCZOS)
        im.save(dst_path, format="JPEG", quality=quality, optimize=True)
    return dst_path


# ------------------------------------------------------------------ 계정 확인
def verify(ig_user_id, token, version=DEFAULT_VERSION):
    """토큰과 계정 설정이 실제로 동작하는지 확인한다(발행하지 않음)."""
    body = _call("GET", _url(version, ig_user_id),
                 {"fields": "id,username,name,followers_count", "access_token": token},
                 "계정 확인")
    log(f"계정 확인 완료: @{body.get('username')} (id={body.get('id')})")
    return body


def publishing_limit(ig_user_id, token, version=DEFAULT_VERSION):
    """24시간 발행 한도 사용량. 한도는 100건이고 캐러셀은 1건으로 센다."""
    body = _call("GET", _url(version, f"{ig_user_id}/content_publishing_limit"),
                 {"fields": "config,quota_usage", "access_token": token}, "발행 한도 조회")
    data = (body.get("data") or [{}])[0]
    return {"used": data.get("quota_usage", 0),
            "total": (data.get("config") or {}).get("quota_total", 100)}


# ------------------------------------------------------------------ 발행
def _wait_ready(container_id, token, version, what, tries=10, delay=6):
    """컨테이너가 FINISHED 가 될 때까지 기다린다.

    문서 권장은 '1분에 한 번, 최대 5분'인데 이미지 캐러셀은 보통 수초 안에 끝난다.
    """
    for i in range(tries):
        body = _call("GET", _url(version, container_id),
                     {"fields": "status_code,status", "access_token": token},
                     f"{what} 상태 확인")
        st = body.get("status_code")
        if st == "FINISHED":
            return True
        if st in ("ERROR", "EXPIRED"):
            raise GraphError(f"{what} 실패: status={st} — {body.get('status', '')}")
        if i == 0:
            log(f"{what} 처리 대기 중... (status={st})")
        time.sleep(delay)
    raise GraphError(f"{what}: 시간 안에 준비되지 않았습니다(마지막 status={st}).")


def publish_carousel(image_urls, caption, ig_user_id, token,
                     version=DEFAULT_VERSION, dry_run=True):
    """공개 URL 목록을 캐러셀 게시물로 올린다.

    dry_run=True 면 컨테이너까지만 만들고 발행하지 않는다. 컨테이너는 24시간 뒤
    자동 만료되므로 남아도 게시되지 않는다 — 안전하게 배선을 점검할 수 있다.
    """
    urls = [u for u in image_urls if u][:MAX_ITEMS]
    if len(urls) < 2:
        raise GraphError("캐러셀은 이미지가 2장 이상이어야 합니다.")

    # 1) 이미지별 컨테이너
    children = []
    for i, u in enumerate(urls, 1):
        body = _call("POST", _url(version, f"{ig_user_id}/media"),
                     {"image_url": u, "is_carousel_item": "true", "access_token": token},
                     f"{i}번째 이미지 컨테이너 생성")
        children.append(body["id"])
        log(f"이미지 컨테이너 {i}/{len(urls)} 생성 완료")

    # 2) 캐러셀 컨테이너 (캡션은 여기에 붙는다)
    body = _call("POST", _url(version, f"{ig_user_id}/media"),
                 {"media_type": "CAROUSEL", "children": ",".join(children),
                  "caption": caption or "", "access_token": token},
                 "캐러셀 컨테이너 생성")
    carousel_id = body["id"]
    log(f"캐러셀 컨테이너 생성 완료 (id={carousel_id})")
    _wait_ready(carousel_id, token, version, "캐러셀")

    if dry_run:
        log("테스트 모드: 컨테이너까지만 만들고 발행하지 않았습니다.")
        log("   (컨테이너는 24시간 뒤 자동 만료되며 게시되지 않습니다.)")
        return {"status": "dry_run", "images": len(urls), "container_id": carousel_id}

    # 3) 발행
    body = _call("POST", _url(version, f"{ig_user_id}/media_publish"),
                 {"creation_id": carousel_id, "access_token": token}, "발행")
    media_id = body["id"]
    log(f"게시 완료 (media_id={media_id})")
    return {"status": "published", "images": len(urls), "media_id": media_id}


def post_comment(media_id, text, token, version=DEFAULT_VERSION):
    """게시물에 첫 댓글을 단다(해시태그 분리용)."""
    if not text.strip():
        return False
    _call("POST", _url(version, f"{media_id}/comments"),
          {"message": text, "access_token": token}, "첫 댓글 등록")
    log("첫 댓글 등록 완료.")
    return True
