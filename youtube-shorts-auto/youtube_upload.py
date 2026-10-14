"""저장된 토큰(token.json)으로 YouTube Data API v3 에 Shorts mp4 를 업로드한다.

Shorts 로 인식되는 조건: 세로(9:16) + 3분 이내 (여기서는 ~1분) + 제목/설명에 #Shorts.
category_id 기본 25(News & Politics). privacy 는 config.youtube.privacy(기본 public).

★ 안전장치(다른 프로젝트와 동일 철학):
  - 수동 실행(python youtube_upload.py)은 기본 dry_run → 업로드하지 않고 메타데이터만 출력.
  - 실제 발행은 스케줄 엔트리(run_weekly.py)에서 dry_run=False 로만 일어난다.
  - 실제 업로드를 '비공개(private)'로 미리 테스트하려면:  python youtube_upload.py --private
"""
import json
import os
import re
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from common import POSTS_DIR, TOKEN_PATH, load_config, log

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.keyword_terms import TAG_DISASTER_TERMS, TAG_REGION_TERMS  # noqa: E402

# 업로드 + 읽기(검색·통계) + 애널리틱스 + 댓글쓰기(force-ssl). 업로드만 넣으면 토큰
# 재저장 시 나머지 스코프가 날아가 web_search / 애널리틱스 / 자동댓글이 403 이 된다.
# force-ssl 추가 후에는 youtube_login_setup.py 로 1회 재인증(재동의)해야 댓글이 붙는다.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]

# 검색 최적화(SEO) 기본값 — config.youtube.seo_footer / seo_keywords 로 덮어쓸 수 있다.
DEFAULT_SEO_FOOTER = (
    "세명대학교 재난안전학과가 전하는 주간 재난안전 뉴스입니다. "
    "지진·태풍·호우·산사태·폭염 등 재난 대비와 대응 정보를 매주 정리합니다.")
DEFAULT_SEO_KEYWORDS = [
    "재난안전", "재난안전뉴스", "안전정보", "재난대비", "재난대응", "안전수칙",
    "세명대학교", "세명대", "재난안전학과",
]
# 태그 자동 보강 키워드 — 공통 목록은 shared/keyword_terms.py 에 있다.
EXTRA_TAG_TERMS = []          # 유튜브에만 붙일 추가 재난 태그(현재 없음)
DISASTER_TERMS = TAG_DISASTER_TERMS + EXTRA_TAG_TERMS
REGION_TERMS = TAG_REGION_TERMS


def _detected_keywords(data):
    """제목 + 출처 제목에서 지역·재난 키워드를 뽑아 검색 태그로 쓴다.

    출처 제목 끝의 ' - 언론사'는 제거한 뒤 매칭한다. (예: '서울경제TV' 때문에
    '서울'이 잘못 잡히는 것을 막는다.)
    """
    def _strip_outlet(t):
        return re.sub(r"\s*-\s*[^-]+$", "", t)
    hay = (data.get("title", "") + " " +
           " ".join(_strip_outlet(s.get("title", ""))
                    for s in (data.get("sources") or [])))
    # 학과별 키워드는 config.keywords 로 덮어쓸 수 있다(없으면 아래 기본값=재난안전).
    kw = load_config().get("keywords", {})
    terms = (kw.get("tag_terms") or DISASTER_TERMS) + (kw.get("region_terms") or REGION_TERMS)
    # 띄어 쓴 표기("안전 훈련")도 잡도록 공백을 지운 사본과 함께 비교한다.
    flat = hay.replace(" ", "")
    found = []
    for term in terms:
        if (term in hay or term.replace(" ", "") in flat) and term not in found:
            found.append(term)
    return found


