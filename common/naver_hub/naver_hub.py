"""네이버 검색·데이터랩 공용 클라이언트 — 다른 기능이 가져다 쓰는 얇은 계층.

키는 .env의 NAVER_SEARCH_CLIENT_ID·NAVER_SEARCH_CLIENT_SECRET(커머스·검색광고 키와 별개). 키 값은 로그·예외·응답 어디에도 남기지 않는다.
제공처는 NAVER_SEARCH_PROVIDER(openapi 기본|apihub). openapi는 developers.naver.com 오픈 API(openapi.naver.com,
X-Naver-Client-Id·Secret 헤더)로 검색·쇼핑·데이터랩이 모두 된다. apihub(NCP API HUB)는 예전 키를 쓸 때만. 호출 주소는 모두 고정(사용자 입력은 파라미터로만).
네이버가 보장하는 한도: 검색 계열 하루 25,000회, 키당 50 RPS, 초과하면 429. 호출 횟수 제한은 부르는 쪽 책임.
"""
import re

import httpx

HUB_BASE = "https://naverapihub.apigw.ntruss.com"
OPENAPI_BASE = "https://openapi.naver.com"
ID_KEY, SECRET_KEY, PROVIDER_KEY = "NAVER_SEARCH_CLIENT_ID", "NAVER_SEARCH_CLIENT_SECRET", "NAVER_SEARCH_PROVIDER"
KEY_MISSING = "검색 키가 필요해요(.env의 NAVER_SEARCH_CLIENT_ID·SECRET)"
TIMEOUT = 10.0
UA = {"User-Agent": "AutoSNS/1.0"}

# 검색 종류 → (display 최대, start 최대, 허용 sort, 추가 허용 파라미터 이름)
SEARCH_KINDS = {
    "news": (100, 1000, ("sim", "date"), ()),
    "encyc": (100, 1000, (), ()),
    "blog": (100, 1000, ("sim", "date"), ()),
    "webkr": (100, 1000, (), ()),
    "kin": (100, 1000, ("sim", "date", "point"), ()),
    "cafearticle": (100, 1000, ("sim", "date"), ()),
    "local": (5, 1, ("random", "comment"), ()),
    "image": (100, 1000, ("sim", "date"), ("filter",)),
    "shop": (100, 1000, ("sim", "date", "asc", "dsc"), ("exclude",)),
}
SHOP_EXCLUDES = ("used", "rental", "cbshop")
IMAGE_FILTERS = ("all", "large", "medium", "small")
TIME_UNITS = ("date", "week", "month")
DEVICES, GENDERS = ("pc", "mo"), ("m", "f")
INSIGHT_AGES = ("10", "20", "30", "40", "50", "60")
TREND_AGES = tuple(str(i) for i in range(1, 12))
# 데이터랩 API HUB 경로 → 오픈 API 경로
TREND_PATHS = {"apihub": "/search-trend/v1/search", "openapi": "/v1/datalab/search"}
# 쇼핑 인사이트: 이름 → (API HUB 경로, 'category' 필드 형태). 분야별은 category가 [{name,param}] 배열, 키워드별은 문자열 category + keyword 필드
INSIGHT_PATHS = {
    "categories": "/shopping/v1/categories",
    "category_device": "/shopping/v1/category/device",
    "category_gender": "/shopping/v1/category/gender",
    "category_age": "/shopping/v1/category/age",
    "keywords": "/shopping/v1/category/keywords",
    "keyword_device": "/shopping/v1/category/keyword/device",
    "keyword_gender": "/shopping/v1/category/keyword/gender",
    "keyword_age": "/shopping/v1/category/keyword/age",
}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TAG = re.compile(r"<[^>]+>")


class HubError(Exception):
    """요청이 잘못됐거나 거절됨. 메시지에 키는 없다."""


class HubUnavailable(HubError):
    """연결 실패·시간 초과·서버 오류 — 나중에 다시 시도할 만한 경우."""


