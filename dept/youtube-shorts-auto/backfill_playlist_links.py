"""이미 발행된 영상 설명에 시리즈 재생목록 링크를 소급 삽입한다(연속 시청 유도).

새로 발행되는 영상은 youtube_upload/publish_career 가 자동으로 넣지만, 그전에
올라간 영상들은 링크가 없어 한 편 보고 이탈한다. 재생목록에 담긴 영상을 훑어
설명에 링크가 없으면 홈페이지 줄 앞(없으면 첫 문단 뒤)에 한 줄을 끼워 넣는다.

멱등: 이미 같은 재생목록 URL 이 있으면 건너뛴다. 기본은 미리보기(dry-run).
사용: python backfill_playlist_links.py [--go] [--kind news|career|quiz]
"""
import sys

from googleapiclient.discovery import build

from common import load_config, log
from youtube_upload import _creds

HOME_MARK = "🏫"


def _playlist_ids(yt, pid):
    out, tok = [], None
    while True:
        r = yt.playlistItems().list(part="snippet", playlistId=pid,
                                    maxResults=50, pageToken=tok).execute()
        out += [i["snippet"]["resourceId"]["videoId"] for i in r["items"]]
        tok = r.get("nextPageToken")
        if not tok:
            return out


def _insert(desc, line):
    """홈페이지 줄 앞에 넣고, 없으면 첫 문단 뒤에, 그것도 없으면 맨 끝에."""
    lines = desc.split("\n")
    for i, ln in enumerate(lines):
        if ln.startswith(HOME_MARK):
            return "\n".join(lines[:i] + [line, ""] + lines[i:])
    if "\n\n" in desc:
        head, rest = desc.split("\n\n", 1)
        return f"{head}\n\n{line}\n\n{rest}"
    return f"{desc}\n\n{line}"


def run(kinds=None, go=False):
    cfg = load_config()
    yc = cfg.get("youtube", {})
    pls, labels = yc.get("playlists", {}) or {}, yc.get("playlist_labels", {}) or {}
    yt = build("youtube", "v3", credentials=_creds(), cache_discovery=False)
    done = skipped = failed = 0
    for kind, pid in pls.items():
        if kinds and kind not in kinds:
            continue
        url = f"https://www.youtube.com/playlist?list={pid}"
        line = f"▶ {labels.get(kind, '시리즈 전편 보기')}: {url}"
        vids = _playlist_ids(yt, pid)
        log(f"[{kind}] {len(vids)}편 점검")
        for vid in vids:
            try:
                item = yt.videos().list(part="snippet", id=vid).execute()["items"][0]
                sn = item["snippet"]
                if url in (sn.get("description") or ""):
                    skipped += 1
                    continue
                new_desc = _insert(sn.get("description", "").strip(), line)
                if not go:
                    log(f"  [DRY] {vid} {sn['title'][:40]}")
                    done += 1
                    continue
                yt.videos().update(part="snippet", body={"id": vid, "snippet": {
                    "title": sn["title"], "description": new_desc,
                    "tags": sn.get("tags", []),
                    "categoryId": sn.get("categoryId", "27"),
                    "defaultLanguage": sn.get("defaultLanguage", "ko"),
                }}).execute()
                done += 1
                log(f"  링크 삽입 {vid} {sn['title'][:40]}")
            except Exception as e:
                failed += 1
                log(f"  실패 {vid}: {type(e).__name__}: {str(e)[:90]}")
    log(f"{'적용' if go else 'DRY-RUN'} 완료 — 대상 {done}편, 이미있음 {skipped}편, 실패 {failed}편")
    return {"updated": done, "skipped": skipped, "failed": failed}


if __name__ == "__main__":
    kinds = None
    if "--kind" in sys.argv:
        kinds = [sys.argv[sys.argv.index("--kind") + 1]]
    run(kinds=kinds, go="--go" in sys.argv)
