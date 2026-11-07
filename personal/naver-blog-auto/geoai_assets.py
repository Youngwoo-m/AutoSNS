"""카드뉴스 PNG 를 공개 GitHub 저장소에 올리고 CDN 주소를 돌려준다.

왜 필요한가: Blogger API v3 에는 이미지 업로드가 없다. 글 본문에 <img> 로 걸려면
이미지가 이미 어딘가에 공개돼 있어야 한다. 그래서 공개 저장소를 이미지 호스트로 쓰고
jsDelivr CDN 주소로 건다(무료·안정적, 깃허브 raw 보다 이미지 전송에 적합).

인증은 gh CLI 를 그대로 쓴다(이미 로그인돼 있다). 파일은 Contents API 로 올리므로
저장소를 따로 클론해 두지 않는다.

주의: 여기 올라간 이미지는 공개된다. 공개해도 되는 카드뉴스만 넣는다.
"""
import base64
import json
import os
import shutil
import subprocess

from common import POSTS_DIR, load_config, log


def _acfg(cfg=None):
    return ((cfg or load_config()).get("geoai") or {}).get("assets") or {}


def _gh_bin():
    """gh 실행 파일 경로. launchd 로 돌면 PATH 가 최소라 이름만으로는 못 찾는다
    (2026-09-17 아침 발행에서 FileNotFoundError: 'gh' 로 배너가 통째로 빠졌다)."""
    found = shutil.which("gh")
    if found:
        return found
    for c in ("/opt/homebrew/bin/gh", "/usr/local/bin/gh", "/usr/bin/gh",
              os.path.expanduser("~/.local/bin/gh")):
        if os.path.exists(c):
            return c
    return "gh"


def _owner_env():
    """저장소 주인 계정의 토큰으로 gh 를 부른다. gh 기본 계정을 바꿔도(콘솔에서 전환)
    업로드가 깨지지 않게 하려는 것(2026-10-17 기본 계정이 Youngwoo-m 으로 바뀐 뒤
    SMUDS-m/geoai-assets 업로드가 404 로 모두 실패했다). 토큰을 못 얻으면 기본 계정으로 간다."""
    a = _acfg()
    user = a.get("account") or (a.get("repo") or "").split("/")[0]
    if not user:
        return None
    t = subprocess.run([_gh_bin(), "auth", "token", "--user", user], capture_output=True, text=True, timeout=30)
    if t.returncode != 0 or not t.stdout.strip():
        return None
    return {**os.environ, "GH_TOKEN": t.stdout.strip()}


def _gh(args, **kw):
    if "env" not in kw:
        env = _owner_env()
        if env:
            kw["env"] = env
    p = subprocess.run([_gh_bin()] + args, capture_output=True, text=True, timeout=120, **kw)
    if p.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])} 실패: {(p.stderr or p.stdout)[:200]}")
    return p.stdout


def ensure_repo(cfg=None):
    """이미지 저장소가 없으면 공개 저장소로 만든다(있으면 그대로 쓴다)."""
    a = _acfg(cfg)
    repo = a.get("repo")
    if not repo:
        raise RuntimeError("config.json 의 geoai.assets.repo 가 비어 있습니다.")
    try:
        _gh(["repo", "view", repo, "--json", "name"])
        return repo
    except RuntimeError:
        log(f"이미지 저장소가 없어 새로 만듭니다: {repo} (공개)")
        _gh(["repo", "create", repo, "--public",
             "--description", "GeoAI 블로그 카드뉴스 이미지 호스팅"])
        return repo


def _shrink(path, max_w, quality=82):
    """Gamma 원본은 장당 4~5MB 라 블로그에 그대로 걸면 무겁다 — 폭을 줄여 JPEG 로 저장.

    실패하면 원본 경로를 그대로 쓴다(이미지가 아예 빠지는 것보다 낫다)."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("RGB")
            if im.width > max_w:
                im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
            out = os.path.join(
                POSTS_DIR, os.path.splitext(os.path.basename(path))[0] + "_web.jpg")
            im.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
        return out
    except Exception as e:
        log(f"이미지 축소 실패({os.path.basename(path)}): {type(e).__name__} — 원본 사용")
        return path


def upload(paths, prefix, cfg=None):
    """PNG 들을 올리고 CDN URL 목록을 돌려준다. 실패한 파일은 건너뛴다.

    prefix: 저장소 안 경로 앞부분(예: 2026/09/20260916_brief)."""
    cfg = cfg or load_config()
    a = _acfg(cfg)
    repo = ensure_repo(cfg)
    branch = a.get("branch", "main")
    urls = []
    for i, p in enumerate(paths, start=1):
        if not (p and os.path.exists(p)):
            continue
        p = _shrink(p, int(a.get("max_width", 1400)))
        dest = f"{prefix}_{i}{os.path.splitext(p)[1].lower() or '.png'}"
        with open(p, "rb") as f:
            content = base64.b64encode(f.read()).decode("ascii")
        body = {"message": f"카드뉴스 추가: {dest}", "content": content, "branch": branch}
        try:
            # 같은 경로가 이미 있으면 sha 가 필요하다(재실행 대비).
            try:
                cur = json.loads(_gh(["api", f"repos/{repo}/contents/{dest}",
                                      "-q", "{sha:.sha}"]) or "{}")
                if cur.get("sha"):
                    body["sha"] = cur["sha"]
            except RuntimeError:
                pass
            _gh(["api", "--method", "PUT", f"repos/{repo}/contents/{dest}",
                 "--input", "-"], input=json.dumps(body))
            urls.append(f"https://cdn.jsdelivr.net/gh/{repo}@{branch}/{dest}")
        except Exception as e:
            log(f"이미지 업로드 실패({os.path.basename(p)}): {str(e)[:120]}")
    log(f"카드뉴스 이미지 {len(urls)}/{len(paths)}장 업로드 완료")
    return urls


if __name__ == "__main__":
    import sys
    print(json.dumps(upload(sys.argv[1:], "test/manual"), ensure_ascii=False, indent=2))
