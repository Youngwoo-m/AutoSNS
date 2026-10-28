"""계획표(schedule.json)의 한 편을 Claude 로 대본(script.json)으로 만든다.

  .venv/bin/python write_script.py 2026-10-13
근거: 국민안전24 국민행동요령 원문(source.md 로 저장). 장면마다 근거 문장(source_quote)을
원문에서 그대로 옮기게 하고, 원문에 실제로 있는지 검사한다 — 없으면 다시 쓰게 한다.
"""
import html, json, os, re, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
CATS = json.load(open(os.path.join(HERE, "safekorea_categories.json"), encoding="utf-8"))
AUTOSNS = "/Volumes/USB256/devAPP/AutoSNS/channels/youtube-shorts-auto"
sys.path.insert(0, AUTOSNS); sys.path.insert(0, os.path.dirname(AUTOSNS))
ROOT = CFG["root"]

STYLE_PREFIX = ("Style: photorealistic documentary footage filmed on location in Korea at real-world scale, natural light, "
                "realistic materials and textures, natural-looking Korean people of mixed ages moving at real-time speed. "
                "Thin, subtle glowing blue architectural wireframe outlines appear only on buildings in view; land, trees, water, "
                "roads, sky, vehicles and people stay completely natural with no blue lines. All walls, signboards, banners, screens "
                "and vehicles are plain and unmarked; single continuous shot, no captions or on-screen graphics. "
                "Avoid: miniature or tilt-shift look, toy models, cartoon or video-game CGI, text, letters, numbers, logos.")
# 장면마다 카메라 — 대본의 "camera" 값(aerial/eye). 영상은 움직임까지 정해 Veo 의 제멋대로 카메라를 막는다(10/12 프롬프트 개선)
CAMERA = {"aerial": " Camera: wide establishing shot from a high drone, slow steady forward glide, level horizon.",
          "eye": " Camera: eye-level medium-wide shot, 35mm lens, steady tripod with a slow gentle push-in; "
                 "the people and their actions fill a large part of the frame."}
CAMERA_IMAGE = {"aerial": " Camera: wide establishing shot from a high drone, level horizon.",
                "eye": " Camera: eye-level medium-wide shot, 35mm lens; the people and their actions fill a large part of the frame."}
# 지하 단면 — 장면의 "cutaway": true 일 때만 붙인다(땅속을 보여 줘야 이해되는 장면만)
CUTAWAY = (" Part of the ground is cut away as a clean vertical cross-section revealing the real soil and rock layers "
           "underneath, to show what happens below the surface.")

RULES = """영상 프롬프트 규칙(지난 편에서 배운 것 — 반드시 지킬 것):
- 파란 설계도 선은 장면에 건물이 있을 때 그 건물에만 그려진다(스타일 문구가 처리). video_prompt 에 파란 선·화살표·안내선을 쓰지 않는다. 건물이 필요 없는 장면(실내, 숲, 사람 행동)에 건물을 일부러 넣지 않는다.
- camera: 지형·피해 규모·마을 전체를 보여 줄 장면은 aerial, 사람의 행동(신고, 소화, 대피, 준비)을 보여 줄 장면은 eye. shots 의 컷마다 따로 정할 수 있다.
- 땅속 단면(cutaway)은 땅속을 보여 줘야 이해되는 장면에만 true(예: 산사태 흙층, 싱크홀, 지반·기초, 지하 침수). 그 밖에는 false.
- 대피 장면(사람이 위험을 피해 대피소로 가는 장면)은 shots 로 4초짜리 두 컷으로 나눈다: 컷0 = 가까운 곳의 위험을 뒤로하고 사람들이 카메라 쪽으로 서둘러/뛰어서 피함, 컷1 = 대피소(학교·마을회관) 앞에서 사람들이 서둘러 들어가는 모습. 위급한 장면에서 사람은 걷지 않고 서두르거나 뛴다. 한 컷 안에서 '왼쪽→오른쪽' 같은 방향 지시는 AI 가 지키지 않는다(2026-10-06 산불편).
- 장면 하나 = 8초짜리 한 컷(대피 장면만 shots 두 컷 예외). 'then' 으로 장면을 이어 붙이지 말고 동작 하나만 쓴다.
- 실제 크기의 사실적인 풍경·사람(축소 모형, 인형, 만화 느낌 금지).
- video_prompt 에 카메라·구도 낱말(aerial, drone, close-up, wide shot, zoom)을 쓰지 않는다 — camera 값으로만 정한다(겹치면 AI 가 헷갈림).
- video_prompt 좋은 예: \"Two Korean high school students in school uniforms crouch low and cover their heads under a sturdy classroom desk as the room shakes and books slide off the shelves, on a weekday morning with bright light coming through the windows.\"
- 빨간 선·윤곽은 '위험한 곳'에만, 그것도 위험 요소(불, 물, 무너지는 곳) 바로 위에만 쓴다. 대피 장소·안전한 곳에는 절대 빨간색을 쓰지 않는다.
- 대피 방향은 선·화살표 없이 구도로 보여 준다: 반드시 위험 요소에서 멀어지는 방향, 안전한 장소에 도착하는 모습.
- 영상 안에 글자·숫자·간판이 나오지 않게. AI 가 그린 한글은 깨진다 → 이름이 붙은 건물 정면(소방서·가게 간판), 표지판, 현수막, 화면을 장면 중심에 두지 않는다(예: 소방서 대신 소방차·소방관). 화면에 필요한 글자는 labels_3d 로 넣는다.
- 대피 장면에서 사람은 위험 요소(산비탈·불·물)를 등지고 안전한 곳을 향해 서둘러 이동한다(10/6 산사태편: 가족이 산비탈 쪽 건물로 걸어가는 것처럼 보임).
- 위험 장면(산사태·불 등)은 건물·간판이 화면에 들어오지 않게 지형만 잡는다(간판 글자가 깨져 나옴).
- 다치거나 숨진 사람, 공포를 주는 장면 금지. 대피·예방 행동을 보여 준다.
- 한국 풍경(한국 산·아파트·도로·마을)으로.
대본 규칙:
- narration 에는 숫자를 숫자로(119), tts_text 에만 한글로(일일구).
- 원문에 조건이 붙은 행동(예: '건물에 갇혔을 때만 높은 층으로')을 조건 없이 일반 수칙처럼 쓰지 않는다.
- 대피 방향은 원문 표현 그대로(예: '산에서 떨어진 곳', '계곡을 피해서').
- 제목·나레이션에서 원문 범위를 넘는 과장 금지(예: '~만 하면 막아요', '순식간에'). 효과를 단정하지 말고 '대비해요', '줄일 수 있어요'처럼."""

