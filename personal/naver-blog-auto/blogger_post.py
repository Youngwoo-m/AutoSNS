"""완성된 HTML 원고 한 편을 개인 Blogger(재난안전과 GeoAI, geoaina.blogspot.com)에 올린다 — 클로드 자동 작업용.

인증·라벨 규칙·중복 제목 확인은 geoai_blogger.py 것을 쓴다. 학과 Blogger 에는 올리지 않는다.
하루 발행 한도를 GeoAI 아침·저녁 글과 함께 쓰므로 quota:blogger-personal 잠금을 잡고 올린다.
그림·PDF 는 공개 https 주소로 넣는다(로컬 경로·티스토리 서명 링크 금지).

    ./.venv/bin/python blogger_post.py --html 원고.html --title "제목" --labels "토목시공기술사,흙의 다짐" --dry
    ./.venv/bin/python blogger_post.py --html 원고.html --title "제목" --labels "토목시공기술사" --go

결과는 마지막 줄에 JSON 한 줄: {"status": "published"|"dry"|"duplicate"|"error", "url": …, "message": …}
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))


def out(status, url="", message=""):
    print(json.dumps({"status": status, "url": url, "message": message}, ensure_ascii=False))
    return 0 if status in ("published", "dry") else 1


def main():
    ap = argparse.ArgumentParser(description="개인 Blogger 공용 발행기")
    ap.add_argument("--html", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--labels", default="", help="쉼표로 구분(브랜드·지역 라벨은 자동으로 붙는다)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry", action="store_true")
    g.add_argument("--go", action="store_true")
    ap.add_argument("--job", default="claude")
    a = ap.parse_args()
    if os.environ.get("AX_DRY") == "1":
        a.go = False
    body = open(a.html, encoding="utf-8").read()
    if re.search(r'(src|href)="(?!https?://)[^"#]', body):
        return out("error", message="본문에 http(s) 가 아닌 그림·링크 주소가 있습니다 — 공개 https 주소로 바꾸세요")
    labels = [x.strip() for x in a.labels.split(",") if x.strip()]

    import geoai_blogger as gb
    from shared.axlock import Timeout, hold, stopped
    if not a.go:
        r = gb.publish(a.title, body, labels, dry_run=True)
        return out("dry", message=f"라벨: {', '.join(r.get('labels', []))}")
    if stopped():
        return out("error", message="비상 정지 중이라 발행하지 않았습니다")
    try:
        with hold(["quota:blogger-personal"], job=f"{a.job}:blogger_post", wait=2400):
            r = gb.publish(a.title, body, labels, pinned=labels[:1])
    except Timeout:
        return out("error", message="40분 기다려도 개인 Blogger 한도 잠금이 비지 않았습니다")
    if r.get("status") == "published":
        return out("published", r.get("url", ""))
    if r.get("status") == "duplicate":
        return out("duplicate", message="같은 제목 글이 이미 있습니다")
    return out("error", message=r.get("error") or json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    sys.exit(main())
