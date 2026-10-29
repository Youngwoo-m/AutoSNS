"""티스토리 본문 HTML 을 네이버 스마트에디터에 '붙여넣기'로 옮긴다(개인 교차 발행용, 2026-10-28).

글자를 한 줄씩 치면 표는 '|' 줄 글, 인용은 「」, 구분선·문단 안 링크·둘째 그림·PDF 가 빠졌다.
본문 HTML 을 macOS 시스템 클립보드에 넣고 Cmd+V 로 붙이면 에디터가 표·인용·구분선·링크·번호를
제 구성요소로 바꾼다(가짜 paste 이벤트는 먹지 않음). 다만 티스토리(카카오) 그림 주소는 네이버에서
깨지고 PDF 주소는 네이버 referer 로 404 가 나서, 그 자리에 표시 글자를 두고 붙인 뒤 받아 둔 파일을
사진·파일 버튼으로 그 자리에 올린다(GIF 도 움직임 그대로 올라간다).

    prep(body_html, workdir) -> {"html", "images", "files", "expect"}
    fill(driver, data)       # 제목을 넣은 뒤 부른다. 빠진 것이 있으면 RuntimeError
"""
import html as H
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

UA = {"User-Agent": "Mozilla/5.0"}
MARK = "[[AX{}{}]]"     # 예: [[AXIMG0]] [[AXFILE0]]

# 버튼이 여는 숨은 file input 을 가로챈다(창이 뜨지 않게 click 을 막고 요소만 잡아 둔다)
HOOK_JS = """
if(!window.__axHook){window.__axHook=1; var o=HTMLInputElement.prototype.click;
HTMLInputElement.prototype.click=function(){ if(this.type==='file'){ window.__axFile=this;
  if(!this.isConnected){this.style.display='none';document.body.appendChild(this);} return;}
  return o.apply(this,arguments);};}
window.__axFile=null;"""

COUNT_JS = """
var r={};
document.querySelectorAll('.se-content .se-component').forEach(function(c){
  var k=(c.className.match(/se-component\\s+se-([\\w-]+)/)||[])[1]||'?'; r[k]=(r[k]||0)+1;});
r.link=document.querySelectorAll('.se-content .se-link').length;
return r;"""


def _download(url, folder, name):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())
    return path


def prep(body, workdir):
    """그림·첨부를 받아 두고 그 자리를 표시 글자로 바꾼 HTML 과, 에디터에 있어야 할 구성요소 수를 돌려준다."""
    images, files = [], []

    def fileblock(m):
        a = re.search(r'href="([^"]+)"', m.group(0))
        n = re.search(r'class="name">([^<]+)<', m.group(0))
        if not a:
            return ""
        name = H.unescape(n.group(1)).strip() if n else os.path.basename(urllib.parse.urlparse(H.unescape(a.group(1))).path)
        files.append(_download(H.unescape(a.group(1)), workdir, name))
        return f"<p>{MARK.format('FILE', len(files) - 1)}</p>"

    def figure(m):
        fig = m.group(0)
        out = []
        for src in re.findall(r'<img[^>]+src="([^"]+)"', fig):
            src = H.unescape(src)
            ext = os.path.splitext(urllib.parse.urlparse(src).path)[1].lower() or ".png"
            images.append(_download(src, workdir, f"img{len(images):02d}{ext}"))
            out.append(f"<p>{MARK.format('IMG', len(images) - 1)}</p>")
        if not out:
            return fig
        cap = re.search(r"<figcaption[^>]*>(.*?)</figcaption>", fig, re.S)
        return "".join(out) + (f"<p>{cap.group(1)}</p>" if cap and cap.group(1).strip() else "")

    # 파일 카드는 <p> 안에 들어 있다 → 감싼 <p> 까지 바꾼다
    body = re.sub(r'(?:<p[^>]*>\s*)?<figure class="fileblock".*?</figure>(?:\s*</p>)?', fileblock, body, flags=re.S)
    body = re.sub(r"<figure\b.*?</figure>", figure, body, flags=re.S)
    # 본문 끝 '#태그 #태그' 줄은 네이버에서는 태그 칸으로 넣는다
    body = re.sub(r"<p[^>]*>\s*(?:#[^\s<#]+\s*)+</p>", "", body)
    expect = {
        "table": len(re.findall(r"<table\b", body)),
        "quotation": len(re.findall(r"<blockquote\b", body)),
        "horizontalLine": len(re.findall(r"<hr\b", body)),
        "image": len(images),
        "file": len(files),
    }
    heads = [re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", "", h))).strip()
             for h in re.findall(r"<h[23][^>]*>(.*?)</h[23]>", body, re.S)]
    return {"html": body, "images": images, "files": files, "expect": expect, "headings": [h for h in heads if h]}