FACT = """너는 재난 안전 사실 검증자야. 아래 [대본]이 [원문]과 어긋나는 '실제 오류'만 찾아.
실제 오류는 다음 네 가지뿐이다:
 A 원문에 없는 행동·숫자를 지어냄
 B 원문과 반대이거나 다른 행동·숫자
 C 조건을 빼 버려 뜻이 위험하게 달라짐(예: '갇혔을 때만'을 빼서 늘 그렇게 하라는 뜻이 됨)
 D 대피 방향이 반대이거나, 영상 프롬프트가 위험 쪽으로 가는 모습·안전한 곳의 빨간 표시를 보여 줌
다음은 오류가 아니다(쓰지 마): 원문 내용 일부를 생략함, 요약이 짧음, 세부 방법을 덜 씀, 보완하면 좋겠다는 제안, 표기(숫자·한글) 차이, 영상이 덜 자세함.
출력: 첫 줄에 OK 또는 FIX. FIX 면 둘째 줄부터 '- 장면N [A|B|C|D]: 문제와 고칠 방향'. A~D 에 해당하는 것이 하나도 없으면 반드시 OK.

[대본]
{script}

[원문]
{source}"""

PROMPT = """너는 세명대학교 재난안전학과의 유튜브 숏츠 대본 작가야.
시리즈: 「재난 유형별 피해 양상과 대응 방안」, 이번 편 주제: {type} — {angle}
방송일: {date} ({weekday}요일 아침), 다음 편 주제: {next_type}

아래 [원문]은 행정안전부 국민안전24의 '{type}' 국민행동요령이야. 대본의 모든 행동 수칙은 이 원문에 있는 내용만 써.
원문에 없는 숫자·통계·사례를 지어내지 마.

말투: 나레이션의 모든 문장은 '~습니다.' / '~합니다.' / '~입니다.'(합쇼체)로 끝낸다('~요'로 끝내지 않는다). 낱말은 초등학생도 알 만큼 쉽게, 문장은 짧게. 명령문 대신 '~합니다', '~해야 합니다'로.
제목도 '~요'로 끝내지 않는다(명사형이나 '~합니다').
{length_rule}

{rules}

JSON 하나만 출력해(설명 금지). 형식:
{{
 "title": "제목(40자 이내, 호기심 + 주제) | 재난 대응 #{ep_no} {type}",
 "hook_text": "영상 첫 2.6초에 크게 띄울 훅(2줄 이내, 줄당 11자 이내, 경고·질문 한마디. 장면 1 첫 문장의 핵심)",
 "scenes": [
  {{"id": 1, "role": "훅 + 피해 양상",
    "narration": "...",
    "tts_text": "나레이션과 같되 숫자는 한글로 읽는 대로(119→일일구, 30분→삼십 분)",
    "subtitle": ["화면 자막 1(18자 이내, 명사형·'~요' 금지)", "화면 자막 2"],
    "labels_3d": ["화면 꼬리표 1(10자 이내)", "꼬리표 2"],
    "source_quote": ["이 장면의 근거가 된 원문 문장을 원문 그대로 복사"],
    "media": "{media_hint}",
    "camera": "aerial 또는 eye",
    "cutaway": false,
    "shots": "(선택) 대피 장면이면 [{{\"seconds\": 4, \"camera\": \"eye\", \"prompt\": \"컷0 영어\"}}, {{\"seconds\": 4, \"camera\": \"eye\", \"prompt\": \"컷1 영어\"}}], 아니면 생략",
    "video_prompt": "영어 1~2문장, 이 순서로: 누가(나이·옷차림) → 동작 하나(몸 움직임 동사) → 어디서(한국의 구체적 장소, 계절·날씨·시간대) → 빛. 스타일·카메라 문구는 내가 붙임. 파란 선·화살표·카메라 낱말 금지"}},
  ...{card_hint}
 ],
 "tags": ["유튜브 검색 태그 6~8개"],
 "hashtags": {{
   "youtube": ["3~4개. 첫째는 재난 이름, 나머지는 사람들이 실제로 검색할 구체적 키워드(예: 산불예방, 산불대피)"],
   "instagram": ["5개. 구체 키워드 + 계절 키워드(예: 가을산행)"],
   "threads": "주제 태그 1개(가장 많이 검색될 말)",
   "naver": ["10개. 띄어쓰기 없는 검색어"]
 }}
}}
해시태그는 '#' 없이, 띄어쓰기 없이 써. '재난대응' 같은 넓은 말보다 구체적인 말을 우선해.

[원문]
{source}
"""


