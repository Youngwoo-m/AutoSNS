"""네이버 블로그 프로필 영역(프로필 이미지 · 소개글)을 갱신한다.

네이버 '블로그 정보' 페이지는 자체 JS 가 초기화 중 예외(setWordCheckObject)로 죽어서
'등록'·'확인' 버튼이 눌리지 않는다. 그래서 버튼을 쓰지 않고 같은 일을 직접 한다.

  1. 관리 SPA(/{blogId}/config/bloginfo) 안의 iframe#papermain 으로 들어간다.
     (저장 엔드포인트가 상대경로라 이 프레임 안에서 보내야 한다)
  2. AddProfileImageView.naver 팝업을 직접 열어 파일을 올린다.
     업로드 결과는 upload.blog.naver.com 이 postMessage 로 돌려준다
     (sFilePath / sFileName / nFileSize).
  3. 받은 값을 cgiform 의 img_path · image · img_size 에 넣고 소개글을 바꾼 뒤,
     폼 action(AdminUserBasicUpdate.naver — 직접 호출하면 거부된다) 이 아니라
     실제 저장 API 인 /UserBasicInfoUpdateAsync.naver 로 FormData 를 POST 한다.

블로그명·별명·주제 등 나머지 필드는 폼에 있던 값 그대로 함께 전송되므로 바뀌지 않는다.
'네이버 프로필에도 적용합니다' 가 켜져 있으면 네이버 프로필 사진도 같이 바뀐다.

사용:  ./.venv/bin/python naver_profile.py --image posts/profile_a.png --intro-file intro.txt
       (--image 나 --intro 중 하나만 줘도 된다)
"""
import argparse
import json
import os
import time

from selenium.webdriver.common.by import By

from common import BASE_DIR, load_config, log
from publish_naver import build_driver

# 블로그 주소(계정 ID 인 config.naver_id 와 다르다). 개인 계정(safeworking)은 AX_NAVER_BLOG_ID 로 바꾼다
BLOG_ID = os.environ.get("AX_NAVER_BLOG_ID") or "studs23"
UPLOAD_ORIGIN = "https://upload.blog.naver.com"
MAX_INTRO = 200              # 한글 기준 200자


def _enter_form(d):
    """관리 SPA 의 설정 폼 iframe 으로 들어간다."""
    d.switch_to.default_content()
    d.switch_to.frame(d.find_element(By.ID, "papermain"))


def _read(d):
    return d.execute_script(
        "var f=document.cgiform;"
        "return {img_path:f.img_path.value, img_size:f.img_size.value,"
        " introduce:f.introduce.value, papername:f.papername.value, nickname:f.nickname.value};")


def _upload_image(d, path):
    """프로필 이미지 업로드 팝업을 띄워 파일을 올리고 업로드 결과를 돌려준다."""
    d.execute_script("""
      var origin = arguments[0];
      window.__up = null;
      window.addEventListener('message', function(e){
        if (e.origin === origin && e.data && e.data.type === 'admin_profile_upload')
          window.__up = e.data;
      });
    """, UPLOAD_ORIGIN)
    d.execute_script("""
      var w = window.open('about:blank','addlink','width=420,height=360');
      w.location.href = gsMylogURL + "/AddProfileImageView.naver?blogId=" + gsPaperId
          + "#origin=" + window.location.origin + "&token=" + blogUtil.makeToken();
    """)
    time.sleep(5)
    main = d.current_window_handle
    pop = [h for h in d.window_handles if h != main][0]
    d.switch_to.window(pop)
    time.sleep(2)
    d.find_element(By.NAME, "file1").send_keys(path)
    time.sleep(1)
    d.find_element(By.ID, "submitBtn").click()
    time.sleep(9)
    if pop in d.window_handles:
        d.switch_to.window(pop)
        d.close()
    d.switch_to.window(main)
    time.sleep(1)
    _enter_form(d)
    return d.execute_script("return window.__up")


def _save(d, intro):
    """폼 값을 실제 저장 API 로 보낸다(확인 버튼이 하는 일과 동일)."""
    return d.execute_async_script("""
      var intro = arguments[0], blogId = arguments[1], done = arguments[2];
      var f = document.cgiform, u = window.__up;
      if (u) { f.img_path.value = u.sFilePath; f.image.value = u.sFileName; f.img_size.value = u.nFileSize; }
      if (intro !== null) f.introduce.value = intro;
      fetch('/UserBasicInfoUpdateAsync.naver?blogId=' + blogId,
            {method:'POST', body:new FormData(f), credentials:'include'})
        .then(function(r){ return r.text().then(function(t){ done({status:r.status, body:t}); }); })
        .catch(function(e){ done({error:String(e)}); });
    """, intro, BLOG_ID)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", help="프로필 이미지 파일(파일명은 영문·숫자로)")
    ap.add_argument("--intro", help="소개글 텍스트")
    ap.add_argument("--intro-file", help="소개글이 든 텍스트 파일")
    ap.add_argument("--dry-run", action="store_true", help="폼 값만 읽고 저장하지 않는다")
    a = ap.parse_args()

    intro = a.intro
    if a.intro_file:
        with open(a.intro_file, encoding="utf-8") as f:
            intro = f.read().strip()
    if intro and len(intro) > MAX_INTRO:
        raise SystemExit(f"소개글이 {len(intro)}자입니다 — {MAX_INTRO}자 이내로 줄여주세요")
    image = a.image and os.path.abspath(os.path.join(BASE_DIR, a.image))
    if image and not os.path.exists(image):
        raise SystemExit(f"이미지가 없습니다: {image}")
    if not image and intro is None and not a.dry_run:
        raise SystemExit("--image 또는 --intro/--intro-file 중 하나는 필요합니다")

    cfg = load_config()
    d = build_driver(headless=cfg.get("publish", {}).get("headless", False))
    try:
        d.get(f"https://admin.blog.naver.com/{BLOG_ID}/config/bloginfo")
        time.sleep(12)
        _enter_form(d)
        log("변경 전: " + json.dumps(_read(d), ensure_ascii=False)[:200])
        if a.dry_run:
            return

        if image:
            up = _upload_image(d, image)
            if not up:
                raise SystemExit("❌ 업로드 결과를 받지 못했습니다 — 저장하지 않고 중단합니다")
            log(f"업로드 완료: {up['sFileName']} ({up['nWidth']}x{up['nHeight']})")

        res = _save(d, intro)
        log("저장 응답: " + json.dumps(res, ensure_ascii=False)[:200])
        if "success" not in json.dumps(res, ensure_ascii=False):
            raise SystemExit("❌ 저장에 실패했습니다")

        d.get(f"https://admin.blog.naver.com/{BLOG_ID}/config/bloginfo")
        time.sleep(12)
        _enter_form(d)
        log("변경 후: " + json.dumps(_read(d), ensure_ascii=False)[:400])
        log("✅ 프로필 갱신 완료")
    finally:
        d.quit()


if __name__ == "__main__":
    main()
