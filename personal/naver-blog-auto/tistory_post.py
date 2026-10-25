"""완성된 HTML 원고 한 편을 티스토리(na-geoai.tistory.com)에 올린다 — 클로드 자동 작업(GeoAI_NA/claude-jobs)이 쓰는 공용 발행기.

글쓰기 화면 조작(로그인 쿠키·카카오 재로그인·카테고리·제목·본문·태그·공개 발행)은 tistory_crosspost.py 것을 그대로 쓴다.
크롬 프로필은 profile:tistory 잠금(shared/axlock.py)을 잡은 뒤에만 연다 — 다른 작업과 겹치지 않게.

첨부: 본문에 자리표시 <p data-ax-attach="파일 경로"></p> 를 넣으면 그 자리에 파일을 티스토리 첨부로 올린다.
  그림은 이미지, pdf 등은 파일 카드(네이티브 첨부)로 들어간다. 경로는 HTML 파일 기준 상대 경로도 된다.
유튜브 임베드: 본문의 <iframe src="https://www.youtube.com/embed/영상ID" …> 가 편집기에 넣은 뒤에도 남아 있는지 보고,
  지워졌으면 발행하지 않고 error 로 끝난다(--dry 에서도 같은 점검).

    ./.venv/bin/python tistory_post.py --html 원고.html --title "제목" --category "노르딕워킹" --tags "a,b,c" --dry
    ./.venv/bin/python tistory_post.py --html 원고.html --title "제목" --category "노르딕워킹" --tags "a,b,c" --go

이미 올린 글의 본문만 바꿀 때(제목·태그·카테고리·주소는 그대로):
    ./.venv/bin/python tistory_post.py --edit-post 109 --html 수정본.html --title "현재 제목" --dry|--go
    --title 은 글 번호가 맞는지 확인하는 용도다(편집기의 현재 제목과 다르면 중단). 첨부 자리표시는 지원하지 않는다.

결과는 마지막 줄에 JSON 한 줄: {"status": "published"|"dry"|"duplicate"|"error", "url": …, "message": …}
같은 제목 글이 공개 RSS 에 이미 있으면 올리지 않고 duplicate 로 끝난다(--allow-duplicate 로 끌 수 있음).
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
from common import log  # noqa: E402
import tistory_crosspost as tc  # noqa: E402

def out(status, url="", message=""):
    print(json.dumps({"status": status, "url": url, "message": message}, ensure_ascii=False))
    return 0 if status in ("published", "dry", "saved") else 1


def existing_url(title):
    u = tc.find_url(title, tries=1)
    return "" if "주소 확인 실패" in u else u


def attachments(body, base):
    """자리표시를 찾아 [(자리표시 원문, 절대 경로)]."""
    found = []
    for m in re.finditer(r'<p[^>]*\bdata-ax-attach="([^"]+)"[^>]*>\s*</p>', body):
        p = m.group(1)
        p = p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))
        if not os.path.isfile(p):
            raise FileNotFoundError(f"첨부 파일이 없습니다: {p}")
        found.append((m.group(0), p))
    return found


_DROP_JS = """
const [b64, name, mt] = arguments; const bin = atob(b64), u = new Uint8Array(bin.length);
for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
const dt = new DataTransfer(); dt.items.add(new File([u], name, {type: mt}));
const ed = tinymce.activeEditor, body = ed.getBody();
ed.focus(); ed.selection.select(body.firstChild, true); ed.selection.collapse(true);
for (const t of ['dragenter', 'dragover', 'drop'])
  body.dispatchEvent(new DragEvent(t, {bubbles: true, cancelable: true, dataTransfer: dt}));