def fetch_source(type_):
    cat = CATS.get(type_)
    if not cat:
        raise SystemExit(f"국민안전24 유형 코드를 모릅니다: {type_} (tools/safekorea_categories.json 에 추가 필요)")
    url = f"https://www.safekorea.go.kr/safekorea-kor/acts/nacts/action-guide.do?category={cat}&menuSn=4"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    h = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
    t = html.unescape(re.sub(r"<[^>]+>", "\n", h))
    t = "\n".join(l.strip() for l in t.splitlines() if l.strip())
    a = t.find("행동요령\n", t.find("관련동영상")) if "관련동영상" in t else -1
    if a < 0 and "행동요령 PDF다운로드" in t:   # 관련동영상이 없는 쪽(예: 지반침하)은 PDF 버튼 다음부터(10/15, 메뉴 글자 섞임 방지)
        a = t.find("\n", t.find("행동요령 PDF다운로드")) + 1
    if a < 0:
        a = t.find(f"{type_.split('(')[0].strip()} 국민행동요령")
    if a < 0:
        a = t.find("행동요령")
    if "자율안전점검" in t[a:a + 800] and "행동요령 PDF다운로드" in t:   # 그래도 사이트 메뉴가 섞이면 PDF 버튼 다음부터
        a = t.find("\n", t.find("행동요령 PDF다운로드")) + 1
    if "자율안전점검" in t[a:a + 800] and "\n재난 현황\n" in t:       # PDF 버튼이 없는 쪽(다중운집사고 등)은 '재난 현황' 다음부터
        a = t.find("\n", t.rfind("\n재난 현황\n") + 1) + 1
    b = t.find("소관부서")
    body = t[a:b] if a >= 0 and b > a else t
    if len(body) < 200:
        raise SystemExit(f"원문이 너무 짧습니다({len(body)}자) — 페이지 구조가 바뀌었는지 확인: {url}")
    return url, body


