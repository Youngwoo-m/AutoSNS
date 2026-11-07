"""채널별 계정 연결 상태 점검 — 읽기 전용(2026-11-06, Mac 은퇴 후 Windows 이전용).

무엇을 보나(값은 읽거나 출력하지 않는다):
  - 토큰형 채널: 암호화 저장소(secrets.env.enc)에 그 이름이 있는지 (shared/token_store.NAMES)
  - 브라우저 로그인형 채널: 자동화 전용 프로필(~/.autosns-login/<계정>)의 쿠키 DB 에 로그인 쿠키 이름이 있는지
    (쿠키 값은 암호화돼 있어 읽지 않는다. 크롬이 열려 있어도 되도록 DB 를 임시 사본으로 읽는다)
  - 학과 크롬 실행 파일(chrome_bin)

    python common/tools/check_connections.py            # 표
    python common/tools/check_connections.py --json     # 기계용

상태: ok(연결됨) · missing(없음 → '할 일' 참고) · unknown(확인 불가)
"""
import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
LOGIN = Path.home() / ".autosns-login"

# (계정, 채널, 종류, 확인 대상, 할 일)
CHECKS = [
    ("common", "Google OAuth 앱", "secret", ["GOOGLE_OAUTH_CLIENT"],
     "Google Cloud 콘솔에서 OAuth 클라이언트 JSON 을 내려받아 저장소에 넣기(학과 smuds-501923 · 개인 GeoAI 프로젝트)"),
    ("dept", "유튜브(@smds2023)", "secret", ["YOUTUBE_TOKEN_DEPT"],
     "dept/youtube-shorts-auto/youtube_login_setup.py — semyungds 계정으로 동의"),
    ("dept", "유튜브 공개 상태 관리", "secret", ["YOUTUBE_TOKEN_MANAGE"], "set_video_privacy 용 force-ssl 토큰 재발급"),
    ("dept", "Blogger(smuds2026)", "secret", ["BLOGGER_TOKEN_GEOAI", "BLOGGER_TOKEN_DEPT"],
     "dept/naver-blog-auto/blogger_auth_setup.py (config.blogger.token_file 이 가리키는 계정)"),
    ("dept", "네이버 블로그(studs23)", "cookie", ("dept", [(".naver.com", "NID_AUT")]),
     "dept/naver-blog-auto/login_setup.py — 학과 크롬으로 네이버 로그인"),
    ("dept", "인스타그램", "cookie", ("dept", [(".instagram.com", "sessionid")]),
     "dept/insta-cardnews/login_setup_insta.py"),
    ("dept", "인스타 비밀값", "secret", ["INSTAGRAM_ID", "INSTAGRAM_PW"], "python -m shared.secret_env set INSTAGRAM_ID / INSTAGRAM_PW"),
    # 스레드는 API 앱 미설정(config.threads.app_id 없음) — 학과 브라우저 로그인 세션으로 올린다
    ("dept", "스레드", "cookie", ("dept", [(".threads.com", "sessionid"), (".threads.net", "sessionid")]),
     "바탕화면 '학과 크롬 (AutoSNS)' 에서 threads.com 에 인스타 계정으로 로그인"),
    ("dept", "틱톡 API", "secret", ["TIKTOK_TOKEN", "TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"],
     "dept/youtube-shorts-auto/tiktok_login_setup.py"),
    ("dept", "틱톡 웹 업로드", "cookie", ("dept", [(".tiktok.com", "sessionid")]),
     "dept/youtube-shorts-auto/tiktok_web_login.py"),
    ("dept", "X(트위터)", "secret", ["X_TOKEN", "X_OAUTH2_CLIENT_ID"], "X OAuth2 재인증(x_post.py 안내)"),
    ("dept", "유튜브 브라우저(댓글 고정)", "cookie", ("dept", [(".youtube.com", "SAPISID"), (".google.com", "SAPISID")]),
     "dept/youtube-shorts-auto/pin_comment.py login"),
    ("personal", "유튜브(@geoai-safety)", "secret", ["YOUTUBE_TOKEN_GEOAI"],
     "personal/geoai-youtube/geoai_youtube_auth.py — ds2eye 계정으로 동의"),
    ("personal", "Blogger(geoaina)", "secret", ["BLOGGER_TOKEN_GEOAI"], "personal/naver-blog-auto/geoai_auth_setup.py"),
    ("personal", "티스토리(na-geoai)", "cookie", ("personal", [(".tistory.com", "TSSESSION")]),
     "personal/naver-blog-auto/tistory_login.py — 카카오 계정으로 로그인"),
    ("personal", "네이버 safeworking", "cookie", ("personal", [(".naver.com", "NID_AUT")]),
     "dept/naver-blog-auto/login_setup_safeworking.py"),
    ("personal", "유튜브 브라우저(게시물)", "cookie", ("personal", [(".youtube.com", "SAPISID"), (".google.com", "SAPISID")]),
     "personal/geoai-youtube/geoai_community_login.py"),
    ("personal", "카카오 알림", "secret", ["KAKAO_TOKEN"], "카카오 '나에게 보내기' 토큰 재발급(kakao_notify 안내)"),
]


