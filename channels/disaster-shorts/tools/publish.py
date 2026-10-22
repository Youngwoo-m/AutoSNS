"""완성본을 학과 채널에 '비공개 + 예약 공개'로 올린다(AutoSNS 의 학과 채널 토큰 사용).

  .venv/bin/python publish.py 2026-10-06_산불            # 실제 업로드(예약)
  .venv/bin/python publish.py 2026-10-06_산불 --dry-run  # 메타데이터만 확인
예약 시각: 편의 날짜(화요일) 19:00 KST. 이미 올렸으면(<편>/upload.json) 다시 올리지 않는다.
"""
import argparse, datetime as dt, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
AUTOSNS = "/Volumes/USB256/devAPP/AutoSNS/channels/youtube-shorts-auto"
sys.path.insert(0, AUTOSNS); os.chdir(AUTOSNS)

KST = dt.timezone(dt.timedelta(hours=9))
SERIES = "재난 유형별 피해 양상과 대응 방안"
DISCLOSURE = ("※ 인트로·아웃트로는 세명대학교 재난안전학과 나영우 교수의 모습과 목소리를 바탕으로 AI로 만든 "
              "아바타 영상이며, 본문 배경은 AI로 생성한 3D 재현 영상입니다(합성 음성·영상).")
DISCLOSURE_LOOP = ("※ 나레이션은 세명대학교 재난안전학과 나영우 교수의 목소리를 바탕으로 AI로 합성했으며, "
                   "배경은 AI로 생성한 3D 재현 영상입니다(합성 음성·영상).")
if CFG.get("voice_backend") == "edge":      # 2026-10-22: 본문 나레이션을 edge-tts(ko-KR-InJoonNeural)로 바꿨다
    DISCLOSURE = ("※ 인트로·아웃트로는 세명대학교 재난안전학과 나영우 교수의 모습과 목소리를 바탕으로 AI로 만든 "
                  "아바타 영상이며, 본문 나레이션은 AI 합성 음성(TTS), 본문 배경은 AI로 생성한 3D 재현 영상입니다(합성 음성·영상).")
    DISCLOSURE_LOOP = ("※ 나레이션은 AI 합성 음성(TTS)이며, 배경은 AI로 생성한 3D 재현 영상입니다(합성 음성·영상).")


def publish_at(date_str):
    h, m = map(int, CFG["publish"]["time_kst"].split(":"))
    d = dt.date.fromisoformat(date_str)
    return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=KST)


def yt_tags(sc):
    """설명란 해시태그 — 유튜브는 15개를 넘으면 전부 무시하므로 3~4개만(앞 3개가 제목 위에 보인다)."""
    h = (sc.get("hashtags") or {}).get("youtube") or [sc["type"].replace(" ", "").replace("·", ""), "재난대응", "국민행동요령"]
    return [t.lstrip("#").replace(" ", "") for t in h][:4]


def meta(sc):
    title = sc["title"]
    if "#" not in title:
        title = f"{title} #Shorts"
    lines = [f"[{SERIES}] {sc['type']} 편", ""]
    for s in sc["scenes"]:
        lines.append("• " + s["narration"])
    if sc.get("loop") and sc.get("next_episode_text"):
        lines += ["", "▶ 다음 편 — " + sc["next_episode_text"]]
    lines += ["", sc["upload"]["description_notes"], DISCLOSURE_LOOP if sc.get("loop") else DISCLOSURE, "",
              "매주 화요일 저녁 7시, 계절에 맞는 재난 대응 방법을 알려 드려요.",
              "세명대학교 재난안전학과 https://www.semyung.ac.kr/smds.do", "",
              " ".join("#" + t for t in yt_tags(sc)) + " #Shorts"]
    tags = list(dict.fromkeys(yt_tags(sc) + sc["upload"].get("tags", []) + ["재난 유형별 대응", "국민행동요령", "세명대 재난안전학과"]))
    return title[:100], "\n".join(lines)[:4900], tags