LOOP_FROM = "2026-10-16"       # 이날 방송분부터 루프 구조(인트로·아웃트로 없음), 사용자 결정 2026-10-14
LONG_FROM = "2026-11-01"        # 이날부터 50초판(6부분 + 정리 카드), 사용자 결정 2026-10-08
LONG_MEDIA = ["video", "diorama", "image", "image", "video", "card"]   # 2 = 실사 디오라마 + 계기판(10/15 사용자 결정)
MODEL_FROM = "2026-10-16"       # 이날 방송분부터 모형 장면 1개(짧은 편 = 장면 1, 50초판 = 장면 2)
MODEL_RULE = ("\n디오라마 장면(media \"diorama\", 10/15 사용자 결정): 실제 작업대 위에 만든 정교한 축소 모형(디오라마)을 실사로 찍은 영상으로 그 장면 나레이션의 원리를 보여 준다. 그 장면에 \"diorama_prompt\": \"영어 1~2문장: 어떤 축소 모형인지(단면이 필요하면 흙층·바위층이 보이는 잘린 앞면), 그 안에서 무엇이 어떻게 움직이는지(동작 하나)\" 와 \"gauge\" 를 쓴다. gauge 는 그 장면 나레이션에 계기로 재는 양(땅 울림·진동, 기온·체온, 비의 양, 풍속, 습도, 수위)이 직접 나올 때만 \"한국어 한 줄: 계기 하나(진동계·온도계·우량계·풍속계·습도계·수위계 중)와 바늘이 어떻게 움직이는지\", 그렇지 않으면 빈 문자열(\"\"). 계기판은 꼭 필요할 때만 넣는다(10/15 사용자 지시). 나레이션은 그 모형으로 보여 줄 수 있는 원리(왜 위험한지, 어떤 신호인지)로 쓴다. 대체용 video_prompt 도 함께 쓴다. 사람이 다치는 모습은 넣지 않는다.")
LEN_SHORT = "길이: 장면 3개, 나레이션 합계 한글 75~85자(약 14~16초, Voicebox 음성 기준 추정 — 2026-10-22 사용자 지시로 더 짧게, 글자 수는 그대로). 문장은 짧게 끊는다. 장면 1은 시청자가 멈춰 보게 만드는 훅 + 피해 양상, 장면 2·3은 대응 방법."
LEN_LONG = ("길이: 6부분, 나레이션 합계 한글 190~225자(약 36~42초, Voicebox 음성 기준 추정), 각 부분 28~40자. 수칙마다 이유나 예시를 원문 범위 안에서 붙여 지금보다 자세히.\n"
            "1 = 훅 + 피해 양상(media video, 움직임이 중요한 장면), 2 = 피해 특징·위험한 이유(media image, 디오라마 편이면 diorama), "
            "3 = 미리 지킬 일·예방(media image), 4 = 일이 났을 때 행동(media image), "
            "5 = 원문에 대피가 나오는 주제면 대피(shots 두 컷), 원문에 대피가 없으면 원문에 있는 가장 중요한 행동 하나(shots 없이 한 컷) — media video. 원문에 없는 대피·이동을 지어내지 않는다, "
            "6 = 정리(media card): narration 은 '정리합니다.'로 시작해 수칙 세 가지를 한 문장으로, "
            "card = {{\"title\": \"오늘의 핵심\", \"items\": [세 줄, 각 20자 이내]}}, subtitle·labels_3d 는 빈 목록, video_prompt 는 빈 문자열.\n"
            "그림(image) 장면은 사람이 크게 보이는 눈높이 장면으로 쓴다.")


LOOP_RULE = ("\n루프 구조(반복 재생 때 끝이 처음으로 이어지게, 인트로·아웃트로 없음):\n"
             "- 장면 1 첫 문장은 인사·소개 없이 바로 훅으로 시작한다(예: '축제 인파 속에서는 몇 초 만에 넘어질 수 있습니다.').\n"
             "- 마지막 장면의 마지막 문장은 '다리 문장'이다: 장면 1 첫 문장 바로 앞에 붙여 읽었을 때 한 이야기처럼 자연스럽게 이어져야 한다"
             "(예: '그래서 꼭 기억해야 할 사실이 있습니다.' → 처음으로). 다리 문장도 '~습니다/~합니다'로 끝낸다.\n"
             "- '다음 편', '이상', '감사합니다', '안녕하세요' 같은 시작·끝맺음 인사를 쓰지 않는다.\n"
             "- 다리 문장은 이 편의 첫 문장에 맞춰 새로 쓴다(예시 문장을 그대로 베끼지 않는다). 정리 장면이면 정리 뒤에 다리 문장을 둔다.\n"
             "- JSON 에 \"loop_bridge\": \"마지막 문장 + ' → ' + 첫 문장\" 을 함께 써서 이어짐을 보여 준다.")


def _n(s):
    return re.sub(r"[^가-힣0-9]", "", s)


