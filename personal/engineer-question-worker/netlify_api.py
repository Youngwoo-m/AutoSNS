import json, urllib.request, urllib.error
from pathlib import Path
SITE_ID = "2b48a04b-d979-4a63-bc37-a83659678647"
SITE_DIR = Path(__file__).resolve().parent.parent / "geoai-site"

def api(path, method="GET", data=None, content_type="application/json"):
    config = json.loads((Path.home() / "Library/Preferences/netlify/config.json").read_text())
    user = config["users"][config["userId"]]
    token = user.get("auth", {}).get("token") or user.get("token")
    if not token:
        raise RuntimeError("Netlify 로그인 토큰을 찾지 못했습니다")
    if isinstance(data, dict): data = json.dumps(data).encode()
    req = urllib.request.Request("https://api.netlify.com/api/v1" + path, data=data, method=method,
        headers={"Authorization": "Bearer " + token, "Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            raw=res.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Netlify API 오류 {e.code}: {e.read().decode()[:500]}") from None
