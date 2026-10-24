"""남색 블로그 헤더(smusafe) — 2800x700 로 그려 1400x350 JPG 로 줄인다. 글자는 크게, 여백은 좁게."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from shared.fonts import display_css, ROOT_FONT_DIR  # noqa: E402
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

HERE = os.path.dirname(os.path.abspath(__file__))
MASCOT = os.path.join(os.path.dirname(HERE), "youtube-shorts-auto", "legal", "mascot.png")
W, H = 2800, 700
OUT = os.path.join(HERE, "posts", "smusafe_header_new_web.jpg")
HTML = f"""<!doctype html><html><head><meta charset="utf-8"><style>{display_css()}
 body{{margin:0}}
 #h{{width:{W}px;height:{H}px;position:relative;overflow:hidden;box-sizing:border-box;padding:0 150px;
   display:flex;align-items:center;color:#fff;font-family:'Display',sans-serif;
   background:radial-gradient(circle at 88% 45%,rgba(180,70,90,.45),rgba(0,0,0,0) 34%),linear-gradient(110deg,#0b1d45,#14295c 60%,#1b2f66)}}
 #h:before{{content:'';position:absolute;inset:0;opacity:.18;
   background:linear-gradient(rgba(255,255,255,.5) 1px,transparent 1px) 0 0/70px 70px,linear-gradient(90deg,rgba(255,255,255,.5) 1px,transparent 1px) 0 0/70px 70px}}
 .t{{position:relative}}
 .k{{font-family:'Body';font-size:60px;letter-spacing:12px;color:#f6d04d}}
 .n{{font-size:186px;line-height:1.08;letter-spacing:-5px;margin-top:6px}}
 .s{{font-family:'Body';font-size:78px;color:#dbe6f5;margin-top:22px}}
 .r{{width:260px;height:14px;background:#e24a5a;border-radius:7px;margin-top:40px}}
 .m{{position:absolute;right:30px;top:-10px;height:720px}}
</style></head><body><div id="h"><div class="t">
 <div class="k">SEMYUNG UNIVERSITY</div><div class="n">세명대학교 재난안전학과</div>
 <div class="s">제천·충북 재난안전 소식과 학과 이야기</div><div class="r"></div></div>
 <img class="m" src="file://{MASCOT}"></div></body></html>"""
p = "/tmp/_safe_header.html"
open(p, "w", encoding="utf-8").write(HTML)
o = Options()
for a in ("--headless=new", f"--window-size={W},{H+200}", "--hide-scrollbars", "--allow-file-access-from-files",
          "--force-device-scale-factor=1", "--disable-features=MacAppCodeSignClone"):
    o.add_argument(a)
d = webdriver.Chrome(options=o)
try:
    d.get("file://" + p); time.sleep(1.5)
    d.find_element("id", "h").screenshot("/tmp/_safe_header.png")
finally:
    d.quit()
from PIL import Image
Image.open("/tmp/_safe_header.png").convert("RGB").resize((1400, 350), Image.LANCZOS).save(OUT, quality=92)
print(OUT, os.path.getsize(OUT)//1024, "KB")