def check(sc, source, long=False, loop=False, model=False):
    errs = []
    if model:
        want = 2 if long else 1
        ms = [s for s in sc.get("scenes", []) if s.get("media") == "diorama"]
        if len(ms) != 1 or ms[0].get("id") != want:
            errs.append(f"디오라마 장면은 장면 {want} 하나만 media \"diorama\"")
        elif not (ms[0].get("diorama_prompt") or "").strip():
            errs.append(f"장면 {want} diorama_prompt 누락")
    if loop:
        first = (sc["scenes"][0]["narration"] if sc.get("scenes") else "").strip()
        last = (sc["scenes"][-1]["narration"] if sc.get("scenes") else "").strip()
        if re.match(r"(안녕|세명대|저는)", first):
            errs.append("루프: 장면 1 은 인사 없이 바로 훅으로")
        if re.search(r"(다음 편|이상으로|감사합니다|말씀 드렸습니다|말씀드렸습니다)", last):
            errs.append("루프: 마지막 문장에 끝맺음 인사 금지 — 첫 문장으로 이어지는 다리 문장으로")
        if not sc.get("loop_bridge"):
            errs.append("루프: loop_bridge(마지막 문장 → 첫 문장) 누락")
    src = _n(source)
    total = sum(len(re.findall(r"[가-힣0-9]", s["narration"])) for s in sc["scenes"])
    lo, hi, n_sc = (180, 235, 6) if long else (65, 95, 3)
    if not lo <= total <= hi:
        errs.append(f"나레이션 길이 {total}자 ({lo + 10}~{hi - 10}자로)")
    if long:
        media = [x.get("media") for x in sc["scenes"]]
        if media != (LONG_MEDIA if model else [m if m != "diorama" else "image" for m in LONG_MEDIA]):
            errs.append(f"media 순서는 {LONG_MEDIA} (지금 {media})")
        card = (sc["scenes"][-1].get("card") or {}) if sc["scenes"] else {}
        items = card.get("items") or []
        if len(items) != 3 or any(len(i) > 22 for i in items):
            errs.append("정리 카드 items 는 3줄, 각 20자 이내")
    if re.search(r"요[!?.]?\s*$", sc.get("title", "").split("|")[0]):
        errs.append("제목이 '~요'로 끝남 — 명사형이나 '~합니다'로")
    if len(sc["scenes"]) != n_sc:
        errs.append(f"장면은 {n_sc}개")
    h = sc.get("hashtags") or {}
    if not (3 <= len(h.get("youtube", [])) <= 4 and len(h.get("instagram", [])) == 5
            and isinstance(h.get("threads"), str) and h.get("threads") and len(h.get("naver", [])) == 10):
        errs.append("hashtags: 유튜브 3~4개, 인스타 5개, 스레드 1개(문자열), 네이버 10개")
    for s in sc["scenes"]:
        if s.get("media") == "card":
            for sent in re.split(r"(?<=[.!?])\s+", s["narration"].strip()):
                if sent and not re.search(r"다[.!?]?$", sent):
                    errs.append(f"정리 문장이 '~다.'로 끝나지 않음: {sent[:30]}")
            continue
        for q in s.get("source_quote") or []:
            if _n(q) and _n(q) not in src:
                errs.append(f"장면 {s['id']} 근거 문장이 원문에 없음: {q[:40]}")
        if not s.get("source_quote"):
            errs.append(f"장면 {s['id']} 근거 문장 없음")
        for sent in re.split(r"(?<=[.!?])\s+", s["narration"].strip()):
            if sent and not re.search(r"다[.!?]?$", sent):
                errs.append(f"장면 {s['id']} 문장이 '~다.'로 끝나지 않음: {sent[:30]}")
        for sub in s.get("subtitle", []) + s.get("labels_3d", []):
            if re.search(r"요[!?.]?\s*$", re.sub(r"[^\w가-힣!?.]+$", "", sub)):
                errs.append(f"장면 {s['id']} 자막·꼬리표가 '~요'로 끝남: {sub} — 짧은 명사형으로")
        if "일일구" in s["narration"]:
            errs.append(f"장면 {s['id']} narration 에는 119 를 숫자로")
        if re.search(r"\b(wireframe|arrows?|guide lines?)\b|\b(blue|glowing)\s+(\w+\s+){0,2}(lines?|outlines?|arrows?|grid)\b", s["video_prompt"] + " ".join(x.get("prompt", "") for x in (s.get("shots") or []) if isinstance(x, dict)), re.I):
            errs.append(f"장면 {s['id']} 영상 프롬프트에 선·화살표 묘사 — 파란 선은 건물에만(스타일이 처리)")
        if re.search(r"\bthen\b", s["video_prompt"], re.I):
            errs.append(f"장면 {s['id']} 영상 프롬프트에 'then'(두 컷) 사용")
    return errs