def upload(ep, dry_run=False):
    ep_dir = os.path.join(CFG["root"], ep)
    rec = os.path.join(ep_dir, "upload.json")
    if os.path.exists(rec):
        print("이미 업로드됨:", json.load(open(rec)))
        return json.load(open(rec))
    sc = json.load(open(os.path.join(ep_dir, "script.json"), encoding="utf-8"))
    video = os.path.join(ep_dir, "final.mp4")
    when = publish_at(sc["date"])
    if when <= dt.datetime.now(KST) + dt.timedelta(minutes=30):
        raise SystemExit(f"예약 시각이 이미 지났거나 너무 가깝습니다: {when}")
    title, desc, tags = meta(sc)
    status = {"privacyStatus": "private", "publishAt": when.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
              "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
              "embeddable": True, "publicStatsViewable": True, "license": "youtube"}   # 블로그 임베드에 필요
    body = {"snippet": {"title": title, "description": desc, "tags": tags,
                        "categoryId": CFG["publish"]["category_id"], "defaultLanguage": "ko",
                        "defaultAudioLanguage": "ko"}, "status": status}
    print(f"제목: {title}\n예약: {when.isoformat()} (KST)\n영상: {video}\n태그: {', '.join(tags)}\n설명:\n{desc}")
    if dry_run:
        return {"dry_run": True}
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    import youtube_upload as YU
    yt = build("youtube", "v3", credentials=YU._creds(os.path.join(AUTOSNS, CFG["publish"]["channel_token"])),
               cache_discovery=False)
    def _insert(b):
        req = yt.videos().insert(part="snippet,status", body=b,
                                 media_body=MediaFileUpload(video, chunksize=-1, resumable=True, mimetype="video/mp4"))
        r = None
        while r is None:
            _, r = req.next_chunk()
        return r
    mode = "youtube_schedule"
    try:
        resp = _insert(body)
    except Exception as e:
        if "invalidPublishAt" not in str(e):
            raise
        # 예약이 거부되면 예약 없이 비공개로 올리고, 공개는 crosspost.py 가 19:00 이후에 API 로 한다
        print("유튜브 예약이 거부됨 → 비공개로 올리고 19:00 이후 API 로 공개합니다.")
        body["status"].pop("publishAt", None); mode = "api_at_publish_time"
        resp = _insert(body)
    thumb = os.path.join(ep_dir, "thumbnail.jpg")
    thumb_st = "없음"
    if os.path.exists(thumb):
        try:                                # 썸네일 = 인트로 뒤 첫 화면. 실패해도 업로드는 유지
            yt.thumbnails().set(videoId=resp["id"], media_body=MediaFileUpload(thumb, mimetype="image/jpeg")).execute()
            thumb_st = "설정됨"
        except Exception as e:
            thumb_st = f"실패: {str(e)[:120]}"
    print("썸네일:", thumb_st)
    out = {"video_id": resp["id"], "thumbnail": thumb_st, "publish_mode": mode, "url": f"https://youtu.be/{resp['id']}", "publish_at_kst": when.isoformat(),
           "uploaded_at": dt.datetime.now(KST).isoformat()}
    json.dump(out, open(rec, "w"), ensure_ascii=False, indent=1)
    print("업로드 완료(비공개 예약):", out)
    try:   # 틱톡 하루 1편 대기열 — 유튜브 공개 시각 이후에 올라가게, AI 아바타 표시와 함께
        import tiktok_queue as TQ
        TQ.add(video, sc["title"], desc[:400],   # sc["intro"] 는 인트로 영상 경로라 설명으로 쓰면 안 된다
               (sc.get("hashtags") or {}).get("instagram", []) + ["재난안전", "재난안전학과"],
               ai_generated=True, not_before=when.replace(tzinfo=None).isoformat(), source="shorts-disaster")
    except Exception as e:
        print("틱톡 대기열 건너뜀:", type(e).__name__, str(e)[:100])
    return out


def replace(ep):
    """예약된 편을 새 완성본으로 바꾼다 — 새 영상을 같은 시각으로 예약하고, 이전 영상은 예약을 풀어 비공개로 남긴다
    (지우지 않음 — 지우기는 사용자가 결정). 10/14 루프 구조 교체 때 만듦."""
    ep_dir = os.path.join(CFG["root"], ep); rec = os.path.join(ep_dir, "upload.json")
    old = json.load(open(rec)) if os.path.exists(rec) else None
    if old:
        os.replace(rec, os.path.join(ep_dir, f"upload_replaced_{old['video_id']}.json"))
    new = upload(ep)
    if old:
        from googleapiclient.discovery import build
        import youtube_upload as YU
        yt = build("youtube", "v3", credentials=YU._creds(os.path.join(AUTOSNS, CFG["publish"]["channel_token"])),
                   cache_discovery=False)
        st = {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True,
              "embeddable": True, "publicStatsViewable": True, "license": "youtube"}   # 빠진 필드는 기본값으로 덮이므로 모두 보낸다
        yt.videos().update(part="status", body={"id": old["video_id"], "status": st}).execute()
        print(f"이전 영상 {old['video_id']}: 예약 해제, 비공개로 남김")
    return new


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("ep"); ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replace", action="store_true")
    a = ap.parse_args()
    replace(a.ep) if a.replace else upload(a.ep, a.dry_run)
