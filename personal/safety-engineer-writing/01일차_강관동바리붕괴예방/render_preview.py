from pathlib import Path
import sys,time
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS');OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'dept/naver-blog-auto'))
from common import start_chrome
from selenium.webdriver.chrome.options import Options
opt=Options();opt.add_argument('--headless=new');opt.add_argument('--window-size=1200,1000');opt.add_argument('--hide-scrollbars');opt.add_argument('--allow-file-access-from-files')
d=start_chrome(opt)
try:
 d.get((OUT/'미리보기.html').as_uri());time.sleep(.7)
 for name,selector in [('preview-top.png','h1'),('preview-intro.png','p small'),('preview-table.png','table'),('preview-answer.png','hr')]:
  node=d.find_element('css selector',selector);d.execute_script('arguments[0].scrollIntoView({block:"start"})',node);time.sleep(.2);d.save_screenshot(str(OUT/name))
finally:d.quit()
