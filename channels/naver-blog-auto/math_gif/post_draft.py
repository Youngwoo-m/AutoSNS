"""수식 GIF·PNG 를 공개 이미지 저장소에 올리고 GeoAI 블로그(geoaina)에 '초안(비공개)'으로 저장한다 — 시험용.

geoai_assets.upload() 는 모든 그림을 JPEG 로 줄이므로 GIF 움직임이 사라진다. 그래서 파일을 그대로(줄이지 않고) 올린다.
발행(공개)은 하지 않는다. 초안은 Blogger 관리 화면(글 > 초안)에서 확인하고, 공개는 거기서 직접 누른다.

    ./.venv/bin/python math_gif/post_draft.py --title "[시험] …" --gif samples/soil_phase.gif --png samples/soil_formula.png \
        --prefix math-sample/20261023_soil --alt-gif "…" --alt-png "…" [--go]     # --go 없으면 올릴 내용만 보여 준다
"""
import argparse
import base64
import html
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import geoai_assets  # noqa: E402
import geoai_blogger  # noqa: E402
from common import load_config, log  # noqa: E402


def upload_raw(path, dest, cfg):
    """파일을 줄이지 않고 그대로 저장소에 올리고 CDN 주소를 돌려준다."""
    a = geoai_assets._acfg(cfg)
    repo, branch = geoai_assets.ensure_repo(cfg), a.get("branch", "main")
    with open(path, "rb") as f:
        body = {"message": f"수식 시험 이미지 추가: {dest}", "branch": branch,
                "content": base64.b64encode(f.read()).decode("ascii")}
    try:
        cur = json.loads(geoai_assets._gh(["api", f"repos/{repo}/contents/{dest}", "-q", "{sha:.sha}"]) or "{}")
        if cur.get("sha"):
            body["sha"] = cur["sha"]
    except RuntimeError:
        pass
    geoai_assets._gh(["api", "--method", "PUT", f"repos/{repo}/contents/{dest}", "--input", "-"], input=json.dumps(body))
    return f"https://cdn.jsdelivr.net/gh/{repo}@{branch}/{dest}"


def figure(url, alt, caption):
    return (f'<figure style="text-align:center;margin:1.4em 0">'
            f'<img src="{html.escape(url)}" alt="{html.escape(alt)}" style="max-width:100%;height:auto"/>'
            f'<figcaption style="color:#555;font-size:.9em">{html.escape(caption)}</figcaption></figure>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--gif", required=True)
    ap.add_argument("--png", required=True)
    ap.add_argument("--prefix", required=True, help="저장소 안 경로 앞부분(확장자 제외)")
    ap.add_argument("--alt-gif", required=True)
    ap.add_argument("--alt-png", required=True)
    ap.add_argument("--go", action="store_true")
    a = ap.parse_args()

    cfg = load_config()
    if not a.go:
        print("[미리보기] 올릴 파일:", a.gif, a.png, "→", a.prefix, "· 제목:", a.title)
        return
    gif_url = upload_raw(os.path.join(HERE, a.gif), a.prefix + ".gif", cfg)
    png_url = upload_raw(os.path.join(HERE, a.png), a.prefix + "_formula.png", cfg)
    log(f"이미지 올림: {gif_url} {png_url}")

    body = (
        "<p>수식이 나오는 글에 넣을 <b>Manim 도식 GIF</b>와 <b>LaTeX 수식 이미지</b>의 시험 글입니다. (공개하지 않는 초안)</p>"
        "<h2>흙의 3상과 건조단위중량</h2>"
        "<p>흙은 흙 입자·물·공기의 세 상으로 이루어지고, 건조단위중량은 물의 무게를 뺀 흙 입자 무게만을 부피로 나눈 값입니다.</p>"
        + figure(gif_url, a.alt_gif, "도식: 3상 모델에서 건조단위중량 식이 만들어지는 과정")
        + "<p>습윤단위중량 γt와 함수비 w를 알 때 건조단위중량은 다음과 같습니다.</p>"
        + figure(png_url, a.alt_png, "건조단위중량 γd = γt / (1 + w/100)")
    )
    g = geoai_blogger.gcfg(cfg)
    svc = geoai_blogger.service()
    r = svc.posts().insert(blogId=geoai_blogger.blog_id(cfg), isDraft=True, body={
        "kind": "blogger#post", "title": a.title, "content": body, "labels": ["시험"]}).execute()
    print(json.dumps({"status": "draft", "id": r.get("id"), "url": r.get("url", ""), "gif": gif_url, "png": png_url},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
