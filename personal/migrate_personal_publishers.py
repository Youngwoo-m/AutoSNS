"""개인 계정용 발행기를 dept/ 에서 personal/ 로 옮긴다(2026-11-06 사용자 지시: 학과 계정만 dept/ 에 남긴다).

티스토리 이전(personal/MIGRATION.txt)과 같은 방식:
  1. 개인 계정 스크립트를 git mv 로 personal/naver-blog-auto/, personal/geoai-youtube/ 에 옮긴다(2026-11-06 Windows PC 에서 완료 — 다시 돌리면 건너뜀).
  2. 옛 경로(dept/...)에는 새 파일을 가리키는 심볼릭 링크를 둔다 → launchd·automations.json·작업 지시문의 옛 경로가 그대로 동작한다.
  3. personal/<폴더>/ 에서 직접 실행해도 되도록, 옮기지 않은 공용 파일(common.py·config.json·.venv·토큰 이름표·상태 파일 등)을
     dept/<폴더>/ 를 가리키는 링크로 둔다(이미 같은 이름이 있으면 건드리지 않음). 이 링크들은 .links 목록에 적고 git 에는 넣지 않는다.

Windows 에서는 개발자 모드 + git config core.symlinks true 가 필요하다(2026-11-06 Mac 은퇴 후 이 PC 가 유일한 실행 환경).

    python3 personal/migrate_personal_publishers.py            # 시험(무엇을 할지만 출력)
    python3 personal/migrate_personal_publishers.py --go       # 실제로 옮김(커밋은 하지 않음)
    python3 personal/migrate_personal_publishers.py --relink   # 공용 파일 링크만 다시 만듦(새로 받은 사본 등)
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MOVE = {
    "naver-blog-auto": [
        "blogger_post.py", "blogger_crosspost_personal.py",
        "geoai_assets.py", "geoai_auth_setup.py", "geoai_backfill_media.py", "geoai_banner.py",
        "geoai_blogger.py", "geoai_cards.py", "geoai_daily.py", "geoai_script.py", "geoai_series.py",
        "geoai_shots.py", "geoai_shots_apply.py", "geoai_steps.py",
    ],
    "youtube-shorts-auto": [
        "geoai_short_post.py", "geoai_video.py", "geoai_youtube_auth.py",
        "geoai_community.py", "geoai_community_login.py", "make_geoai_hook_thumbs.py",
    ],
}
DEST = {"naver-blog-auto": "naver-blog-auto", "youtube-shorts-auto": "geoai-youtube"}  # personal/youtube-shorts-auto 는 기존 링크라 쓰지 않는다
SKIP_LINK = {".git", ".DS_Store", "__pycache__", ".gitignore", "MIGRATION.txt"}


def busy():
    """지금 잡혀 있는 발행 잠금이 있으면 그 목록."""
    try:
        r = subprocess.run([sys.executable, str(ROOT / "common/shared/axlock.py"), "status"],
                           capture_output=True, text=True, timeout=20)
        st = json.loads(r.stdout)
        return json.dumps(st.get("holding"), ensure_ascii=False) if st.get("holding") else ""
    except Exception as e:  # noqa: BLE001  상태를 못 읽으면 안전하게 멈춘다
        return f"잠금 상태를 읽지 못했습니다({type(e).__name__})"


def plan():
    moves, links = [], []
    for sub, names in MOVE.items():
        src_dir, dst_dir = ROOT / "dept" / sub, ROOT / "personal" / DEST[sub]
        for n in names:
            s, d = src_dir / n, dst_dir / n
            if s.is_symlink():
                continue                      # 이미 옮김
            if not s.exists():
                print(f"  ⚠ 없음(건너뜀): {s.relative_to(ROOT)}")
                continue
            if d.exists() and not d.is_symlink():
                sys.exit(f"멈춤: 옮길 자리에 다른 파일이 있습니다: {d.relative_to(ROOT)}")
            moves.append((s, d))
        moved = set(names)
        for e in sorted(os.listdir(src_dir)):
            if e in moved or e in SKIP_LINK:
                continue
            d = dst_dir / e
            if not d.exists() and not d.is_symlink():
                links.append((src_dir / e, d))
    return moves, links


def make_links(links, go):
    by_dir = {}
    for target, ln in links:
        rel = os.path.relpath(target, ln.parent)
        print(f"  링크 {ln.relative_to(ROOT)} → {rel}")
        by_dir.setdefault(ln.parent, []).append(ln.name)
        if go:
            ln.parent.mkdir(parents=True, exist_ok=True)
            ln.symlink_to(rel, target_is_directory=target.is_dir())
    if go:
        for d, names in by_dir.items():
            lp = d / ".links"
            old = set(lp.read_text(encoding="utf-8").split()) if lp.exists() else set()
            lp.write_text("\n".join(sorted(old | set(names))) + "\n", encoding="utf-8")
            gi = d / ".gitignore"
            lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
            add = [f"/{n}" for n in sorted(names) if f"/{n}" not in lines]
            if add:
                gi.write_text("\n".join(lines + ["# migrate_personal_publishers.py 가 만든 공용 파일 링크(.links)"] + add) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--relink", action="store_true")
    a = ap.parse_args()
    moves, links = plan()
    if a.relink:
        make_links(links, a.go)
        return 0
    if a.go and busy():
        sys.exit(f"멈춤: 발행 잠금이 잡혀 있습니다 — 작업이 끝난 뒤 다시 실행하세요.\n{busy()}")
    print(f"옮길 파일 {len(moves)}개, 공용 링크 {len(links)}개{'' if a.go else ' (시험 — --go 로 실제 실행)'}")
    for s, d in moves:
        rel = os.path.relpath(d, s.parent)
        print(f"  이동 {s.relative_to(ROOT)} → {d.relative_to(ROOT)}  (옛 자리 링크 → {rel})")
        if a.go:
            d.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "-C", str(ROOT), "mv", str(s), str(d)], check=True)
            s.symlink_to(rel)
            subprocess.run(["git", "-C", str(ROOT), "add", str(s)], check=True)
    make_links(links, a.go)
    if a.go:
        log = ROOT / "personal" / "MIGRATION.txt"
        with log.open("a", encoding="utf-8") as f:
            f.write("\n2026-11-06: 개인 계정 발행기(blogger_post·geoai_*·geoai_short_post 등 "
                    f"{len(moves)}개)를 dept/ 에서 personal/naver-blog-auto, personal/youtube-shorts-auto 로 옮겼다. "
                    "옛 경로는 심볼릭 링크. 공용 파일은 각 폴더 .links 목록의 링크(git 제외, --relink 로 다시 만듦).\n")
        print("완료 — 커밋하지 않았습니다. git status 로 확인 후 커밋하세요.")
        print("확인: blogger_post.py --dry, geoai_short_post.py upload --dry, geoai_daily.py 시험 실행을 옛 경로와 새 경로 모두로.")
    print(json.dumps({"moves": len(moves), "links": len(links), "go": a.go}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
