"""암호화된 환경설정(secrets.env.enc) 읽기·쓰기.

- 값은 AutoSNS/secrets.env.enc 에 Fernet(AES + HMAC)으로 암호화해 둔다.
- 여는 열쇠는 macOS 키체인(서비스 autosns-secrets)에만 있다. 파일만 복사해 가면 못 연다.
- 한 줄에 하나씩 `이름=값(JSON 문자열)` 로 저장한다(값에 #, =, 공백이 있어도 안전).

코드에서:
    from shared import secret_env
    secret_env.load()                 # os.environ 에 채움(이미 있는 값은 덮어쓰지 않음)
    key = secret_env.get("GAMMA_API_KEY")

터미널에서:
    python -m shared.secret_env names           # 이름만 보기
    python -m shared.secret_env get NAME        # 값 출력(스크립트용)
    python -m shared.secret_env set NAME        # 값을 입력받아 저장(화면에 안 보임)
    python -m shared.secret_env delete NAME
"""
import getpass
import json
import os
import subprocess
import sys

from cryptography.fernet import Fernet

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE = os.path.join(ROOT, "secrets.env.enc")
SERVICE, ACCOUNT = "autosns-secrets", "autosns"


def _key(create=False):
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", ACCOUNT, "-w"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip().encode()
    if not create:
        raise SystemExit("키체인에 autosns-secrets 열쇠가 없습니다(다른 Mac 이면 열쇠를 옮겨야 합니다).")
    k = Fernet.generate_key()
    subprocess.run(["security", "add-generic-password", "-U", "-s", SERVICE, "-a", ACCOUNT,
                    "-l", "AutoSNS 환경설정 암호화 열쇠", "-w", k.decode()], check=True)
    return k


def read():
    if not os.path.exists(FILE):
        return {}
    text = Fernet(_key()).decrypt(open(FILE, "rb").read()).decode("utf-8")
    out = {}
    for line in text.splitlines():
        if line and not line.startswith("#") and "=" in line:
            name, val = line.split("=", 1)
            out[name] = json.loads(val)
    return out


def write(values):
    body = "\n".join(f"{k}={json.dumps(v, ensure_ascii=False)}" for k, v in values.items()) + "\n"
    tmp = FILE + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
        f.write(Fernet(_key(create=True)).encrypt(body.encode("utf-8")))
    os.replace(tmp, FILE)


def update(values=None, remove=()):
    """잠금을 잡고 읽고-고치고-쓴다. 발행 중 토큰 갱신과 사람이 넣는 값이 겹쳐도
    서로 지우지 않게 한다(write 는 통째로 덮어쓴다)."""
    import fcntl
    with open(FILE + ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        vals = read()
        vals.update(values or {})
        for k in remove:
            vals.pop(k, None)
        write(vals)
    return vals


def get(name, default=None):
    return os.environ.get(name) or read().get(name, default)


def load(override=False):
    vals = read()
    for k, v in vals.items():
        if override or k not in os.environ:
            os.environ[k] = v
    return list(vals)


def main(argv):
    cmd = argv[0] if argv else "names"
    if cmd == "names":
        for k in read():
            print(k)
    elif cmd == "get" and len(argv) == 2:
        v = read().get(argv[1])
        if v is None:
            raise SystemExit(f"{argv[1]} 없음")
        print(v)
    elif cmd == "set" and len(argv) == 2:
        vals = read()
        vals[argv[1]] = getpass.getpass(f"{argv[1]} 값: ")
        write(vals)
        print(f"{argv[1]} 저장")
    elif cmd == "delete" and len(argv) == 2:
        vals = read()
        vals.pop(argv[1], None)
        write(vals)
        print(f"{argv[1]} 삭제")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
