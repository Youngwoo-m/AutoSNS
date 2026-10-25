"""사이트 + Netlify 함수(geoai-functions/*.js) 함께 배포 — 파일 목록(digest) 방식.

deploy.py(zip 업로드)는 함수를 올리지 못해서, 기상특보 중계 함수(/.netlify/functions/wthr)가
생긴 뒤로는 이 스크립트로 배포한다. 바뀐 파일만 올라가서 zip 보다 가볍다.

  python3 deploy_full.py          # 배포
  python3 deploy_full.py --check  # 무엇이 올라갈지만 보고 끝(배포 안 함)

함수가 쓰는 키(공공데이터포털 DATA_GO_KR_KEY, 카카오 KAKAO_REST_KEY)는 암호화 저장소(secrets.env.enc)에서 읽어
Netlify 사이트 환경변수로 한 번 넣어 둔다 — 사이트 파일에는 들어가지 않는다.
"""
import hashlib, io, json, sys, time, urllib.parse, zipfile
from pathlib import Path
from netlify_api import api, SITE_ID, SITE_DIR

# geoai-site 는 GeoAI_NA 로 옮긴 뒤 원래 자리(AutoSNS/site/geoai-site)를 가리키는 링크다(2026-10-17 이전).
# 링크를 풀어야 함수 폴더(AutoSNS/site/geoai-functions)를 찾는다 — 못 찾으면 함수 없이 배포돼 학식·특보가 사라진다.
FUNC_DIR = SITE_DIR.resolve().parent / "geoai-functions"


def site_files():
    files = {}
    for path in sorted(SITE_DIR.rglob("*")):
        rel = path.relative_to(SITE_DIR)
        if path.is_file() and not any(part.startswith(".") for part in rel.parts):
            files["/" + rel.as_posix()] = path
    return files


def function_zips():
    out = {}
    for f in sorted(FUNC_DIR.glob("*.js")):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            info = zipfile.ZipInfo(f.name, date_time=(2026, 1, 1, 0, 0, 0))  # 내용이 같으면 해시도 같게
            z.writestr(info, f.read_bytes())
        out[f.stem] = buf.getvalue()
    return out


ENV_KEYS = ("DATA_GO_KR_KEY", "KAKAO_REST_KEY")   # 기상특보(wthr) · 카카오 대중교통 길찾기(kroute)


def ensure_env():
    """함수용 환경변수(ENV_KEYS)가 사이트에 없으면 암호화 저장소 값으로 넣는다."""
    # 키는 암호화 저장소에 있다(2026-10-17 AutoSNS/.env 에서 옮김).
    sys.path.insert(0, str(SITE_DIR.parent))
    from shared.secret_get import get
    env = {k: get(k) or "" for k in ENV_KEYS}
    account = api("/sites/" + SITE_ID)["account_id"]
    have = {v.get("key") for v in (api(f"/accounts/{account}/env?site_id={SITE_ID}") or [])}
    out = {}
    for k in ENV_KEYS:
        val = env.get(k, "").strip().strip('"').strip("'")
        if not val:
            raise SystemExit(f"암호화 저장소에 {k} 가 없습니다")
        if k in have:
            out[k] = "있음"; continue
        api(f"/accounts/{account}/env?site_id={SITE_ID}", "POST",
            # 무료 플랜은 scopes(함수 전용) 지정이 막혀 있어 기본 범위로 넣는다 — 그래도 사이트 파일엔 안 들어간다
            json.dumps([{"key": k, "values": [{"value": val, "context": "all"}]}]).encode())
        out[k] = "새로 넣음"
    return out


def deploy(check=False):
    files = site_files()
    digests = {p: hashlib.sha1(f.read_bytes()).hexdigest() for p, f in files.items()}
    funcs = function_zips()
    if not funcs:   # 함수 없이 올리면 Netlify 가 기존 함수를 지운다(2026-10-18 학식·특보 중단 사례)
        raise SystemExit(f"함수를 찾지 못했습니다({FUNC_DIR}) — 배포 중단")
    fdig = {name: hashlib.sha256(z).hexdigest() for name, z in funcs.items()}
    print(f"파일 {len(files)}개, 함수 {list(funcs)}")
    if check:
        return
    print("환경변수:", ensure_env())
    d = api(f"/sites/{SITE_ID}/deploys?title=" + urllib.parse.quote("dinner-roulette+functions"), "POST",
            {"files": digests, "functions": fdig})
    did = d["id"]
    need = set(d.get("required") or [])
    for p, f in files.items():
        if digests[p] in need:
            api(f"/deploys/{did}/files{urllib.parse.quote(p)}", "PUT", f.read_bytes(), "application/octet-stream")
            print("  올림", p)
    need_f = set(d.get("required_functions") or [])
    for name, z in funcs.items():
        if fdig[name] in need_f:
            api(f"/deploys/{did}/functions/{name}?runtime=js", "PUT", z, "application/octet-stream")
            print("  함수 올림", name)
    for _ in range(40):
        cur = api("/deploys/" + did)
        if cur["state"] == "ready":
            print(json.dumps({"state": "ready", "url": cur.get("ssl_url"), "deploy_url": cur.get("deploy_ssl_url")},
                             ensure_ascii=False))
            return cur
        if cur["state"] == "error":
            raise RuntimeError(cur.get("error_message", "Deploy failed"))
        time.sleep(3)
    raise RuntimeError("배포 확인 시간 초과: " + did)


if __name__ == "__main__":
    deploy(check="--check" in sys.argv)
