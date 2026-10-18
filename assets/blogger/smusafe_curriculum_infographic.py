import os, sys, time
ROOT = "/Volumes/USB256/devAPP/AutoSNS"
sys.path.insert(0, ROOT)
from shared.fonts import display_css
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

OUT = os.path.dirname(os.path.abspath(__file__))
Y = [
 ("1학년", "기초를 다지는 해", [], ["CAD의 이해", "기후재난과 자연재해"]),
 ("2학년", "재난관리의 뼈대", ["재난안전 기초 및 이해", "재난관리론", "방재정책론", "AI 기반 재난위험분석", "수질오염방지기술 I"],
           ["재난안전 인공지능 기초", "위기대응관리론", "재난발생과 지반거동", "수리수문학", "수질오염개론"]),
 ("3학년", "도시와 시설을 지키는 법", ["도시방재학", "안전관리론", "재난안전시설 계획 및 설계 I"],
           ["재해대책 및 재해지도", "재난안전시설 계획 및 설계 II", "재난폐기물관리", "재난폐기물처리 및 실습", "재난방지수처리 및 실습", "수질오염방지기술 II"]),
 ("4학년", "현장과 실무로", [],
           ["생성형AI 재난실무", "재난안전 캡스톤디자인", "재난안전실무체험", "시설물안전진단 및 유지관리실습", "재해/환경영향평가실습", "재해예방 및 산업안전시스템론", "재난안전법", "재난안전세미나"]),
]
cols = ""
for y, sub, req, el in Y:
    chips = "".join(f'<div class="c req">{c}</div>' for c in req) + "".join(f'<div class="c">{c}</div>' for c in el)
    cols += f'<div class="col"><div class="yr">{y}</div><div class="sub">{sub}</div>{chips}</div>'
html = f"""<!doctype html><html><head><meta charset="utf-8"><style>{display_css()}
*{{box-sizing:border-box;margin:0}}
body{{background:#fff}}
#c{{width:1200px;padding:56px 56px 44px;background:#fff;font-family:'Body';color:#272C3C}}
.k{{color:#FFA500;font-size:20px;letter-spacing:.12em}}
h1{{font-family:'Display';font-weight:700;font-size:46px;color:#1b2333;margin:10px 0 6px}}
.lead{{font-size:21px;color:#5b6273}}
.bar{{width:90px;height:6px;background:#FFA500;margin:22px 0 30px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:18px}}
.col{{background:#f5f7fb;border-top:6px solid #334A8E;padding:20px 16px 18px}}
.yr{{font-family:'Display';font-weight:700;font-size:32px;color:#334A8E}}
.sub{{font-size:18px;color:#5b6273;margin:4px 0 16px}}
.c{{background:#fff;border:1.5px solid #d9dfeb;border-radius:8px;padding:10px 12px;font-size:18px;margin-bottom:9px;line-height:1.3;word-break:keep-all}}
.c.req{{background:#334A8E;border-color:#334A8E;color:#fff}}
.leg{{display:flex;gap:26px;align-items:center;margin-top:24px;font-size:17px;color:#5b6273}}
.leg span{{display:inline-block;width:22px;height:16px;border-radius:4px;margin-right:8px;vertical-align:-2px}}
.src{{margin-left:auto;font-size:15px;color:#8b91a1}}
</style></head><body><div id="c">
<div class="k">SEMYUNG UNIVERSITY · 재난안전학과</div>
<h1>4년 동안 무엇을 배우나</h1>
<div class="lead">재난을 예방·대비·대응·복구의 흐름으로 배우고, AI·빅데이터 같은 신기술을 재난 관리에 접목합니다</div>
<div class="bar"></div>
<div class="grid">{cols}</div>
<div class="leg"><div><span style="background:#334A8E"></span>전공필수</div><div><span style="background:#fff;border:1.5px solid #d9dfeb"></span>전공선택</div>
<div class="src">2026학년도 교육과정 기준 · 출처: 세명대학교 재난안전학과 홈페이지</div></div>
</div></body></html>"""
page = os.path.join(OUT, "curriculum.html"); open(page, "w", encoding="utf-8").write(html)
o = Options(); o.add_argument("--headless=new"); o.add_argument("--hide-scrollbars")
o.add_argument("--force-device-scale-factor=1"); o.add_argument("--disable-features=MacAppCodeSignClone")
d = webdriver.Chrome(options=o)
try:
    d.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {"width": 1200, "height": 1600, "deviceScaleFactor": 1, "mobile": False})
    d.get("file://" + page); time.sleep(1.5)
    print("fonts:", d.execute_script("return [...document.fonts].filter(f=>f.status=='loaded').map(f=>f.family).join(',')"))
    d.find_element(By.ID, "c").screenshot(os.path.join(OUT, "curriculum.png"))
finally:
    d.quit()
print("ok")
