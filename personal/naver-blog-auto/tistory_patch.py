"""이미 올린 티스토리 글의 편집기 본문에 조각(수식 이미지·GIF 등)을 끼워 넣는다 — 기존 이미지·첨부 토큰([##_Image…##])은 그대로 둔다.
--edit-post 는 본문을 통째로 바꾸므로 첨부가 든 글은 이 도구를 쓴다. 2026-10-23 티스토리 121번에 처음 사용.

    ./.venv/bin/python tistory_patch.py 글번호 "현재 제목" patch.json --dry|--go

patch.json: [{"anchor": "본문 속 한 곳에만 나오는 글귀", "mode": "before|after", "html": "끼울 HTML"}, …]
  before: 앵커가 든 문단 앞, after: 앵커 뒤 첫 닫는 태그(p·h·table) 다음. 앵커가 0곳·2곳 이상이면 저장하지 않는다."""
import json, os, re, sys, time
MAIN = os.path.dirname(os.path.abspath(__file__))
os.chdir(MAIN); sys.path.insert(0, MAIN)
import tistory_post as tp

def patch_content(content, patches):
    for p in patches:
        i = content.find(p["anchor"])
        if i < 0 or content.count(p["anchor"]) != 1:
            raise RuntimeError(f"앵커를 하나로 찾지 못함: {p['anchor'][:30]!r} ({content.count(p['anchor'])}곳)")
        if p["mode"] == "before":
            j = content.rfind("<p", 0, i)
        else:
            m = re.compile(r"</(p|h[1-6]|table)>").search(content, i); j = m.end()
        content = content[:j] + p["html"] + content[j:]
    return content

def edit_body(args, body):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    tc = tp.tc
    patches = json.loads(body)
    d = tc.build_driver(headless=not args.show)
    try:
        W = WebDriverWait(d, 25)
        u = f"{tc.BLOG}/manage/newpost/{args.edit_post}?type=post&returnURL=ENTRY"
        d.get(u)
        if "/manage/newpost" not in tc._cur_url(d) and tc.kakao_relogin(d):
            d.get(u)
        W.until(lambda x: x.execute_script("return !!(window.tinymce && tinymce.activeEditor && tinymce.activeEditor.initialized)"))
        time.sleep(1.5)
        cur = d.find_element(By.ID, "post-title-inp").get_attribute("value")
        if cur != args.title:
            raise RuntimeError(f"{args.edit_post}번 글 제목이 다름: {cur!r} — 저장하지 않음")
        old = d.execute_script("return tinymce.activeEditor.getContent();")
        new = patch_content(old, patches)
        open(os.environ["PATCH_DUMP"], "w").write(old + "\n=====\n" + new)
        d.execute_script("tinymce.activeEditor.setContent(arguments[0]);tinymce.activeEditor.fire('change');tinymce.activeEditor.save();", new)
        got = d.execute_script("return tinymce.activeEditor.getContent();")
        for k in ("fileblock", "imageblock", "[##_"):
            if old.count(k) != got.count(k):
                raise RuntimeError(f"{k} 개수가 달라짐 {old.count(k)}→{got.count(k)} — 저장하지 않음")
        n_img = got.count("cdn.jsdelivr.net")
        if n_img != sum(p["html"].count("cdn.jsdelivr.net") for p in patches):
            raise RuntimeError(f"끼운 이미지가 편집기에서 달라짐({n_img}) — 저장하지 않음")
        if not args.go:
            tc._shot(d, "edit_dry"); return f"{tc.BLOG}/{args.edit_post}"
        d.execute_script("arguments[0].click();", d.find_element(By.ID, "publish-layer-btn"))
        W.until(EC.presence_of_element_located((By.ID, "publish-btn"))); time.sleep(0.8)
        d.execute_script("document.getElementById('open20') && document.getElementById('open20').click();")
        d.execute_script("arguments[0].scrollIntoView({block:'center'}); arguments[0].click();", d.find_element(By.ID, "publish-btn"))
        W.until(lambda x: "/manage/newpost" not in x.current_url); time.sleep(2)
        return f"{tc.BLOG}/{args.edit_post}"
    finally:
        tc.close(d)

tp.edit_body = edit_body
n, title, pj, mode = sys.argv[1:5]
sys.argv = ["tistory_post.py", "--edit-post", n, "--html", pj, "--title", title, mode, "--job", "formula-retrofit"]
sys.exit(tp.main())