def next_label(date, nxt):
    """아웃트로 위 문구 — 다음 편 요일과 주제(예: '다음 편 금요일: 산불 2편')."""
    if not nxt:
        return ""
    import datetime as dt
    wd = "월화수목금토일"[dt.date.fromisoformat(nxt["date"]).weekday()]
    gap = (dt.date.fromisoformat(nxt["date"]) - dt.date.fromisoformat(date)).days
    when = f"이번 주 {wd}요일" if gap < 7 and wd != "화" else f"다음 주 {wd}요일"
    sch = json.load(open(os.path.join(ROOT, "schedule.json"), encoding="utf-8"))["episodes"]
    n = sum(1 for x in sch if x["type"] == nxt["type"] and x["date"] <= nxt["date"])
    return f"{when}: {nxt['type']}" + (f" {n}편" if n > 1 else "")


def write(date, loop=False, sample=False):
    sch = json.load(open(os.path.join(ROOT, "schedule.json"), encoding="utf-8"))["episodes"]
    i = next(k for k, e in enumerate(sch) if e["date"] == date)
    e = sch[i]; nxt = sch[i + 1] if i + 1 < len(sch) else None
    ep_no = sum(1 for x in sch[:i + 1] if x["type"] == e["type"])
    ep_dir = os.path.join(ROOT, ("sample_loop_" if sample else "") + f"{date}_{e['type'].replace(' ', '').replace('/', '·')}")
    os.makedirs(os.path.join(ep_dir, "clips"), exist_ok=True)
    out = os.path.join(ep_dir, "script.json")
    if os.path.exists(out):
        print("대본 이미 있음:", out); return ep_dir
    long = date >= LONG_FROM
    loop = loop or date >= LOOP_FROM
    model = date >= MODEL_FROM
    url, source = fetch_source(e["type"])
    open(os.path.join(ep_dir, "source.md"), "w", encoding="utf-8").write(f"# 출처: 국민안전24 — {e['type']}\n{url}\n\n{source}\n")
    from common import load_config
    from shared.llm import client
    cfg = load_config()
    msgs = [{"role": "user", "content": PROMPT.format(type=e["type"], angle=e["angle"], date=date,
                                                       next_type=nxt["type"] if nxt else "", rules=RULES,
                                                       ep_no=ep_no, source=source[:12000],
                                                       weekday="월화수목금토일"[__import__("datetime").date.fromisoformat(date).weekday()],
                                                       length_rule=(LEN_LONG if long else LEN_SHORT) + (LOOP_RULE if loop else "") + (MODEL_RULE + (" 50초판은 장면 2 가 모형(정해진 media 순서대로)." if long else " 장면 1 의 media 를 \"diorama\" 로.") if model else ""),
                                                       media_hint=("video|diorama|image|card (정해진 순서대로)" if model else "video|image|card (정해진 순서대로)") if long else ("diorama 또는 video" if model else "video"),
                                                       card_hint=(',\n  {"id": 6, "media": "card", "narration": "정리합니다. ...", "tts_text": "...", '
                                                                  '"subtitle": [], "labels_3d": [], "source_quote": [], "video_prompt": "", '
                                                                  '"card": {"title": "오늘의 핵심", "items": ["...", "...", "..."]}}') if long else "")}]
    for attempt in range(5):
        r = client(cfg).messages.create(model=cfg.get("model", "claude-sonnet-4-6"), max_tokens=3000, messages=msgs)
        txt = "".join(getattr(b, "text", "") for b in r.content)
        m = re.search(r"\{.*\}", txt, re.S)
        try:
            gen = json.loads(m.group(0))
        except Exception:
            msgs += [{"role": "assistant", "content": txt}, {"role": "user", "content": "JSON 형식이 깨졌어. JSON 하나만 다시."}]
            continue
        errs = check(gen, source, long, loop, model)
        if not errs:
            v = client(cfg).messages.create(model=cfg.get("model", "claude-sonnet-4-6"), max_tokens=1200, messages=[
                {"role": "user", "content": FACT.format(script=json.dumps(gen["scenes"], ensure_ascii=False, indent=1),
                                                        source=source[:12000])}])
            verdict = "".join(getattr(b, "text", "") for b in v.content).strip()
            real = [l for l in verdict.splitlines() if re.match(r"\s*-\s*장면\s*\d+\s*\[[ABCD]\]", l)]
            if not verdict.upper().lstrip().startswith("FIX") or not real:   # 분류 없는 지적(생략·제안)은 통과(10/14)
                break
            verdict = "FIX\n" + "\n".join(real)
            errs = ["사실 검증: " + verdict[:1200]]
        print("검사 실패, 다시 쓰게 함:", errs)
        last = gen
        msgs += [{"role": "assistant", "content": txt},
                 {"role": "user", "content": "아래 지적만 고치고, 이미 맞는 부분(길이·말투·형식)은 그대로 두고 JSON 전체를 다시 써:\n- " + "\n- ".join(errs)}]
    else:
        # 실패해도 마지막 초안과 이유를 남겨 사람이 고칠 수 있게 한다(2026-10-10 다중운집사고 2편)
        json.dump({"errors": errs, "draft": locals().get("last")}, open(os.path.join(ep_dir, "script_draft.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        raise SystemExit(f"대본 검사 5회 실패 — 초안을 script_draft.json 에 남김: {str(errs)[:300]}")
    sc = {"series": "재난 유형별 피해 양상과 대응 방안", "date": date, "type": e["type"], "angle": e["angle"], "ep_no": ep_no, "visual_mode": e.get("visual", "video"),
          "title": gen["title"], "intro": None if loop else "../common/intro.mp4", "outro": None if loop else "../common/outro.mp4",
          "loop": loop, "loop_bridge": gen.get("loop_bridge", ""), "hook_text": gen.get("hook_text", ""),
          "next_episode_text": next_label(date, nxt), "body_target_seconds": 43 if long else 20, "clip_seconds": 8,
          "format": "long50" if long else "short30", "max_seconds": 52 if long else 29.5,
          "tone": "쉬운 낱말 + 합쇼체(~습니다/~합니다)", "style": "3d_real", "style_prefix": {"3d_real": STYLE_PREFIX}, "cutaway_text": CUTAWAY, "camera_text": CAMERA, "camera_text_image": CAMERA_IMAGE, "prompt_order": "scene_first",
          "hashtags": gen.get("hashtags", {}), "scenes": [], "sources": [f"국민안전24 국민행동요령 — {e['type']} (source.md)"],
          "upload": {"description_notes": desc_notes(e["type"], loop),
                     "contains_synthetic_media": True, "tags": gen.get("tags", []) + ["세명대학교", "재난안전학과", "쇼츠"]}}
    for s in gen["scenes"]:
        s["video_prompt"] = {"3d_real": s.get("video_prompt") or "(정리 카드)"}
        s["cutaway"] = bool(s.get("cutaway", False))
        if s.get("camera") not in ("aerial", "eye"):
            s["camera"] = "aerial" if s.get("id") == 1 else "eye"
        if not isinstance(s.get("shots"), list) or not s["shots"]:
            s.pop("shots", None)
        sc["scenes"].append(s)
    json.dump(sc, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("대본 저장:", out)
    return ep_dir


def desc_notes(type_, loop):
    if loop:
        return f"출처: 행정안전부 국민안전24 국민행동요령({type_}) / 배경 영상은 AI로 생성한 3D 재현 영상입니다."
    return f"출처: 행정안전부 국민안전24 국민행동요령({type_}) / 인트로·아웃트로는 AI 아바타, 배경 영상은 AI로 생성한 3D 재현 영상입니다."


RELOOP = """너는 세명대학교 재난안전학과의 유튜브 숏츠 대본 작가야. 이미 만들어 둔 장면 영상은 그대로 쓰고, 나레이션만 루프 구조로 다시 쓴다.
이번 편 주제: {type} — {angle}
아래 [장면 영상]은 장면마다 화면에 나오는 모습이야. 각 장면의 나레이션은 그 화면과 어울려야 한다(화면에 없는 장면을 설명하지 않는다).
[원문]은 국민안전24 '{type}' 국민행동요령이야. 행동 수칙은 원문에 있는 것만 쓴다. 숫자·통계·사례를 지어내지 않는다.

말투: 모든 문장은 '~습니다.' / '~합니다.' / '~입니다.'로 끝낸다('~요' 금지). 낱말은 초등학생도 알 만큼 쉽게, 문장은 짧게.
{length_rule}
{loop_rule}
대본 규칙:
- narration 에는 숫자를 숫자로(119), tts_text 에만 한글로(일일구).
- 원문에 조건이 붙은 행동을 조건 없이 쓰지 않는다. 대피 방향은 원문 표현 그대로.
- subtitle: 화면 자막 2개(각 18자 이내, 명사형, '~요' 금지), labels_3d: 꼬리표 1~2개(10자 이내).
- source_quote: 그 장면의 근거 원문 문장을 원문 그대로 복사.

[장면 영상]
{scenes}

[지금 나레이션(참고, 구조만 바꾼다)]
{old}

JSON 하나만 출력(설명 금지):
{{"loop_bridge": "마지막 문장 → 첫 문장",
 "scenes": [{{"id": 1, "narration": "...", "tts_text": "...", "subtitle": ["..", ".."], "labels_3d": [".."], "source_quote": [".."]}}, ...]}}

[원문]
{source}"""


def reloop(ep):
    """이미 만든 편을 루프 구조로 — 장면 영상(video_prompt·shots·media)은 그대로, 나레이션·자막만 다시 쓴다(10/14)."""
    ep_dir = os.path.join(ROOT, ep); p = os.path.join(ep_dir, "script.json")
    sc = json.load(open(p, encoding="utf-8"))
    if sc.get("loop"):
        print("이미 루프 구조:", ep); return ep_dir
    long = sc.get("format") == "long50"
    source = open(os.path.join(ep_dir, "source.md"), encoding="utf-8").read().split("\n\n", 1)[-1]
    vis = []
    for s in sc["scenes"]:
        v = s["video_prompt"].get("3d_real", "") if isinstance(s["video_prompt"], dict) else s["video_prompt"]
        if s.get("shots"):
            v = " / ".join(f"컷{k}: {sh['prompt']}" for k, sh in enumerate(s["shots"]))
        vis.append(f"장면 {s['id']} ({s.get('media', 'video')}): {v}")
    from common import load_config
    from shared.llm import client
    cfg = load_config()
    msgs = [{"role": "user", "content": RELOOP.format(type=sc["type"], angle=sc.get("angle", ""), length_rule=LEN_LONG if long else LEN_SHORT,
                                                      loop_rule=LOOP_RULE, scenes="\n".join(vis),
                                                      old="\n".join(f"장면 {s['id']}: {s['narration']}" for s in sc["scenes"]),
                                                      source=source[:12000])}]
    for attempt in range(5):
        r = client(cfg).messages.create(model=cfg.get("model", "claude-sonnet-4-6"), max_tokens=2500, messages=msgs)
        txt = "".join(getattr(b, "text", "") for b in r.content)
        try:
            gen = json.loads(re.search(r"\{.*\}", txt, re.S).group(0))
            new = {x["id"]: x for x in gen["scenes"]}
            assert set(new) == {s["id"] for s in sc["scenes"]}
        except Exception:
            msgs += [{"role": "assistant", "content": txt}, {"role": "user", "content": "JSON 형식이나 장면 번호가 맞지 않아. 같은 장면 번호로 JSON 하나만 다시."}]
            continue
        cand = json.loads(json.dumps(sc))
        for s in cand["scenes"]:
            for k in ("narration", "tts_text", "subtitle", "labels_3d", "source_quote"):
                if k in new[s["id"]]:
                    s[k] = new[s["id"]][k]
        cand["loop_bridge"] = gen.get("loop_bridge", "")
        chk = dict(cand); chk["scenes"] = [dict(s, video_prompt=(s["video_prompt"].get("3d_real", "") if isinstance(s["video_prompt"], dict) else s["video_prompt"]))
                                            for s in cand["scenes"]]
        errs = [e for e in check(chk, source, long, loop=True) if "영상 프롬프트" not in e]   # 영상은 이미 만든 것 — 검사 제외
        if not errs:
            v = client(cfg).messages.create(model=cfg.get("model", "claude-sonnet-4-6"), max_tokens=1200, messages=[
                {"role": "user", "content": FACT.format(script=json.dumps([{k: s.get(k) for k in ("id", "narration")}   # 영상은 이미 만든 것 — 나레이션만 검증
                                                                           for s in chk["scenes"]], ensure_ascii=False, indent=1), source=source[:12000])}])
            verdict = "".join(getattr(b, "text", "") for b in v.content).strip()
            real = [l for l in verdict.splitlines() if re.match(r"\s*-\s*장면\s*\d+\s*\[[ABCD]\]", l)]
            if not verdict.upper().lstrip().startswith("FIX") or not real:
                break
            errs = ["사실 검증: " + "\n".join(real)]
        print("검사 실패, 다시 쓰게 함:", errs)
        msgs += [{"role": "assistant", "content": txt},
                 {"role": "user", "content": "아래 지적만 고치고 나머지는 그대로 두고 JSON 전체를 다시 써:\n- " + "\n- ".join(errs)}]
    else:
        raise SystemExit(f"루프 대본 검사 5회 실패: {str(errs)[:300]}")
    json.dump(sc, open(os.path.join(ep_dir, "script_preloop.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    cand.update({"loop": True, "intro": None, "outro": None})
    cand["upload"]["description_notes"] = desc_notes(cand["type"], True)
    json.dump(cand, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("루프 대본 저장:", p, "\n다리:", cand["loop_bridge"])
    return ep_dir


if __name__ == "__main__":
    if "--reloop" in sys.argv:
        reloop(sys.argv[1]); sys.exit()
    write(sys.argv[1], loop="--loop" in sys.argv, sample="--sample" in sys.argv)