def _set_clipboard_html(body):
    hexs = body.encode("utf-8").hex()
    if len(hexs) > 900_000:
        raise RuntimeError(f"본문 HTML 이 너무 커 클립보드에 넣지 못함({len(body)}바이트)")
    subprocess.run(["osascript", "-e", f"set the clipboard to «data HTML{hexs}»"], check=True)


def _count(driver):
    return driver.execute_script(COUNT_JS) or {}


def _put_at_marker(driver, mark, path, button, kind):
    """표시 글자 문단을 지우고 그 자리에 파일을 올린다. 올라가면 True."""
    p = driver.execute_script("""
var ps=document.querySelectorAll('.se-content .se-text-paragraph');
for(var i=0;i<ps.length;i++){ if(ps[i].innerText.trim()===arguments[0]) return ps[i]; } return null;""", mark)
    if p is None:
        raise RuntimeError(f"붙여넣은 본문에서 자리표시 {mark} 를 찾지 못함")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", p)
    time.sleep(0.4)
    ActionChains(driver).move_to_element(p).click().send_keys(Keys.END).perform()
    # 에디터는 자체 선택 모델을 써서 JS 선택+지우기가 한 글자만 지운다 → 글자 수만큼 지운다
    for _ in range(len(mark)):
        ActionChains(driver).send_keys(Keys.BACK_SPACE).perform()
        time.sleep(0.03)
    time.sleep(0.4)
    before = _count(driver).get(kind, 0)
    driver.execute_script(HOOK_JS)
    driver.find_element(By.CSS_SELECTOR, f"button[data-name='{button}']").click()
    time.sleep(1.5)
    fi = driver.execute_script("return window.__axFile;")
    if not fi:
        # 파일 버튼은 '내 컴퓨터 / 네이버 MYBOX' 고르는 층을 먼저 연다
        for b in driver.find_elements(By.CSS_SELECTOR, ".se-popup-file-source-button-local"):
            driver.execute_script("arguments[0].click();", b)
            time.sleep(1.5)
            break
        fi = driver.execute_script("return window.__axFile;")
    if not fi:
        raise RuntimeError(f"{button} 버튼의 파일 입력을 찾지 못함")
    fi.send_keys(os.path.abspath(path))
    for _ in range(60):
        time.sleep(1)
        if _count(driver).get(kind, 0) > before:
            time.sleep(1)
            return True
    return False


def fill(driver, data):
    """제목 아래 본문 칸에 data['paste'] 를 붙이고 그림·첨부를 제자리에 올린 뒤, 원문과 구성요소 수를 맞춰 본다."""
    from publish_naver import MOD_KEY, _doc_text, dismiss_upload_error, log
    pk = data["paste"]
    el = driver.find_elements(By.CSS_SELECTOR, ".se-content .se-component.se-text .se-text-paragraph")[-1]
    ActionChains(driver).move_to_element(el).click().perform()
    time.sleep(0.5)
    _set_clipboard_html(pk["html"])
    ActionChains(driver).key_down(MOD_KEY).send_keys("v").key_up(MOD_KEY).perform()
    last, same = None, 0
    for _ in range(40):                       # 구성요소 수가 3초 동안 그대로면 붙여넣기 끝
        time.sleep(1)
        now = _count(driver)
        same = same + 1 if now == last else 0
        last = now
        if same >= 3 and now.get("text"):
            break
    log(f"붙여넣기 뒤 구성요소: {last}")
    for i, path in enumerate(pk["images"]):
        if not _put_at_marker(driver, MARK.format("IMG", i), path, "image", "image"):
            raise RuntimeError(f"그림 {os.path.basename(path)} 이 올라가지 않음")
        dismiss_upload_error(driver, quiet=True)
    for i, path in enumerate(pk["files"]):
        if not _put_at_marker(driver, MARK.format("FILE", i), path, "file", "file"):
            raise RuntimeError(f"첨부 {os.path.basename(path)} 이 올라가지 않음")
    time.sleep(2)
    have = _count(driver)
    log(f"그림·첨부 뒤 구성요소: {have}")
    missing = [f"{k} {v}개 중 {have.get(k, 0)}개" for k, v in pk["expect"].items() if have.get(k, 0) < v]
    txt = re.sub(r"\s+", " ", _doc_text(driver))
    missing += [f"소제목 '{h[:20]}'" for h in pk["headings"] if h[:25] not in txt]
    if "[[AX" in txt:
        missing.append("자리표시 글자가 남음")
    if missing:
        raise RuntimeError("붙여넣은 본문이 원문과 달라 발행을 멈춥니다: " + " / ".join(missing[:6]))