"""
TOKEN = re.compile(r'<p[^>]*>\s*\[##_(?:Image|File)\|.*?_##\]\s*</p>', re.S)
MARKER = re.compile(r'<p[^>]*\bdata-ax-attach="[^"]*"[^>]*>.*?</p>', re.S)


def upload_at(d, path):
    """파일을 편집기에 끌어다 놓아 티스토리 첨부로 올리고, 생긴 첨부 토큰을 첫 자리표시 자리로 옮긴다.

    파일 입력칸(#attach-file)에 경로를 넣는 방식은 업로드가 시작되지 않았다(2026-10-18 시험).
    끌어다 놓기는 그림·PDF 모두 올라가지만 글 맨 앞에 들어가서, [##_Image|…_##] / [##_File|…_##]
    토큰을 찾아 자리표시와 바꾼다."""
    import base64
    import mimetypes
    get = "return tinymce.activeEditor.getContent()"
    before = d.execute_script(get)
    old = set(TOKEN.findall(before))
    mt = mimetypes.guess_type(path)[0] or "application/octet-stream"
    d.execute_script(_DROP_JS, base64.b64encode(open(path, "rb").read()).decode(), os.path.basename(path), mt)
    t0, new = time.time(), None
    while time.time() - t0 < 180:
        time.sleep(1.5)
        c = d.execute_script(get)
        new = [t for t in TOKEN.findall(c) if t not in old]
        if new:
            break
    else:
        tc._shot(d, "attach_timeout")
        log(f"  첨부 대기 중 본문 앞부분: {c[:200]!r}")
        raise RuntimeError(f"첨부 업로드 시간 초과: {os.path.basename(path)}")
    token = new[0]
    c = c.replace(token, "", 1)
    if not MARKER.search(c):
        raise RuntimeError(f"자리표시를 찾지 못함: {path}")
    c = MARKER.sub(lambda m: token, c, count=1)
    d.execute_script("tinymce.activeEditor.setContent(arguments[0]); tinymce.activeEditor.fire('change');"
                     "tinymce.activeEditor.save();", c)
    if token.split("|")[1][:40] not in d.execute_script(get):
        raise RuntimeError(f"첨부 토큰이 본문에서 사라짐: {os.path.basename(path)}")
    log(f"  첨부 올림: {os.path.basename(path)} ({mt})")


def publish(args, body, files):
    d = tc.build_driver(headless=not args.show)
    embeds = set(tc.YT_EMBED.findall(body))
    try:
        if not files and not embeds:
            return tc.write_post(d, {"title": args.title}, body, args.category, args.tags, args.go)
        # 본문을 넣은 직후 끼어든다: 자리표시마다 첨부를 올리고, 유튜브 임베드가 편집기에 남았는지 본 뒤
        # 남은 단계(태그·발행)를 write_post 와 같게 한다
        orig_set = d.execute_script
        state = {"done": False}

        def hooked(script, *a):
            r = orig_set(script, *a)
            if not state["done"] and "tinymce.activeEditor.setContent" in script:
                state["done"] = True
                for _, p in files:
                    upload_at(d, p)           # 올릴 때마다 앞 자리표시가 하나씩 첨부로 바뀐다
                c = orig_set("return tinymce.activeEditor.getContent()")
                lost = [v for v in embeds if f"embed/{v}" not in c]
                if lost:   # 편집기가 iframe 을 걸러 내면 영상 없이 발행되므로 여기서 멈춘다
                    tc._shot(d, "embed_lost")
                    raise RuntimeError(f"편집기가 유튜브 임베드 iframe 을 지웠습니다: {lost} — 발행하지 않음")
                if embeds:
                    log(f"  유튜브 임베드 유지 확인: {sorted(embeds)}")
                c = re.sub(r"\[##_Image\|.*?_##\]", "[그림]", re.sub(r"\[##_File\|.*?_##\]", "[파일]", c, flags=re.S), flags=re.S)
                log(f"  본문 순서: {re.sub(r'<[^>]+>', ' ', c).split()[:40]}")
            return r
        d.execute_script = hooked
        return tc.write_post(d, {"title": args.title}, body, args.category, args.tags, args.go)
    finally:
        try:
            del d.execute_script
        except Exception:
            pass
        tc.close(d)


def edit_body(args, body):
    """기존 글(args.edit_post)의 본문만 교체한다. 편집기의 현재 제목이 --title 과 다르면 저장하지 않는다."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    d = tc.build_driver(headless=not args.show)
    try:
        W = WebDriverWait(d, 25)
        u = f"{tc.BLOG}/manage/newpost/{args.edit_post}?type=post&returnURL=ENTRY"
        d.get(u)
        if "/manage/newpost" not in tc._cur_url(d) and tc.kakao_relogin(d):
            d.get(u)
        W.until(lambda x: x.execute_script("return !!(window.tinymce && tinymce.activeEditor && tinymce.activeEditor.initialized)"))
        time.sleep(1.5)
        cur_title = d.find_element(By.ID, "post-title-inp").get_attribute("value")
        if cur_title != args.title:
            raise RuntimeError(f"{args.edit_post}번 글 제목이 다름: {cur_title!r} — 저장하지 않음")
        d.execute_script("tinymce.activeEditor.setContent(arguments[0]);"
                         "tinymce.activeEditor.fire('change'); tinymce.activeEditor.save();", body)
        new = d.execute_script("return tinymce.activeEditor.getContent();")
        if len(new) < len(body) // 2:
            raise RuntimeError("편집기가 본문을 많이 지움 — 저장하지 않음")
        if not args.go:
            tc._shot(d, "edit_dry")
            return f"{tc.BLOG}/{args.edit_post}"
        d.execute_script("arguments[0].click();", d.find_element(By.ID, "publish-layer-btn"))
        W.until(EC.presence_of_element_located((By.ID, "publish-btn")))
        time.sleep(0.8)
        d.execute_script("document.getElementById('open20') && document.getElementById('open20').click();")
        d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();",
                         d.find_element(By.ID, "publish-btn"))
        W.until(lambda x: "/manage/newpost" not in x.current_url)
        time.sleep(2)
        return f"{tc.BLOG}/{args.edit_post}"
    finally:
        tc.close(d)


def main():
    ap = argparse.ArgumentParser(description="티스토리 공용 발행기")
    ap.add_argument("--html", required=True, help="본문 HTML 파일")
    ap.add_argument("--title", required=True)
    ap.add_argument("--category", default="", help="티스토리 관리 화면의 카테고리 이름 그대로(--edit-post 에서는 쓰지 않음)")
    ap.add_argument("--edit-post", type=int, default=0, help="이미 올린 글 번호 — 본문만 교체")
    ap.add_argument("--tags", default="", help="쉼표로 구분")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry", action="store_true", help="발행 직전에 멈춤(실제로 올리지 않음)")
    g.add_argument("--go", action="store_true", help="공개 발행")
    ap.add_argument("--allow-duplicate", action="store_true")
    ap.add_argument("--show", action="store_true", help="크롬 창을 띄워서(기본은 창 없이)")
    ap.add_argument("--job", default="claude", help="잠금 기록에 남길 작업 이름")
    args = ap.parse_args()
    args.tags = [t.strip() for t in args.tags.split(",") if t.strip()][:10]

    if os.environ.get("AX_DRY") == "1" and args.go:
        log("  AX_DRY=1 — 시험 실행이라 --go 를 --dry 로 바꿉니다")
        args.go, args.dry = False, True
    try:
        body = open(args.html, encoding="utf-8").read()
        files = attachments(body, os.path.dirname(os.path.abspath(args.html)))
    except (OSError, FileNotFoundError) as e:
        return out("error", message=str(e))
    if args.edit_post:
        from shared.axlock import Timeout, hold, stopped
        if args.go and stopped():
            return out("error", message="비상 정지 중이라 수정하지 않았습니다(ax-console/data/STOP.json)")
        if files:
            return out("error", message="--edit-post 는 첨부 자리표시를 지원하지 않습니다")
        try:
            with hold(["profile:tistory"], job=f"{args.job}:tistory_edit", wait=2400):
                os.environ["AX_LOCKED"] = "1"
                url = edit_body(args, body)
        except Timeout:
            return out("error", message="40분 기다려도 티스토리 크롬 프로필이 비지 않았습니다")
        except Exception as e:
            return out("error", message=f"{type(e).__name__}: {str(e)[:300]}")
        return out("saved" if args.go else "dry", url)
    if not args.category:
        return out("error", message="--category 가 필요합니다")
    if not args.allow_duplicate:
        u = existing_url(args.title)
        if u:
            return out("duplicate", u, "같은 제목 글이 이미 공개돼 있어 올리지 않았습니다")

    from shared.axlock import Timeout, hold, stopped
    if args.go and stopped():
        return out("error", message="비상 정지 중이라 발행하지 않았습니다(ax-console/data/STOP.json)")
    try:
        with hold(["profile:tistory"], job=f"{args.job}:tistory_post", wait=2400):
            os.environ["AX_LOCKED"] = "1"
            log(f"티스토리 {'발행' if args.go else '시험'}: [{args.category}] {args.title} (첨부 {len(files)}개)")
            try:
                url = publish(args, body, files)
            except RuntimeError as e:
                # 세션 만료 → 카카오 재로그인 직후 첫 시도는 글쓰기 화면에 못 들어가는 일이 있다(2026-10-19 06:01).
                # 같은 잠금 안에서 크롬을 새로 띄워 한 번만 다시 한다(재로그인으로 받은 새 쿠키를 쓴다).
                if "글쓰기 화면이 아님" not in str(e):
                    raise
                log(f"  글쓰기 화면 진입 실패 — 10초 뒤 한 번 더: {str(e)[:120]}")
                time.sleep(10)
                url = publish(args, body, files)
    except Timeout:
        return out("error", message="40분 기다려도 티스토리 크롬 프로필이 비지 않았습니다")
    except Exception as e:
        log(f"  티스토리 발행 실패: {type(e).__name__}: {e}")
        return out("error", message=f"{type(e).__name__}: {str(e)[:300]}")
    if not args.go:
        return out("dry", message="발행 직전까지 채우고 멈췄습니다(logs/ 에 스크린샷)")
    if "주소 확인 실패" in url:
        return out("error", url, "발행 버튼은 눌렀으나 공개 RSS 에서 글을 찾지 못했습니다 — 관리 화면에서 확인 필요")
    return out("published", url)


if __name__ == "__main__":
    sys.exit(main())
