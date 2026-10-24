"""블로그 헤더 이미지를 만든다(생성 배경 + 제목·설명 합성).

배경은 Gamma 로 만든 일러스트(위성·드론·지형·데이터 포인트)를 쓰고, 그 위에 제목과
설명을 얹는다. 결과물은 공개 저장소에 올려 Blogger 머리글의 '이미지 URL' 로 건다
(Blogger 레이아웃은 URL 입력을 받으므로 파일 업로드 자동화가 필요 없다).

배경 파일 경로(BG)만 바꿔서 다시 돌리면 헤더를 새로 뽑을 수 있다.
"""
import os, sys, time
sys.path.insert(0, "/Volumes/USB256/devAPP/AutoSNS/channels/naver-blog-auto")
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

import sys as _sys  # Pretendard 글꼴(공용 shared/fonts)
_sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.fonts import display_css  # noqa: E402

SC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "posts")
BG = f"file://{SC}/header_bg_1600x400.jpg"
W, H = 1600, 400
HTML = f"""<!doctype html><html><head><meta charset="utf-8"><style>{display_css()}
 body{{margin:0;background:#fff}}
 #header{{width:{W}px;height:{H}px;position:relative;overflow:hidden;
   background:#07142c url('{BG}') right center/cover no-repeat;
   font-family:'Body','Apple SD Gothic Neo','Malgun Gothic',sans-serif;color:#fff;
   display:flex;flex-direction:column;justify-content:center;padding:0 72px;box-sizing:border-box}}
 #header::before{{content:'';position:absolute;inset:0;
   background:linear-gradient(90deg,#07142c 0%,rgba(7,20,44,.92) 42%,rgba(7,20,44,0) 72%)}}
 .kicker{{position:relative;font-size:22px;letter-spacing:6px;color:#7dd3fc;font-weight:700;margin-bottom:14px}}
 .title{{position:relative;font-size:76px;font-weight:700;letter-spacing:-2px;line-height:1.1}}
 .desc{{position:relative;font-size:26px;color:#c7d6e6;margin-top:18px}}
 .rule{{position:relative;width:92px;height:5px;background:#38bdf8;margin-top:26px;border-radius:3px}}
</style></head><body>
 <div id="header">
   <div class="kicker">DISASTER SAFETY · GEOAI</div>
   <div class="title">재난안전과 GeoAI</div>
   <div class="desc">재난안전 · 공간정보 · 생성형 AI 를 쉽게 정리합니다</div>
   <div class="rule"></div>
 </div></body></html>"""
path = f"{SC}/_header.html"
open(path, "w", encoding="utf-8").write(HTML)
o = Options()
for a in ("--headless=new", f"--window-size={W+80},{H+120}", "--hide-scrollbars",
          "--allow-file-access-from-files", "--force-device-scale-factor=1"):
    o.add_argument(a)
# 크롬이 실행마다 앱 전체(~1.4GB)를 임시 폴더에 복제하고 남기는 것을 막는다(2026-10-09)
o.add_argument("--disable-features=MacAppCodeSignClone")
d = webdriver.Chrome(options=o)
try:
    d.get("file://" + path); time.sleep(1.5)
    out = f"{SC}/blog_header.png"
    d.find_element(By.ID, "header").screenshot(out)
    print(out, os.path.getsize(out)//1000, "KB")
finally:
    d.quit()
