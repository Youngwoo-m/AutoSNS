"""현재 로그인 창의 다른 사이트 쿠키를 지우지 않고 티스토리 세션만 저장·재검증."""
from pathlib import Path
import sys,json,datetime
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS')
sys.path.insert(0,str(ROOT/'dept/naver-blog-auto'))
import tistory_crosspost as tc
import tistory_login as login
original_build=tc.build_driver
original_restore=tc.restore_cookies
calls=0

def build(headless):
 global calls
 calls+=1
 if calls>1:
  return original_build(headless)
 # Do not overwrite the person's freshly authenticated profile with old saved cookies.
 tc.restore_cookies=lambda driver:0
 try:driver=original_build(headless)
 finally:tc.restore_cookies=original_restore
 execute=driver.execute_cdp_cmd
 def preserved(method,params):
  if method=='Network.clearBrowserCookies':
   # Refresh Tistory only; preserve Kakao, Google and Naver sessions.
   for cookie in execute('Network.getAllCookies',{}).get('cookies',[]):
    if cookie.get('domain','').lstrip('.').endswith('tistory.com'):
     execute('Network.deleteCookies',{'name':cookie['name'],'domain':cookie['domain'],'path':cookie.get('path','/')})
   return {}
  return execute(method,params)
 driver.execute_cdp_cmd=preserved
 return driver

login.build_driver=build
login.main()
# Only record whether the tool actually reopened and verified, never cookie data.
out=ROOT/'GeoAI_NA/claude-jobs/recovery/2026-10-31/registration/login-tool-result.json'
out.write_text(json.dumps({'at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),'browser_open_count':calls,'cookie_values_logged':False,'other_site_cookies_cleared':False,'note':'See login tool output for reopened session verification'},ensure_ascii=False,indent=2))
