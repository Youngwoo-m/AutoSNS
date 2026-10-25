"""공개 글·파일에 박힌 이미지 저장소 주소(CDN)를 새 주소로 한꺼번에 고친다 — geoai-assets 를 SMUDS-m → Youngwoo-m 으로 옮길 때 만들었다.

    # naver-blog-auto 가상환경 파이썬으로 실행(블로거 API 인증이 거기 있다)
    cd channels/naver-blog-auto && ./.venv/bin/python ../../tools/rewrite_asset_urls.py blogger          # 시험(고치지 않음)
    cd channels/naver-blog-auto && ./.venv/bin/python ../../tools/rewrite_asset_urls.py blogger --go     # 실제 수정
    python3 tools/rewrite_asset_urls.py files [--go]                                          # 저장소 안 파일

  --old / --new   바꿀 문구(기본 SMUDS-m/geoai-assets → Youngwoo-m/geoai-assets)
수정 전에 원본을 backups/asset_urls_<날짜>/ 에 저장한다(되돌릴 때 쓴다). 수정한 글은 다시 읽어 옛 주소가 0 인지 확인한다.
티스토리 글은 편집기를 거쳐야 해서 GeoAI_NA/naver-blog-auto/tistory_rewrite_urls.py 가 따로 한다.
"""
import argparse
import datetime
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
OLD, NEW = "SMUDS-m/geoai-assets", "Youngwoo-m/geoai-assets"
STAMP = datetime.date.today().strftime("%Y%m%d")
BK = os.path.join(ROOT, "backups", f"asset_urls_{STAMP}")

# 저장소 안에서 고칠 파일(옛 백업 html 은 역사 기록이라 건드리지 않는다)
FILES = ["channels/naver-blog-auto/assets/widget/dinner_banner.json",
         "channels/naver-blog-auto/assets/widget/shuttle_banner.json", "site/geoai-site/index.html",
         "channels/naver-blog-auto/README.md", "channels/naver-blog-auto/shots/README.md", "assets/blogger/README.md"]


def cmd_files(a):
    n = 0
    for rel in FILES:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        s = open(p, encoding="utf-8").read()
        c = s.count(a.old)
        if not c:
            continue
        n += c
        print(f"  {rel}: {c}곳")
        if a.go:
            os.makedirs(os.path.dirname(os.path.join(BK, "files", rel)), exist_ok=True)
            open(os.path.join(BK, "files", rel), "w", encoding="utf-8").write(s)
            open(p, "w", encoding="utf-8").write(s.replace(a.old, a.new))
    print(("수정 완료" if a.go else "시험(고치지 않음)") + f": 파일 {n}곳")
    if a.go:
        print("site/geoai-site/index.html 을 고쳤으면 Netlify 사이트를 다시 배포해야 반영된다.")


def cmd_blogger(a):
    sys.path.insert(0, os.path.join(ROOT, "channels", "naver-blog-auto"))
    sys.path.insert(0, ROOT)
    os.chdir(os.path.join(ROOT, "channels", "naver-blog-auto"))
    import geoai_blogger as gb
    svc, bid = gb.service(), gb.blog_id()
    posts, tok = [], None
    while True:
        r = svc.posts().list(blogId=bid, maxResults=50, fetchBodies=True, pageToken=tok,
                             status=["LIVE", "DRAFT", "SCHEDULED"],
                             fields="items(id,title,status,content),nextPageToken").execute()
        posts += r.get("items", [])
        tok = r.get("nextPageToken")
        if not tok:
            break
    hit = [p for p in posts if a.old in p.get("content", "")]
    print(f"개인 블로거: 글 {len(posts)}편 중 {len(hit)}편, 주소 {sum(p['content'].count(a.old) for p in hit)}곳")
    done = bad = 0
    for p in hit:
        if not a.go:
            continue
        os.makedirs(os.path.join(BK, "blogger"), exist_ok=True)
        open(os.path.join(BK, "blogger", f"{p['id']}.html"), "w", encoding="utf-8").write(p["content"])
        svc.posts().patch(blogId=bid, postId=p["id"], body={"content": p["content"].replace(a.old, a.new)}).execute()
        after = svc.posts().get(blogId=bid, postId=p["id"], fields="content").execute()["content"]
        if a.old in after:
            bad += 1
            print(f"  ✗ 남음: {p['id']} {p['title'][:30]}")
        else:
            done += 1
    if a.go:
        print(f"수정 완료 {done}편, 옛 주소가 남은 글 {bad}편. 원본은 {BK}/blogger/ 에 있다.")
    else:
        for p in hit[:5]:
            print(f"  시험: {p['status']} {p['title'][:40]} ({p['content'].count(a.old)}곳)")
        print("시험(고치지 않음)")


def main():
    ap = argparse.ArgumentParser(description="이미지 저장소 주소 일괄 고치기")
    ap.add_argument("what", choices=["blogger", "files"])
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--old", default=OLD)
    ap.add_argument("--new", default=NEW)
    a = ap.parse_args()
    (cmd_blogger if a.what == "blogger" else cmd_files)(a)


if __name__ == "__main__":
    main()