def _creds(token_path=None):
    """저장된 토큰으로 자격증명을 만든다.

    token_path 를 주면 다른 채널의 토큰을 쓴다(예: 개인 GeoAI 채널 —
    token_youtube_geoai.json). 기본값은 학과 채널 토큰(token.json)."""
    path = token_path or TOKEN_PATH
    if not os.path.exists(path):
        raise RuntimeError(
            f"{os.path.basename(path)} 이 없습니다. 먼저 로그인 스크립트로 1회 인증하세요"
            " (학과 채널: youtube_login_setup.py / GeoAI 채널: geoai_youtube_auth.py).")
    creds = Credentials.from_authorized_user_file(path, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            log(f"토큰 자동 갱신됨({os.path.basename(path)}).")
        else:
            raise RuntimeError(
                "토큰이 만료되어 갱신할 수 없습니다. youtube_login_setup.py 를 다시 실행하세요.")
    return creds


DESC_LIMIT = 4900      # 유튜브 한도 5000자 — 전각 치환으로 늘 수 있어 여유를 둔다
TITLE_LIMIT = 100


def _build_title(data, ycfg):
    """제목 앞에 [SMU 재난안전뉴스] 등 접두사, 또는 뒤에 '| 채널명' 접미사를 붙인다(중복/100자 초과 방지).

    숏츠 피드는 제목 앞 20자 남짓만 보여서, 검색어가 앞에 와야 하는 채널은 접미사를 쓴다."""
    title = (data.get("title") or "재난안전 Shorts").strip()
    prefix = ycfg.get("title_prefix", "").strip()
    suffix = ycfg.get("title_suffix", "").strip()
    if prefix and not title.startswith(prefix):
        title = f"{prefix} {title}"
    if suffix and not title.endswith(suffix):
        # 잘려도 본 제목이 남도록 접미사 자리를 먼저 뺀다
        title = f"{title[:TITLE_LIMIT - len(suffix) - 1].rstrip()} {suffix}"
    return _sanitize(title)[:TITLE_LIMIT]


def pick_playlist(title, ycfg):
    """제목 키워드로 넣을 재생목록 id 를 고른다. 규칙(playlist_rules)은 위에서부터 먼저 맞는 것,
    아무것도 안 맞으면 playlist_default. 둘 다 없으면 None(재생목록에 넣지 않음)."""
    for rule in ycfg.get("playlist_rules", []):
        if any(k in title for k in rule.get("match", [])):
            return rule.get("playlist")
    return ycfg.get("playlist_default") or None


def put_in_playlist(youtube, video_id, playlist_id):
    """영상을 재생목록 맨 위에 넣는다. 이미 들어 있으면 건너뛴다(재실행해도 중복되지 않음)."""
    if not (video_id and playlist_id):
        return False
    have = youtube.playlistItems().list(part="id", playlistId=playlist_id,
                                        videoId=video_id).execute().get("items")
    if have:
        return False
    youtube.playlistItems().insert(part="snippet", body={"snippet": {
        "playlistId": playlist_id, "position": 0,
        "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
    return True


def _build_description(data, cfg):
    ycfg = cfg.get("youtube", {})
    parts = [data.get("description", "").strip()]

    # 검색용 고정 키워드 문장(채널 일관성 → 검색 랭킹). 첫 문단 바로 아래에 둔다.
    seo = ycfg.get("seo_footer", DEFAULT_SEO_FOOTER).strip()
    if seo:
        parts.append("")
        parts.append(seo)

    # 시리즈 몰아보기 링크 — 한 편만 보고 나가지 않게 연속 시청을 유도한다.
    # (최근 28일 조회 1.1만 대비 구독 +4 로 전환이 약해, 세션 시청을 늘리는 쪽으로 보강)
    pls = ycfg.get("playlists", {}) or {}
    pl_labels = ycfg.get("playlist_labels", {}) or {}
    kind = data.get("playlist_kind", "news")
    if pls.get(kind):
        parts.append("")
        parts.append(f"▶ {pl_labels.get(kind, '지난 편 몰아보기')}: "
                     f"https://www.youtube.com/playlist?list={pls[kind]}")

    homepage = ycfg.get("homepage_url", "").strip()
    if homepage:
        parts.append("")
        # 라벨은 채널마다 다르다(학과 채널=학과 홈페이지, GeoAI 채널=블로그).
        parts.append(f'{ycfg.get("homepage_label", "🏫 세명대학교 재난안전학과")}: {homepage}')

    # 다른 채널로 보내는 줄 — Shorts 피드로 들어온 시청자는 채널을 인지하지 못한 채
    # 지나간다(유입의 86%가 Shorts 피드). 설명에서 다시 만날 길을 준다.
    for ln in (ycfg.get("channel_links") or []):
        if (ln.get("url") or "").strip():
            parts.append(f"{ln.get('label','').strip()}: {ln['url'].strip()}")

    # AI 아나운서 영상이면 합성 콘텐츠 고지를 자동 삽입(YouTube 정책 준수)
    if data.get("ai_disclosure"):
        parts.append("")
        parts.append(cfg.get("heygen", {}).get("disclosure_text",
            "※ 이 영상은 세명대학교 재난안전학과 학과장의 모습을 바탕으로 "
            "AI로 자동 생성한 아바타 영상입니다(합성 음성·영상)."))

    if data.get("ai_broll") and not data.get("ai_disclosure"):
        parts.append("")
        parts.append("※ 일부 배경 화면은 AI로 생성한 영상입니다(실제 현장 영상이 아님).")

    sources = data.get("sources") or []
    src_from = len(parts)          # 길이 초과 시 여기부터 뒤로 덜어낸다(출처는 부가 정보)
    if sources and ycfg.get("include_sources", True):
        parts.append("")
        parts.append("📰 참고 뉴스 출처")
        for s in sources[:6]:
            parts.append(f"· [{s.get('published_str','')}] {s.get('title','')}")
            link = (s.get("real_link") or s.get("link") or "").strip()
            if link:
                parts.append(f"  {link}")
    # 채널 지역 브랜딩: config.hashtags + local_tags(제천·충북 등)를 모든 영상에 항상 포함.
    # local_tags 는 에디션(토요일 GeoAI판)이 hashtags 를 덮어써도 유지된다(지역태그 규칙 보장).
    base_tags = cfg.get("hashtags", []) + cfg.get("local_tags", [])
    tags = list(dict.fromkeys((data.get("hashtags") or []) + base_tags))
    # #Shorts 는 항상 포함되도록 보장
    tag_line_src = tags if any(t.lower() == "shorts" for t in tags) else (["Shorts"] + tags)
    tag_line = " ".join("#" + t for t in tag_line_src)

    # 유튜브 설명 상한 5000자. 넘으면 출처 줄을 끝에서부터 덜어낸다 — 해시태그 줄은
    # 검색 유입에 쓰이므로 반드시 남긴다. 지금은 1.5천자대라 걸리지 않지만, 출처 제목이
    # 길어져 조용히 넘치면 업로드가 invalidDescription 으로 통째로 실패한다.
    # 배경음악 출처(CC BY 4.0 — 표기 필수). 설명이 길어 출처 줄을 덜어낼 때도 남긴다.
    tail = (["", data["bgm_credit"]] if data.get("bgm_credit") else []) + ["", tag_line]
    head = list(parts)
    while True:
        desc = "\n".join(x for x in head + tail if x is not None).strip()
        if len(desc) <= DESC_LIMIT or len(head) <= src_from:
            break
        head.pop()
    # 링크를 잃은 출처 제목 줄이 홀로 남지 않게 한 줄 더 덜어낸다.
    if len(head) > src_from and str(head[-1]).startswith("· ["):
        head.pop()
        desc = "\n".join(x for x in head + tail if x is not None).strip()
    if len(head) < len(parts):
        log(f"설명이 {DESC_LIMIT}자를 넘어 출처 {len(parts) - len(head)}줄을 덜어냈습니다.")
    return _sanitize(desc)


def _sanitize(text):
    """유튜브가 거부하는 꺾쇠(< >)를 제거한다.

    2026-09-12 토요일 발행이 'invalidDescription' 으로 실패했다. 뉴스 제목에 섞여 온
    '… 스마트 안전망 > 뉴스데스크' 의 꺾쇠가 원인이었다(출처 목록을 설명에 넣기 때문).
    비슷하게 생긴 전각 기호로 바꿔 의미는 살리고 거부는 피한다."""
    return (text or "").replace("<", "〈").replace(">", "〉")


def _preflight(title, description, keywords):
    """업로드 직전 최종 점검. 한도를 넘은 채 API 를 때리면 영상·TTS·아나운서 비용을
    다 쓰고 invalidDescription/invalidTags 로 버려진다(2026-09-12 사례).

    평소엔 걸리지 않는 백스톱이다 — 제목·설명·태그는 각 빌더에서 이미 잘라 넣는다.
    여기서 걸리면 빌더 쪽이 깨진 것이므로, 조용히 자르지 않고 멈추고 사유를 남긴다.
    """
    for name, val, lim in (("제목", title, TITLE_LIMIT),
                           ("설명", description, 5000),
                           ("태그 총합", ",".join(keywords or []), 500)):
        if len(val) > lim:
            raise ValueError(f"{name}이 유튜브 한도를 넘었습니다({len(val)}>{lim}자) — 업로드 중단")
    for name, val in (("제목", title), ("설명", description)):
        bad = [c for c in "<>" if c in val]
        if bad:
            raise ValueError(f"{name}에 유튜브가 거부하는 문자 {bad} 가 남아 있습니다 — 업로드 중단")


def upload(data, dry_run=None, privacy=None, token_path=None):
    cfg = load_config()
    ycfg = cfg.get("youtube", {})
    if dry_run is None:
        dry_run = ycfg.get("dry_run", True)
    if privacy is None:
        privacy = ycfg.get("privacy", "public")

    video_path = data.get("video")
    if not video_path or not os.path.exists(video_path):
        raise RuntimeError("업로드할 mp4 가 없습니다. 먼저 make_video.py 를 실행하세요.")

    title = _build_title(data, ycfg)
    description = _build_description(data, cfg)
    # 검색 태그: 감지된 지역·재난 키워드 + 해시태그 + 지역 브랜딩(local_tags) + 기본 SEO 키워드
    base_kw = ycfg.get("seo_keywords", DEFAULT_SEO_KEYWORDS)
    hashtag_kw = [t for t in (data.get("hashtags") or []) if t.lower() != "shorts"]
    local_kw = cfg.get("local_tags", [])
    keywords = list(dict.fromkeys(_detected_keywords(data) + hashtag_kw + local_kw + base_kw))
    # YouTube tags 총합 500자 제한 → 안전하게 자른다
    trimmed, total = [], 0
    for k in keywords:
        total += len(k) + 1
        if total > 460:
            break
        trimmed.append(k)
    keywords = trimmed

    _preflight(title, description, keywords)

    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": False,
    }
    # AI 아나운서 영상은 유튜브의 공식 '변경·합성 콘텐츠' 라벨까지 신고한다.
    # (설명문 고지는 우리가 쓰는 안내문일 뿐, 정책상 요구되는 신고는 이 플래그다.)
    # 배경에 AI 실사 클립을 쓴 뉴스도 같다 — 실제 현장처럼 보이는 합성 영상이다.
    if data.get("ai_disclosure") or data.get("ai_broll"):
        status["containsSyntheticMedia"] = True
    synthetic = bool(status.get("containsSyntheticMedia"))   # 아래 업로드 루프가 status 를 덮어쓴다

    if dry_run:
        log("DRY_RUN: 업로드하지 않습니다. 아래 메타데이터/영상 경로를 확인하세요.")
        log(f"  제목: {title}")
        log(f"  영상: {video_path} ({data.get('video_seconds','?')}s)")
        log(f"  태그: {', '.join(keywords)}")
        log(f"  status: {json.dumps(status, ensure_ascii=False)}")
        log("  설명 미리보기:\n" + "\n".join("    " + ln for ln in description.splitlines()))
        log("실제 업로드는 run_weekly.py(스케줄)에서, 비공개 테스트는 "
            "'python youtube_upload.py --private' 로 하세요.")
        return {"status": "dry_run", "video": video_path}

    creds = _creds(token_path)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": keywords,
            "categoryId": str(ycfg.get("category_id", "25")),
            "defaultLanguage": "ko",
            "defaultAudioLanguage": "ko",
        },
        "status": status,
    }
    media = MediaFileUpload(video_path, chunksize=-1, resumable=True,
                            mimetype="video/mp4")
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    log(f"업로드 시작(privacy={privacy}"
        f"{', 합성콘텐츠 신고' if status.get('containsSyntheticMedia') else ''}): {title}")
    response = None
    while response is None:
        status, response = req.next_chunk()
        if status:
            log(f"  업로드 {int(status.progress()*100)}%")
    vid = response.get("id")
    url = f"https://youtu.be/{vid}" if vid else "(id 없음)"
    log(f"업로드 완료: {url}  (privacy={privacy})")
    # 썸네일 — 올리지 않으면 유튜브가 표지 프레임(회색 카드)을 골라 쓴다. 검색·채널 목록에서
    # 다른 영상과 구분이 안 되므로 직접 만든 것을 올린다. 맞춤 썸네일은 전화 인증된
    # 채널만 되므로 실패해도 업로드 결과는 그대로 둔다.
    if vid and ycfg.get("thumbnail", True):
        try:
            from make_thumbnail import make_thumbnail
            shape = "shorts" if data.get("video_seconds", 60) <= 180 else "video"
            thumb = make_thumbnail(data, shape=shape)
            youtube.thumbnails().set(videoId=vid, media_body=thumb).execute()
            log(f"썸네일 적용({shape}): {os.path.basename(thumb)}")
        except Exception as e:  # noqa: BLE001
            log(f"썸네일 적용 실패(업로드는 정상): {type(e).__name__}: {str(e)[:120]}")

    # 재생목록 분류는 부가 작업 — 실패해도 업로드 결과는 그대로 둔다
    pl = pick_playlist(title, ycfg)
    if vid and pl:
        try:
            if put_in_playlist(youtube, vid, pl):
                log(f"재생목록 추가: {pl}")
        except Exception as e:  # noqa: BLE001
            log(f"재생목록 추가 실패(업로드는 정상): {type(e).__name__}: {str(e)[:120]}")
    # 공개 숏츠는 학과 틱톡 대기열에도 넣는다(유튜브 공개 30분 뒤). 학과 채널과 개인 GeoAI 채널
    # 모두 — 단 제휴(쿠팡 파트너스) 고지가 있는 영상은 학과 계정에 올리지 않는다.
    if vid and privacy == "public" and "쿠팡" not in (data.get("description") or ""):
        try:
            from tiktok_queue import add as tiktok_add
            geo = bool(token_path) and os.path.abspath(token_path) != os.path.abspath(TOKEN_PATH)
            tiktok_add(video_path, data.get("title", ""), data.get("description", ""),
                       data.get("hashtags") or [], ai_generated=synthetic,
                       source="geoai" if geo else "youtube_upload")
        except Exception as e:  # noqa: BLE001
            log(f"틱톡 대기열 건너뜀: {type(e).__name__}")
    return {"status": "uploaded", "video_id": vid, "url": url, "privacy": privacy}


def comment_text(data, cfg=None):
    """자동 첫 댓글 문구. config.youtube.auto_comment.text 로 덮어쓸 수 있고,
    {title} 플레이스홀더를 영상 제목으로 치환한다."""
    cfg = cfg or load_config()
    ac = cfg.get("youtube", {}).get("auto_comment", {})
    tmpl = ac.get("text") or (
        "이 소식이 도움이 되셨다면 구독 부탁드려요 🙏\n"
        "여러분 지역은 안전한가요? 댓글로 알려주세요! "
        "세명대학교 재난안전학과가 매주 재난안전 정보를 전합니다.")
    try:
        return tmpl.format(title=(data or {}).get("title", ""))
    except Exception:
        return tmpl


def post_top_comment(video_id, text=None, data=None, dry_run=False):
    """업로드한 영상에 최상위 댓글을 자동 작성(구독 유도·참여 마중물).

    youtube.force-ssl 스코프 필요 → 없으면 403(재인증 안내). 실패해도 예외를 삼켜
    발행을 막지 않는다. (참고: 댓글 '상단 고정'은 YouTube API 미지원 — 작성까지만 자동화.)
    """
    if not video_id:
        return {"skipped": "no video_id"}
    text = text or comment_text(data)
    if dry_run:
        log(f"DRY_RUN 자동댓글: {text[:60]}...")
        return {"dry_run": text}
    try:
        yt = build("youtube", "v3", credentials=_creds(), cache_discovery=False)
        body = {"snippet": {"videoId": video_id,
                            "topLevelComment": {"snippet": {"textOriginal": text}}}}
        res = yt.commentThreads().insert(part="snippet", body=body).execute()
        log(f"자동 댓글 작성 완료: {res.get('id')}")
        return {"status": "commented", "id": res.get("id")}
    except Exception as e:
        m = str(e)
        if any(k in m.lower() for k in ("insufficient", "forbidden", "403", "scope")):
            log("⚠ 자동 댓글 실패(권한): force-ssl 스코프 없음 → "
                "youtube_login_setup.py 로 1회 재인증(재동의) 필요")
        else:
            log(f"자동 댓글 실패(발행은 정상): {type(e).__name__}: {m[:120]}")
        return {"error": m[:200]}


def add_to_playlist(video_id, kind="news", cfg=None):
    """발행한 영상을 유형별 재생목록에 담는다(연속 시청·구독 전환용).

    kind: news|career|quiz — config.youtube.playlists 에서 id 를 찾는다.
    force-ssl 스코프 필요. 실패해도 발행에는 영향 없도록 예외를 삼킨다.
    """
    cfg = cfg or load_config()
    pid = (cfg.get("youtube", {}).get("playlists", {}) or {}).get(kind)
    if not (pid and video_id):
        return {"skipped": "no playlist id"}
    try:
        yt = build("youtube", "v3", credentials=_creds(), cache_discovery=False)
        # 이미 담긴 영상이면 건너뛴다(재실행·수동 재발행 시 중복 방지).
        dup = yt.playlistItems().list(part="id", playlistId=pid, videoId=video_id,
                                      maxResults=1).execute().get("items", [])
        if dup:
            log(f"재생목록 이미 포함({kind}) — 편입 생략")
            return {"status": "already", "playlist": pid}
        yt.playlistItems().insert(part="snippet", body={"snippet": {
            "playlistId": pid,
            "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
        log(f"재생목록 편입 완료({kind})")
        return {"status": "added", "playlist": pid}
    except Exception as e:
        log(f"재생목록 편입 실패(발행은 정상): {type(e).__name__}: {str(e)[:100]}")
        return {"error": str(e)[:200]}


def _latest_data():
    files = sorted(f for f in os.listdir(POSTS_DIR) if f.endswith(".json"))
    if not files:
        raise SystemExit("먼저 파이프라인(generate_script→render_frames→tts→make_video)을 실행하세요.")
    with open(os.path.join(POSTS_DIR, files[-1]), "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    data = _latest_data()
    if "--private" in sys.argv:
        # 실제 업로드하되 비공개로(안전 테스트)
        print(upload(data, dry_run=False, privacy="private"))
    elif "--public" in sys.argv:
        print(upload(data, dry_run=False, privacy="public"))
    else:
        # 기본: 업로드 안 함(안전)
        print(upload(data, dry_run=True))