class HubQuotaExceeded(HubUnavailable):
    """429 호출 한도 초과."""


def has_keys(env) -> bool:
    return bool((env or {}).get(ID_KEY)) and bool((env or {}).get(SECRET_KEY))


def provider(env) -> str:
    prov = str((env or {}).get(PROVIDER_KEY) or "openapi").strip().lower()
    if prov not in ("apihub", "openapi"):
        raise HubError("NAVER_SEARCH_PROVIDER는 apihub 또는 openapi만 쓸 수 있어요")
    return prov


def clean(text) -> str:
    """검색 결과의 <b> 강조 태그와 &quot; 등을 제거."""
    s = _TAG.sub("", str(text or ""))
    return s.replace("&quot;", '"').replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'").strip()


def _request(env, method, path, *, params=None, body=None, client=None):
    """공통 호출. (JSON dict) 반환. 키는 헤더로만 보내고 어떤 예외·메시지에도 넣지 않는다."""
    if not has_keys(env):
        raise HubError(KEY_MISSING)
    prov = provider(env)
    if prov == "openapi":
        base, headers = OPENAPI_BASE, {"X-Naver-Client-Id": env[ID_KEY], "X-Naver-Client-Secret": env[SECRET_KEY]}
    else:
        base, headers = HUB_BASE, {"X-NCP-APIGW-API-KEY-ID": env[ID_KEY], "X-NCP-APIGW-API-KEY": env[SECRET_KEY]}
    own = client is None
    client = client or httpx.Client(headers=UA, trust_env=False)
    try:
        if method == "POST":
            r = client.post(base + path, json=body, headers={**headers, "Content-Type": "application/json"}, timeout=TIMEOUT)
        else:
            r = client.get(base + path, params=params, headers=headers, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise HubUnavailable(f"네이버 API에 연결하지 못했어요 ({type(e).__name__})") from None
    finally:
        if own:
            client.close()
    if r.status_code == 429:
        raise HubQuotaExceeded("네이버 API 호출 한도를 넘었어요 (HTTP 429)")
    if r.status_code >= 500:
        raise HubUnavailable(f"네이버 API 서버 오류 (HTTP {r.status_code})")
    if r.status_code != 200:
        raise HubError(f"네이버 API가 거절했어요 (HTTP {r.status_code})")
    try:
        data = r.json()
    except ValueError:
        raise HubError("네이버 API 응답을 읽지 못했어요") from None
    if not isinstance(data, dict):
        raise HubError("네이버 API 응답 형식이 달라요")
    return data


def _paged(path_kind, env, query, display, start, sort, extra, client):
    spec = SEARCH_KINDS.get(path_kind)
    if spec is None:
        raise HubError(f"지원하지 않는 검색 종류예요: {path_kind}")
    dmax, smax, sorts, _extra = spec
    query = str(query or "").strip()[:100]
    if not query:
        raise HubError("검색어가 없어요")
    if not 1 <= int(display) <= dmax:
        raise HubError(f"display는 1~{dmax}만 쓸 수 있어요")
    if not 1 <= int(start) <= smax:
        raise HubError(f"start는 1~{smax}만 쓸 수 있어요")
    if sort and sort not in sorts:
        raise HubError(f"{path_kind} 검색의 sort는 {'/'.join(sorts) or '지원 안 함'}만 쓸 수 있어요")
    params = {"query": query, "display": int(display), "start": int(start)}
    if sort:
        params["sort"] = sort
    if path_kind == "image" and extra.get("filter"):
        if extra["filter"] not in IMAGE_FILTERS:
            raise HubError("filter는 all/large/medium/small만 쓸 수 있어요")
        params["filter"] = extra["filter"]
    if extra.get("exclude"):
        if path_kind != "shop":
            raise HubError("exclude는 쇼핑 검색에서만 쓸 수 있어요")
        parts = str(extra["exclude"]).split(":")
        if any(p not in SHOP_EXCLUDES for p in parts):
            raise HubError("exclude는 used/rental/cbshop만 쓸 수 있어요")
        params["exclude"] = ":".join(parts)
    if provider(env) == "apihub":
        params["format"] = "json"
        path = f"/search/v1/{path_kind}"
    else:
        path = f"/v1/search/{path_kind}.json"
    return _request(env, "GET", path, params=params, client=client)


def search(env, kind, query, *, display=10, start=1, sort=None, filter=None, exclude=None, client=None) -> dict:
    """검색(news·encyc·blog·webkr·kin·cafearticle·local·image·shop). {total, items:[...]} — 제목·설명의 <b> 태그는 제거."""
    data = _paged(kind, env, query, display, start, sort, {"filter": filter, "exclude": exclude}, client)
    items = []
    for it in data.get("items") or []:
        if not isinstance(it, dict):
            continue
        row = dict(it)
        for k in ("title", "description", "bloggername", "cafename"):
            if k in row:
                row[k] = clean(row[k])
        items.append(row)
    try:
        total = int(data.get("total") or 0)
    except (TypeError, ValueError):
        total = 0
    return {"total": total, "items": items}


def is_adult(env, query, *, client=None) -> bool:
    """성인 검색어 판별. 근거 없이 0/1만 온다 — 반려 사유로 단독 사용하지 말고 1차 필터로만."""
    q = str(query or "").strip()[:100]
    if not q:
        raise HubError("검색어가 없어요")
    path = "/search/v1/adult" if provider(env) == "apihub" else "/v1/search/adult.json"
    params = {"query": q}
    if provider(env) == "apihub":
        params["format"] = "json"
    return str(_request(env, "GET", path, params=params, client=client).get("adult")) == "1"


def errata(env, query, *, client=None) -> str:
    """한/영 자판 오입력 교정 결과. 오타가 없으면 빈 문자열. 정상 영문 약어도 바뀔 수 있어 사람 확인과 함께 쓴다."""
    q = str(query or "").strip()[:100]
    if not q:
        raise HubError("검색어가 없어요")
    path = "/search/v1/errata" if provider(env) == "apihub" else "/v1/search/errata.json"
    params = {"query": q}
    if provider(env) == "apihub":
        params["format"] = "json"
    return str(_request(env, "GET", path, params=params, client=client).get("errata") or "").strip()


def _period(start_date, end_date, time_unit, floor):
    for d in (start_date, end_date):
        if not _DATE.match(str(d or "")):
            raise HubError("날짜는 yyyy-mm-dd 형식이에요")
    if str(start_date) < floor:
        raise HubError(f"시작일은 {floor} 이후만 조회할 수 있어요")
    if str(end_date) < str(start_date):
        raise HubError("종료일이 시작일보다 빨라요")
    if time_unit not in TIME_UNITS:
        raise HubError("timeUnit은 date/week/month만 쓸 수 있어요")
    return {"startDate": str(start_date), "endDate": str(end_date), "timeUnit": time_unit}


def _filters(body, device, gender, ages, allowed_ages):
    if device is not None:
        if device not in DEVICES:
            raise HubError("device는 pc/mo만 쓸 수 있어요")
        body["device"] = device
    if gender is not None:
        if gender not in GENDERS:
            raise HubError("gender는 m/f만 쓸 수 있어요")
        body["gender"] = gender
    if ages:
        ages = [str(a) for a in ages]
        if any(a not in allowed_ages for a in ages):
            raise HubError("ages 값이 범위를 벗어났어요")
        body["ages"] = ages
    return body


def _series(data) -> list[dict]:
    """results[] → [{title, keywords, data:[{period, ratio, group?}]}] (ratio는 최댓값=100인 상댓값, 절대 검색량이 아님)."""
    out = []
    for res in data.get("results") or []:
        if not isinstance(res, dict):
            continue
        rows = []
        for d in res.get("data") or []:
            if isinstance(d, dict) and d.get("period") is not None:
                row = {"period": str(d["period"]), "ratio": float(d.get("ratio") or 0)}
                if d.get("group") is not None:
                    row["group"] = str(d["group"])
                rows.append(row)
        out.append({"title": str(res.get("title") or ""), "keywords": list(res.get("keywords") or res.get("keyword") or res.get("category") or []),
                    "data": rows})
    return out


def search_trend(env, groups, start_date, end_date, time_unit="month", *, device=None, gender=None, ages=None, client=None) -> list[dict]:
    """검색어 트렌드. groups = [{"groupName": str, "keywords": [str, ...]}] (최대 5그룹, 그룹당 20개)."""
    if not groups or len(groups) > 5:
        raise HubError("키워드 그룹은 1~5개예요")
    kg = []
    for g in groups:
        kws = [str(k).strip() for k in (g.get("keywords") or []) if str(k).strip()]
        name = str(g.get("groupName") or "").strip()
        if not name or not kws or len(kws) > 20:
            raise HubError("그룹 이름과 키워드(최대 20개)가 필요해요")
        kg.append({"groupName": name, "keywords": kws})
    body = _filters({**_period(start_date, end_date, time_unit, "2016-01-01"), "keywordGroups": kg}, device, gender, ages, TREND_AGES)
    return _series(_request(env, "POST", TREND_PATHS[provider(env)], body=body, client=client))


def _insight_path(env, hub_path):
    """API HUB 경로(/shopping/v1/...)를 오픈 API 경로(/v1/datalab/shopping/...)로."""
    return hub_path if provider(env) == "apihub" else "/v1/datalab/shopping/" + hub_path.removeprefix("/shopping/v1/")


def shopping_insight(env, kind, category, start_date, end_date, time_unit="month", *, keyword=None, device=None,
                     gender=None, ages=None, client=None) -> list[dict]:
    """쇼핑 인사이트(클릭 추이). category는 네이버쇼핑 URL의 cat_id.

    kind: categories(분야별, category=[{name, param:[cat_id]}] 최대 3개) · category_device/gender/age(category=cat_id 문자열) ·
          keywords(keyword=[{name, param:[검색어]}] 최대 5개) · keyword_device/gender/age(keyword=검색어 문자열).
    """
    path = INSIGHT_PATHS.get(kind)
    if path is None:
        raise HubError(f"지원하지 않는 쇼핑 인사이트 종류예요: {kind}")
    body = _period(start_date, end_date, time_unit, "2017-08-01")
    if kind == "categories":
        if not isinstance(category, list) or not 1 <= len(category) <= 3:
            raise HubError("분야는 1~3개예요")
        body["category"] = [{"name": str(c.get("name") or ""), "param": [str(p) for p in c.get("param") or []]} for c in category]
    else:
        if not str(category or "").strip():
            raise HubError("category(cat_id)가 필요해요")
        body["category"] = str(category).strip()
        if kind == "keywords":
            if not isinstance(keyword, list) or not 1 <= len(keyword) <= 5:
                raise HubError("키워드는 1~5개예요")
            body["keyword"] = [{"name": str(k.get("name") or ""), "param": [str(p) for p in (k.get("param") or [])][:1]} for k in keyword]
        elif kind.startswith("keyword_"):
            if not str(keyword or "").strip():
                raise HubError("keyword가 필요해요")
            body["keyword"] = str(keyword).strip()
    # 기기·성별·연령별 API는 자기 기준 축을 필터로 받지 않는다 (기기별에 device 불가 등)
    own_axis = kind.rsplit("_", 1)[-1]
    if own_axis == "device" and device is not None or own_axis == "gender" and gender is not None or own_axis == "age" and ages:
        raise HubError("그 API는 자기 기준 축(기기·성별·연령)을 필터로 받을 수 없어요")
    return _series(_request(env, "POST", _insight_path(env, path), body=_filters(body, device, gender, ages, INSIGHT_AGES), client=client))
