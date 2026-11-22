"""계정별 크롬 실행 파일 — 2026-11-06 Mac 은퇴 후 Windows PC 기준.

학과 계정(semyungds) 크롬은 사용자 지정 실행 파일로 띄운다:
    C:\\Users\\ds2ey\\AppData\\Local\\Chromium\\Application\\chrome-dept.exe
환경변수 AX_CHROME_DEPT / AX_CHROME_PERSONAL 로 바꿀 수 있다. 개인 계정은 chrome-na.exe(같은 폴더)로 띄운다.

계정은 --user-data-dir(프로필 폴더)로 판단한다(axlock.ACCOUNT_OF/_LINKS 와 같은 구분).
axlock 을 import 하지 않는다(Windows 에서 fcntl 이 없어 import 가 실패할 수 있다).

    from shared.chrome_bin import apply, binary
    apply(options)                 # selenium Options: 학과 프로필이면 binary_location 을 학과 크롬으로
    binary("dept")                 # 직접 subprocess 로 띄울 때 실행 파일 경로(없으면 None)
"""
import os
import sys

_DEFAULTS = {
    "dept": r"C:\Users\ds2ey\AppData\Local\Chromium\Application\chrome-dept.exe",
    # 개인 계정(티스토리 na-geoai·네이버 safeworking·유튜브 @geoai-safety) — 2026-11-06 사용자 지정
    "personal": r"C:\Users\ds2ey\AppData\Local\Chromium\Application\chrome-na.exe",
}
_MAC_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 프로필 폴더 이름 → 계정 (axlock._LINKS 와 맞춘다)
_PERSONAL_DIRS = ("chrome-profile-safeworking", "chrome-profile-tistory", "chrome-profile-youtube")
_DEPT_DIRS = ("chrome-profile", "chrome-profile-insta", "chrome-profile-tiktok", "chrome-profile-youtube-dept")


def binary(account):
    """계정의 크롬 실행 파일. 지정이 없거나 파일이 없으면 None(셀레니움 기본 크롬)."""
    if account == "personal-tiktok":    # 2026-11-15 개인 틱톡 전용 프로필도 개인 크롬(chrome-na)으로 띄운다
        account = "personal"
    if account not in ("dept", "personal"):
        return None
    p = os.environ.get(f"AX_CHROME_{account.upper()}") or _DEFAULTS.get(account)
    if p:
        _refresh_copy(p)
    return p if p and os.path.exists(p) else None


def _refresh_copy(p):
    """chrome-dept.exe·chrome-na.exe 는 chrome.exe 복사본이다. Chromium 이 자동 업데이트하면 옛 버전 폴더가
    지워져 복사본이 켜지자마자 꺼진다(0xC0000034, 2026-11-21 157→158 때 틱톡 디버깅 포트 실패).
    같은 폴더 chrome.exe 와 크기·수정 시각이 다르면 다시 복사한다. 실행 중이라 못 덮으면 그대로 둔다."""
    src = os.path.join(os.path.dirname(p), "chrome.exe")
    if os.path.normcase(src) == os.path.normcase(p) or not os.path.exists(src):
        return
    try:
        a, b = os.stat(src), (os.stat(p) if os.path.exists(p) else None)
        if b and a.st_size == b.st_size and int(a.st_mtime) == int(b.st_mtime):
            return
        import shutil
        shutil.copy2(src, p)
    except OSError:
        pass


def default_chrome():
    """계정 지정 없이 직접 띄울 때 쓸 크롬(Windows: 학과 → 기본 설치 경로 순, Mac: 앱 번들)."""
    if sys.platform == "darwin":
        return _MAC_CHROME
    for p in (os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
              os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
              os.path.expandvars(r"%LocalAppData%\Chromium\Application\chrome.exe")):
        if os.path.exists(p):
            return p
    return "chrome"


def account_of_profile(path):
    """프로필 폴더 경로 → 'dept' | 'personal' | None."""
    if not path:
        return None
    norm = os.path.realpath(path).replace("\\", "/").rstrip("/")
    low = norm.lower()
    if "/.autosns-login/dept" in low:
        return "dept"
    if "/.autosns-login/personal" in low:
        return "personal"
    name = norm.rsplit("/", 1)[-1]
    if name in _PERSONAL_DIRS:
        return "personal"
    if name in _DEPT_DIRS or "/dept/insta-manual/" in low + "/":
        return "dept"
    return None


def account_of_options(options):
    for a in getattr(options, "arguments", []):
        if a.startswith("--user-data-dir="):
            return account_of_profile(a.split("=", 1)[1])
    return None


def apply(options, account=None):
    """학과(또는 지정된) 계정이면 options.binary_location 을 그 크롬으로. 이미 정해져 있으면 두지 않는다."""
    if getattr(options, "binary_location", ""):
        return options
    b = binary(account or account_of_options(options))
    if b:
        options.binary_location = b
    return options
