"""네이버 붙여넣기 실패 원인 조사용 시험(발행하지 않음). 2026-11-25.
글쓰기 화면을 새로 열어 제목 입력 → 본문 붙여넣기를 N번 반복하고, 어느 단계에서 글자가 사라지는지 기록한다.
    python tools_probe_paste.py [횟수]
"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.realpath(os.path.join(HERE, "..", ".."))
os.environ["AX_NAVER_PROFILE"] = os.path.join(ROOT, "dept", "naver-blog-auto", "chrome-profile-safeworking")
os.environ["AX_NAVER_ID"] = "safeworking"
os.environ.setdefault("PYTHONUTF8", "1")
sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
os.chdir(HERE)
import publish_naver as pn
import naver_paste as np_
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from shared.axlock import hold

STATE_JS = """
var t=document.querySelector('.se-section-documentTitle .se-text-paragraph');
var a=document.activeElement;
return {title:t?t.innerText.trim():null, hasFocus:document.hasFocus(),
 active:a?(a.tagName+'.'+(a.className||'').toString().slice(0,60)):null,
 popups:[...document.querySelectorAll('[class*=se-popup]')].filter(p=>p.offsetParent).map(p=>p.innerText.slice(0,60)),
 body:[...document.querySelectorAll('.se-content .se-text-paragraph')].map(p=>p.innerText.trim()).join('|').slice(0,120)};
"""


def trial(n):
    rec = {"n": n, "t": []}
    d = pn.build_driver(headless=True)
    if os.environ.get("PROBE_FOCUS_EMU") == "1":
        d.execute_cdp_cmd("Emulation.setFocusEmulationEnabled", {"enabled": True})
    try:
        t0 = time.time()
        d.get("https://blog.naver.com/GoBlogWrite.naver?blogId=safeworking")
        time.sleep(5)
        WebDriverWait(d, 20).until(EC.frame_to_be_available_and_switch_to_it((By.ID, "mainFrame")))
        time.sleep(3)
        rec["draft_popup"] = pn.dismiss_draft_popup(d, wait=8)
        pn.click_if_present(d, By.CSS_SELECTOR, ".se-help-panel-close-button", timeout=2)
        time.sleep(1)
        title = WebDriverWait(d, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".se-section-documentTitle .se-text-paragraph")))
        rec["before_title"] = d.execute_script(STATE_JS)
        clicks = 0
        for clicks in range(1, 6):          # 입력 iframe 으로 포커스가 갈 때까지 다시 누른다
            ActionChains(d).move_to_element(title).click().perform()
            time.sleep(0.5)
            if d.execute_script("return (document.activeElement||{}).tagName") == "IFRAME":
                break
            time.sleep(1)
        rec["title_clicks"] = clicks
        ActionChains(d).send_keys(f"붙여넣기 시험 {n}").perform()
        for s in (0, 1, 2):          # 입력 직후, 1초 뒤, 3초 뒤
            time.sleep(s)
            rec["t"].append([round(time.time() - t0, 1), d.execute_script(STATE_JS)])
        el = d.find_elements(By.CSS_SELECTOR, ".se-content .se-component.se-text .se-text-paragraph")[-1]
        ActionChains(d).move_to_element(el).click().perform()
        time.sleep(0.5)
        rec["body_active"] = d.execute_script("return (document.activeElement||{}).tagName")
        rec["synthetic"] = d.execute_script("""
var f=document.activeElement; if(!f||f.tagName!=='IFRAME') return 'no-iframe';
var doc=f.contentDocument; var tgt=doc.activeElement||doc.body;
var dt=new DataTransfer(); dt.setData('text/html',arguments[0]); dt.setData('text/plain','x');
var ev=new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true});
var r=tgt.dispatchEvent(ev); return tgt.tagName+' handled='+(!r);""", "<p>시험 본문 첫 줄</p><p>[[AXIMG0]]</p>")
        time.sleep(3)
        rec["after_paste"] = d.execute_script(STATE_JS)
        rec["ok_title"] = (rec["after_paste"]["title"] or "").startswith("붙여넣기 시험")
        rec["ok_paste"] = "[[AXIMG0]]" in (rec["after_paste"]["body"] or "")
        if not (rec["ok_title"] and rec["ok_paste"]):
            pn.shot(d, f"probe{n}_fail")
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"[:300]
    finally:
        try:
            d.quit()
        except Exception:  # noqa: BLE001
            pass
    return rec


if __name__ == "__main__":
    N = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    with hold(["profile:safeworking"], job="probe:naver-paste", wait=1800):
        os.environ["AX_LOCKED"] = "1"
        for i in range(1, N + 1):
            r = trial(i)
            print(json.dumps(r, ensure_ascii=False), flush=True)
