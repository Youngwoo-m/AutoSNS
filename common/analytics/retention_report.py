"""조회수 상위·하위 영상이 '몇 초 만에' 넘겨지는지 본다.

왜: 숏츠는 초반 이탈이 전부다. 평균 시청 시간만 보면 길이가 다른 영상끼리 비교가
    안 되므로, 시청 지속율 곡선(audienceWatchRatio)에서 시청자 절반이 빠져나가는
    지점을 초로 환산해 같이 본다.

사용:  python retention_report.py              # 학과 채널, 최근 90일
       python retention_report.py --geoai      # GeoAI 채널
       python retention_report.py --days 28 --top 5
"""
import argparse
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
from analytics.common import ROOT_DIR, log  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/yt-analytics.readonly"]
TOKENS = {"dept": os.path.join(ROOT_DIR, "channels", "youtube-shorts-auto", "token.json"),
          "geoai": os.path.join(ROOT_DIR, "channels", "youtube-shorts-auto", "token_youtube_geoai.json")}


def _creds(path):
    """토큰 파일은 읽기만 한다 — 갱신 결과를 덮어쓰지 않는다.

    여기서 c.to_json() 을 그대로 저장했더니 token.json 의 scopes 가 이 파일의
    SCOPES(읽기 2개)로 좁혀져, 같은 토큰을 쓰는 업로드·썸네일 설정이 403
    'insufficient authentication scopes' 로 막혔다(2026-10-14). 분석용 스크립트가
    발행용 자격 증명을 건드리면 안 된다."""
    from shared import token_store            # 토큰은 암호화 저장소에 있다
    return token_store.load_google(path, SCOPES, save=False)


def _dur_seconds(iso):
    """PT1M30S → 90. 길이를 알아야 비율을 초로 바꾼다."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s


def _videos(yt, ids):
    out = {}
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part="snippet,contentDetails", id=",".join(ids[i:i + 50])).execute()
        for v in r.get("items", []):
            out[v["id"]] = {"title": v["snippet"]["title"],
                            "published": v["snippet"]["publishedAt"][:10],
                            "seconds": _dur_seconds(v["contentDetails"]["duration"])}
    return out


def _half_life(ya, vid, start, end, seconds):
    """시청자 절반이 떠난 지점(초). 데이터가 없으면 None."""
    try:
        r = ya.reports().query(ids="channel==MINE", startDate=start, endDate=end,
                               metrics="audienceWatchRatio", dimensions="elapsedVideoTimeRatio",
                               filters=f"video=={vid}", sort="elapsedVideoTimeRatio").execute()
    except Exception as e:
        return None, f"{type(e).__name__}"
    rows = r.get("rows") or []
    if not rows:
        return None, "데이터 없음"
    first = rows[0][1] or 0
    if first <= 0:
        return None, "시작 지점 0"
    for ratio, watch in rows:
        if watch / first < 0.5:                 # 시작 대비 절반 아래로 떨어진 첫 지점
            return round(ratio * seconds, 1), None
    return None, "끝까지 절반 이상 유지"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--geoai", action="store_true")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args()
    from googleapiclient.discovery import build

    path = TOKENS["geoai" if a.geoai else "dept"]
    creds = _creds(path)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ya = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)

    end = datetime.date.today()
    start = end - datetime.timedelta(days=a.days)
    r = ya.reports().query(ids="channel==MINE", startDate=str(start), endDate=str(end),
                           metrics="views,averageViewDuration,averageViewPercentage",
                           dimensions="video", sort="-views", maxResults=200).execute()
    rows = r.get("rows") or []
    log(f"{'GeoAI' if a.geoai else '학과'} 채널: {len(rows)}편 ({start}~{end})")
    if not rows:
        return
    meta = _videos(yt, [x[0] for x in rows])

    def show(label, subset):
        print(f"\n=== {label}")
        print(f"{'조회':>6} {'길이':>5} {'평균시청':>7} {'시청률':>6} {'절반이탈':>8}  제목")
        for vid, views, avg_dur, avg_pct in subset:
            m = meta.get(vid, {})
            half, why = _half_life(ya, vid, str(start), str(end), m.get("seconds", 0))
            half_s = f"{half:.1f}초" if half is not None else (why or "-")
            print(f"{views:>6} {m.get('seconds', 0):>4}초 {avg_dur:>6}초 {avg_pct:>5.1f}% "
                  f"{half_s:>8}  {m.get('title', vid)[:40]}")

    show(f"조회 상위 {a.top}편", rows[:a.top])
    show(f"조회 하위 {a.top}편", rows[-a.top:])


if __name__ == "__main__":
    main()
