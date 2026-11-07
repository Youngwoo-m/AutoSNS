"""카카오톡 '나에게 보내기' 알림 토큰(KAKAO_TOKEN) 최초 인증 — 사용자가 직접 1회 실행 (2026-11-06, Windows).

    personal\\geoai-youtube\\.venv\\Scripts\\python.exe common\\tools\\kakao_auth_setup.py

1. 카카오 개발자 앱의 REST API 키와 Client Secret 을 입력받는다(화면에 보이지 않음).
2. 개인 크롬(chrome-na.exe)으로 카카오 로그인·동의 화면을 연다(scope: talk_message).
3. http://localhost:5174/kakao 로 돌아온 인가 코드를 토큰으로 바꿔 암호화 저장소(KAKAO_TOKEN)에 넣는다.
4. access_token_info 로 토큰이 살아 있는지만 확인한다 — 메시지는 보내지 않는다.

카카오 개발자 콘솔 > 앱 > 카카오 로그인 > Redirect URI 에 http://localhost:5174/kakao 가 등록돼 있어야 한다.
"""
import getpass
import http.server
import json
import os
import secrets
import subprocess
import sys
import urllib.parse
import urllib.request
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, ROOT)
from shared import token_store  # noqa: E402
from shared.kakao_notify import TOKEN_PATH  # noqa: E402

PORT = 5174
REDIRECT = f"http://localhost:{PORT}/kakao"
CHROME_NA = os.environ.get("AX_CHROME_PERSONAL",
                           r"C:\Users\ds2ey\AppData\Local\Chromium\Application\chrome-na.exe")


def _post(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        return json.load(r)


def main():
    if token_store.read_text(TOKEN_PATH):
        if input("KAKAO_TOKEN 이 이미 있습니다. 다시 인증할까요? [y/N] ").strip().lower() not in ("y", "yes"):
            raise SystemExit("취소했습니다.")
    client_id = getpass.getpass("카카오 REST API 키: ").strip()
    client_secret = getpass.getpass("Client Secret (없으면 Enter): ").strip()
    if not client_id:
        raise SystemExit("REST API 키가 비어 있습니다.")

    state = secrets.token_urlsafe(16)
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if not self.path.startswith("/kakao"):
                self.send_response(404); self.end_headers(); return
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "카카오 인증이 끝났습니다. 이 창을 닫아도 됩니다." if "code" in got else "인증이 취소되었거나 실패했습니다."
            self.wfile.write(f"<p style='font-family:sans-serif'>{msg}</p>".encode())

        def log_message(self, *a):
            pass

    # Windows 는 allow_reuse_address 면 같은 포트를 두 프로세스가 잡아 응답이 엉뚱한 쪽으로 간다(2026-11-06 실제 발생)
    http.server.HTTPServer.allow_reuse_address = False
    try:
        srv = http.server.HTTPServer(("127.0.0.1", PORT), H)
    except OSError:
        raise SystemExit(f"포트 {PORT} 를 다른 프로그램이 쓰고 있습니다 — 앞서 띄운 인증 창(터미널)을 Ctrl+C 로 끄고 다시 실행하세요.")
    url = "https://kauth.kakao.com/oauth/authorize?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT,
        "scope": "talk_message", "state": state, "prompt": "select_account"})
    print("카카오 로그인 창을 엽니다. 알림을 받을 개인 카카오 계정으로 로그인하고 '카카오톡 메시지 전송'에 동의하세요.")
    if os.path.exists(CHROME_NA):
        subprocess.Popen([CHROME_NA, "--profile-directory=Default", url])
    else:
        webbrowser.open(url)
    while "code" not in got and "error" not in got:
        srv.handle_request()
    srv.server_close()
    if got.get("state") != state:
        raise SystemExit("state 가 맞지 않습니다 — 다시 실행하세요.")
    if "error" in got:
        raise SystemExit(f"카카오 인증 실패: {got.get('error')} {got.get('error_description', '')}")

    fields = {"grant_type": "authorization_code", "client_id": client_id,
              "redirect_uri": REDIRECT, "code": got["code"]}
    if client_secret:
        fields["client_secret"] = client_secret
    try:
        d = _post("https://kauth.kakao.com/oauth/token", fields)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"토큰 교환 실패: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:200]}")
    tok = {"client_id": client_id, "client_secret": client_secret,
           "access_token": d["access_token"], "refresh_token": d.get("refresh_token", "")}
    where = token_store.write_json(TOKEN_PATH, tok)
    print("토큰 저장:", token_store.name_for(TOKEN_PATH), f"({where})")
    print("받은 권한:", d.get("scope", "(알 수 없음)"))

    req = urllib.request.Request("https://kapi.kakao.com/v1/user/access_token_info",
                                 headers={"Authorization": "Bearer " + d["access_token"]})
    with urllib.request.urlopen(req, timeout=15) as r:
        info = json.load(r)
    print(f"토큰 확인 완료 — 앱 ID {info.get('app_id')}, 남은 시간 {int(info.get('expires_in', 0)) // 60}분"
          f"(만료되면 refresh_token 으로 자동 갱신)")


if __name__ == "__main__":
    main()
