"""smusafety 블로그 헤더 이미지(2400x600) — 헤드리스 크롬으로 직접 그린다."""
import os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

W, H = 2400, 600
OUT = "/tmp/smusafety_header.png"
HTML = f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Gothic+A1:wght@400;700;900&display=swap" rel="stylesheet">
<style>
 body {{ margin:0; }}
 #h {{ width:{W}px; height:{H}px; box-sizing:border-box; position:relative; overflow:hidden;
      background:linear-gradient(120deg,#0B1C3A 0%,#12294f 55%,#173463 100%);
      font-family:'Gothic A1',sans-serif; color:#fff; display:flex; align-items:center;
      padding:0 110px; }}
 /* 지도 격자 — 공간정보/재난관리 느낌 */
 #h:before {{ content:''; position:absolute; inset:0;
      background-image:linear-gradient(rgba(255,255,255,.07) 1px,transparent 1px),
                       linear-gradient(90deg,rgba(255,255,255,.07) 1px,transparent 1px);
      background-size:80px 80px; }}
 #h:after {{ content:''; position:absolute; right:-160px; top:-220px; width:900px; height:900px;
      border-radius:50%; background:radial-gradient(circle,rgba(230,57,70,.28),transparent 62%); }}
 .txt {{ position:relative; z-index:2; }}
 .kick {{ font-size:34px; font-weight:700; letter-spacing:.14em; color:#FFD24A; margin-bottom:18px; }}
 .title {{ font-size:96px; font-weight:900; letter-spacing:-.02em; line-height:1.12; }}
 .sub {{ margin-top:22px; font-size:38px; font-weight:400; color:#cfd9ea; }}
 .bar {{ width:200px; height:10px; background:#E63946; border-radius:6px; margin:30px 0 0; }}
 .mascot {{ position:absolute; right:150px; bottom:-30px; height:470px; z-index:2; }}
</style></head><body>
<div id="h">
  <div class="txt">
    <div class="kick">SEMYUNG UNIVERSITY</div>
    <div class="title">세명대학교 재난안전학과</div>
    <div class="sub">제천·충북 재난안전 소식과 학과 이야기</div>
    <div class="bar"></div>
  </div>
  <img class="mascot" src="https://smuds.netlify.app/mascot.png">
</div></body></html>"""

path = "/tmp/_header.html"
open(path, "w", encoding="utf-8").write(HTML)
o = Options()
o.add_argument("--headless=new"); o.add_argument(f"--window-size={W},{H+300}")
o.add_argument("--hide-scrollbars"); o.add_argument("--force-device-scale-factor=1")
d = webdriver.Chrome(options=o)
try:
    d.get("file://" + path); time.sleep(3)
    d.set_window_size(W, H + 300)
    d.find_element("id", "h").screenshot(OUT)
finally:
    d.quit()
print(OUT, os.path.getsize(OUT) // 1024, "KB")
