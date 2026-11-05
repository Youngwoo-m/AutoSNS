from pathlib import Path
import sys,time,json
from selenium.webdriver.chrome.options import Options
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS');OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'dept/naver-blog-auto'))
from common import start_chrome
op=Options();op.add_argument('--headless=new');op.add_argument('--allow-file-access-from-files');op.add_argument('--window-size=1100,1050');op.add_argument('--hide-scrollbars')
d=start_chrome(op)
try:
 d.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{'width':1080,'height':1050,'deviceScaleFactor':1,'mobile':False})
 d.get((OUT/'미리보기.html').as_uri());time.sleep(.8)
 h=d.execute_script('return document.documentElement.scrollHeight')
 for name,y in [('top',0),('table',1500),('answer',int(h*.65)),('bottom',max(0,h-1050))]:
  d.execute_script('window.scrollTo(0,arguments[0])',y);time.sleep(.15);d.save_screenshot(str(OUT/f'HTML-preview-{name}.png'))
 d.execute_cdp_cmd('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':True})
 d.execute_script('window.scrollTo(0,0)');time.sleep(.2);d.save_screenshot(str(OUT/'HTML-preview-mobile.png'))
 metrics=d.execute_script('return {viewport:innerWidth,document:document.documentElement.scrollWidth}')
 (OUT/'preview-metrics.json').write_text(json.dumps({'desktop_height':h,'mobile':metrics},ensure_ascii=False,indent=2));print(json.dumps({'desktop_height':h,'mobile':metrics}))
finally:d.quit()