def _store_names():
    try:
        from shared import secret_env
        return set(secret_env.read()), ""
    except SystemExit as e:
        return None, str(e)
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _cookie_names(account):
    """(host, name) 집합. 프로필이 없으면 None."""
    base = LOGIN / account
    found = set()
    dbs = list(base.glob("*/Network/Cookies")) + list(base.glob("*/Cookies"))
    if not dbs:
        return None
    for db in dbs:
        tmp = Path(tempfile.mkdtemp()) / "c.db"
        try:
            shutil.copy2(db, tmp)
            con = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
            try:
                found |= set(con.execute("select host_key, name from cookies"))
            finally:
                con.close()
        except PermissionError:      # Windows: 크롬이 열려 있으면 쿠키 DB 가 잠겨 복사도 안 된다
            return "locked"
        except Exception:  # noqa: BLE001
            continue
        finally:
            shutil.rmtree(tmp.parent, ignore_errors=True)
    return found


def run():
    names, store_err = _store_names()
    cookies = {}
    rows = []
    for acct, ch, kind, target, todo in CHECKS:
        if kind == "secret":
            if names is None:
                st, why = "unknown", f"저장소를 못 엶: {store_err[:80]}"
            else:
                miss = [n for n in target if n not in names]
                ok_any = any(n in names for n in target) if ch.startswith("Blogger(smuds") else not miss
                st, why = ("ok", "") if ok_any else ("missing", "없음: " + ", ".join(miss))
        else:
            prof, want = target
            if prof not in cookies:
                cookies[prof] = _cookie_names(prof)
            have = cookies[prof]
            if have == "locked":
                st, why = "unknown", "크롬이 열려 있어 확인 불가 — 창을 닫고 다시 점검"
            elif have is None:
                st, why = "missing", f"자동화 프로필 없음({LOGIN / prof})"
            else:
                hit = any((h, n) in have for h, n in want)
                st, why = ("ok", "") if hit else ("missing", "로그인 쿠키 없음")
        rows.append({"account": acct, "channel": ch, "status": st, "why": why, "todo": "" if st == "ok" else todo})
    try:
        from shared import chrome_bin
        rows.append({"account": "dept", "channel": "학과 크롬 실행 파일", "status": "ok" if chrome_bin.binary("dept") else "missing",
                     "why": chrome_bin.binary("dept") or "chrome-dept.exe 없음", "todo": ""})
        rows.append({"account": "personal", "channel": "개인 크롬 실행 파일", "status": "ok" if chrome_bin.binary("personal") else "missing",
                     "why": chrome_bin.binary("personal") or "지정 없음(기본 크롬)", "todo": ""})
    except Exception as e:  # noqa: BLE001
        rows.append({"account": "common", "channel": "크롬 실행 파일", "status": "unknown", "why": str(e)[:80], "todo": ""})
    return rows


def main():
    ap = argparse.ArgumentParser(description="채널별 계정 연결 점검(읽기 전용)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    rows = run()
    if a.json:
        print(json.dumps(rows, ensure_ascii=False))
        return 0
    mark = {"ok": "✅", "missing": "❌", "unknown": "❔"}
    for r in rows:
        print(f"{mark[r['status']]} [{r['account']:8}] {r['channel']:22} {r['why']}")
        if r["todo"]:
            print(f"      → {r['todo']}")
    n = sum(r["status"] == "ok" for r in rows)
    print(f"\n연결됨 {n}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
