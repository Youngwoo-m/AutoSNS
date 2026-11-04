"""Firebase(geoai-na) 연결: 문제 접수분 가져오기 + 사이트·함수 배포.
수집 키 COLLECTOR_KEY 는 암호화 저장소(shared.secret_env)에서 읽는다. 값은 코드·로그에 남기지 않는다."""
import json, shutil, subprocess, sys, urllib.request
from pathlib import Path
SITE_DIR = Path(__file__).resolve().parent.parent.parent / "site" / "geoai-site"
BASE = "https://geoai-na.web.app/fn/collect"
FIREBASE = shutil.which("firebase") or "/usr/local/lib/nodejs/node-v24.21.0-darwin-x64/bin/firebase"

def _key():
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root / "common"))
    from shared import secret_env
    key = secret_env.get("COLLECTOR_KEY")
    if not key: raise RuntimeError("COLLECTOR_KEY 가 암호화 저장소에 없습니다")
    return key

def collect(form):
    req = urllib.request.Request(f"{BASE}?form={form}", headers={"x-collector-key": _key()})
    with urllib.request.urlopen(req, timeout=60) as r: return json.loads(r.read())

def deploy(only="hosting,functions,firestore:rules"):
    subprocess.run([FIREBASE, "deploy", "--only", only, "--project", "geoai-na", "--non-interactive"], cwd=SITE_DIR, check=True)
