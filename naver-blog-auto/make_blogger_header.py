"""학과 홈페이지 상단바 스타일 헤더(2400x420) — 흰 배경 + 로고 + 남색 학과명 + 금색 라인."""
import os, time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
W,H=2400,420; OUT="/tmp/smuds2026_header.png"
import sys as _sys  # KoPub 글꼴(공용 shared/fonts)
_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.fonts import kopub_bold_css  # noqa: E402

HTML=f"""<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>{kopub_bold_css()}
 body{{margin:0}}
 #h{{width:{W}px;height:{H}px;box-sizing:border-box;background:#fff;position:relative;
     display:flex;align-items:center;padding:0 120px;
     font-family:'KoPub','Noto Sans KR','Malgun Gothic',Dotum,sans-serif;
     border-bottom:10px solid #334A8E}}
 #h:after{{content:'';position:absolute;left:0;right:0;bottom:-10px;height:10px;
     background:linear-gradient(90deg,#334A8E 0 62%,#FFA500 62% 100%)}}
 .logo{{height:104px;margin-right:52px}}
 .div{{width:2px;height:104px;background:#d6d9e0;margin-right:52px}}
 .name{{font-size:92px;font-weight:900;color:#1b2333;letter-spacing:-.02em}}
 .sub{{margin-top:14px;font-size:34px;font-weight:500;color:#5b6273}}
 .right{{margin-left:auto;text-align:right}}
 .en{{font-size:30px;font-weight:700;letter-spacing:.22em;color:#334A8E}}
 .en2{{margin-top:10px;font-size:24px;letter-spacing:.12em;color:#8b91a1}}
 .mascot{{height:300px;margin-left:56px}}
</style></head><body>
<div id="h">
  <img class="logo" src="https://smuds.netlify.app/SMUDS_LOGO.png">
  <div class="div"></div>
  <div>
    <div class="name">재난안전학과</div>
    <div class="sub">제천·충북 재난안전 소식과 학과 이야기</div>
  </div>
  <div class="right">
    <div class="en">SEMYUNG UNIVERSITY</div>
    <div class="en2">DISASTER &amp; SAFETY</div>
  </div>
  <img class="mascot" src="https://smuds.netlify.app/mascot.png">
</div></body></html>"""
open("/tmp/_h2.html","w",encoding="utf-8").write(HTML)
o=Options(); o.add_argument("--headless=new"); o.add_argument(f"--window-size={W},{H+300}")
o.add_argument("--hide-scrollbars"); o.add_argument("--force-device-scale-factor=1")
# 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
o.add_argument("--disable-features=MacAppCodeSignClone")
d=webdriver.Chrome(options=o)
try:
    d.get("file:///tmp/_h2.html"); time.sleep(3); d.set_window_size(W,H+300)
    d.find_element("id","h").screenshot(OUT)
finally: d.quit()
print(OUT, os.path.getsize(OUT)//1024,"KB")
