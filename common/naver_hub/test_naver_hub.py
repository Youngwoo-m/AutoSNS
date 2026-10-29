import json

import httpx
import pytest

from naver_hub import naver_hub as hub

ENV = {"NAVER_SEARCH_CLIENT_ID": "fake-id", "NAVER_SEARCH_CLIENT_SECRET": "fake-secret"}
HUB = {**ENV, "NAVER_SEARCH_PROVIDER": "apihub"}


class Net:
    def __init__(self, payload=None, status=200):
        self.payload, self.status, self.seen = payload if payload is not None else {}, status, []

    def client(self):
        def handler(request):
            self.seen.append(request)
            return httpx.Response(self.status, json=self.payload)
        return httpx.Client(transport=httpx.MockTransport(handler))


def test_requires_keys():
    with pytest.raises(hub.HubError) as e:
        hub.search({}, "blog", "q", client=Net().client())
    assert "NAVER_SEARCH_CLIENT_ID" in str(e.value)


def test_search_apihub_url_headers_and_tag_cleanup():
    net = Net({"total": 3, "items": [{"title": "<b>등산</b>스틱 &quot;좋음&quot;", "link": "https://b.example/1",
                                      "description": "<b>설명</b>", "bloggername": "블로거"}, "junk"]})
    got = hub.search(HUB, "blog", " 등산스틱 ", display=5, sort="date", client=net.client())
    req = net.seen[0]
    assert str(req.url).startswith("https://naverapihub.apigw.ntruss.com/search/v1/blog?")
    assert req.headers["X-NCP-APIGW-API-KEY-ID"] == "fake-id" and req.headers["X-NCP-APIGW-API-KEY"] == "fake-secret"
    assert req.url.params["query"] == "등산스틱" and req.url.params["format"] == "json"
    assert req.url.params["display"] == "5" and req.url.params["sort"] == "date"
    assert got["total"] == 3 and len(got["items"]) == 1
    assert got["items"][0]["title"] == '등산스틱 "좋음"' and got["items"][0]["description"] == "설명"


def test_search_openapi_provider_uses_legacy_url_and_headers():
    net = Net({"items": []})
    hub.search({**ENV, "NAVER_SEARCH_PROVIDER": "openapi"}, "news", "q", client=net.client())
    req = net.seen[0]
    assert str(req.url).startswith("https://openapi.naver.com/v1/search/news.json?")
    assert req.headers["X-Naver-Client-Id"] == "fake-id" and "format" not in req.url.params
    assert "X-NCP-APIGW-API-KEY" not in req.headers


def test_search_validates_arguments_without_calling():
    net = Net()
    for kw in ({"kind": "movie"}, {"kind": "blog", "display": 101}, {"kind": "blog", "start": 1001},
               {"kind": "blog", "sort": "point"}, {"kind": "local", "start": 2}, {"kind": "encyc", "sort": "sim"},
               {"kind": "image", "filter": "huge"}):
        kind = kw.pop("kind")
        with pytest.raises(hub.HubError):
            hub.search(ENV, kind, "q", client=net.client(), **kw)
    with pytest.raises(hub.HubError):
        hub.search(ENV, "blog", "  ", client=net.client())
    with pytest.raises(hub.HubError):
        hub.search({**ENV, "NAVER_SEARCH_PROVIDER": "zzz"}, "blog", "q", client=net.client())
    assert net.seen == []


def test_image_filter_and_local_limits_pass():
    net = Net({"items": []})
    hub.search(ENV, "image", "q", display=30, sort="sim", filter="large", client=net.client())
    assert net.seen[0].url.params["filter"] == "large"
    hub.search(ENV, "local", "q", display=5, start=1, sort="comment", client=net.client())


def test_adult_and_errata():
    assert hub.is_adult(ENV, "q", client=Net({"adult": "1"}).client()) is True
    assert hub.is_adult(ENV, "q", client=Net({"adult": "0"}).client()) is False
    net = Net({"errata": "네이버"})
    assert hub.errata(HUB, "spdlqj", client=net.client()) == "네이버"
    assert str(net.seen[0].url).startswith("https://naverapihub.apigw.ntruss.com/search/v1/errata?")
    assert hub.errata(ENV, "네이버", client=Net({"errata": ""}).client()) == ""


def test_search_trend_body_and_parse():
    net = Net({"results": [{"title": "스틱", "keywords": ["등산스틱"], "data": [{"period": "2026-01-01", "ratio": 100}]}]})
    got = hub.search_trend(HUB, [{"groupName": "스틱", "keywords": ["등산스틱"]}], "2026-01-01", "2026-06-30",
                           "month", device="mo", ages=["3", "4"], client=net.client())
    req = net.seen[0]
    assert req.method == "POST" and req.url.path == "/search-trend/v1/search"
    assert req.headers["content-type"] == "application/json" and req.headers["X-NCP-APIGW-API-KEY"] == "fake-secret"
    body = json.loads(req.content)
    assert body == {"startDate": "2026-01-01", "endDate": "2026-06-30", "timeUnit": "month",
                    "keywordGroups": [{"groupName": "스틱", "keywords": ["등산스틱"]}], "device": "mo", "ages": ["3", "4"]}
    assert got == [{"title": "스틱", "keywords": ["등산스틱"], "data": [{"period": "2026-01-01", "ratio": 100.0}]}]


def test_search_trend_validation():
    g = [{"groupName": "a", "keywords": ["b"]}]
    net = Net({"results": []})
    for bad in (dict(groups=[]), dict(groups=g * 6), dict(groups=[{"groupName": "a", "keywords": []}]),
                dict(groups=g, start_date="2015-12-31"), dict(groups=g, start_date="2026/01/01"),
                dict(groups=g, end_date="2025-01-01"), dict(groups=g, time_unit="year"),
                dict(groups=g, ages=["12"]), dict(groups=g, device="tablet")):
        args = {"start_date": "2026-01-01", "end_date": "2026-02-01", "time_unit": "month", **bad}
        groups = args.pop("groups")
        with pytest.raises(hub.HubError):
            hub.search_trend(ENV, groups, args.pop("start_date"), args.pop("end_date"), args.pop("time_unit"),
                             client=net.client(), **args)
    assert net.seen == []


def test_shopping_insight_paths_and_bodies():
    net = Net({"results": [{"title": "정장", "keyword": ["정장"], "data": [{"period": "2026-01-01", "group": "f", "ratio": 50}]}]})
    got = hub.shopping_insight(HUB, "keyword_gender", "50000000", "2026-01-01", "2026-01-07", "date",
                               keyword="정장", ages=["20", "30"], client=net.client())
    req = net.seen[0]
    assert req.url.path == "/shopping/v1/category/keyword/gender"
    assert json.loads(req.content) == {"startDate": "2026-01-01", "endDate": "2026-01-07", "timeUnit": "date",
                                       "category": "50000000", "keyword": "정장", "ages": ["20", "30"]}
    assert got[0]["data"] == [{"period": "2026-01-01", "ratio": 50.0, "group": "f"}]
    hub.shopping_insight(HUB, "categories", [{"name": "패션", "param": ["50000000"]}], "2026-01-01", "2026-01-07",
                         client=net.client())
    assert net.seen[1].url.path == "/shopping/v1/categories"
    hub.shopping_insight(HUB, "keywords", "50000000", "2026-01-01", "2026-01-07",
                         keyword=[{"name": "정장", "param": ["정장", "무시"]}], client=net.client())
    assert json.loads(net.seen[2].content)["keyword"] == [{"name": "정장", "param": ["정장"]}]
    for kind, path in (("category_device", "device"), ("category_gender", "gender"), ("category_age", "age"),
                       ("keyword_device", "keyword/device"), ("keyword_age", "keyword/age")):
        hub.shopping_insight(HUB, kind, "50000000", "2026-01-01", "2026-01-07", keyword="x", client=net.client())
        assert net.seen[-1].url.path == f"/shopping/v1/category/{path}"


def test_shopping_insight_validation():
    net = Net({"results": []})
    base = ("2026-01-01", "2026-01-07")
    for args, kw in ((("nope", "1", *base), {}), (("categories", [], *base), {}),
                     (("categories", [{"name": "a", "param": ["1"]}] * 4, *base), {}),
                     (("keywords", "1", *base), {"keyword": [{"name": "a", "param": ["a"]}] * 6}),
                     (("keyword_age", "1", *base), {}), (("keyword_device", "1", *base), {"keyword": "x", "device": "pc"}),
                     (("category_gender", "1", *base), {"gender": "m"}), (("category_age", "1", *base), {"ages": ["20"]}),
                     (("category_device", "1", "2017-07-31", "2017-08-02"), {}), (("category_device", "", *base), {})):
        with pytest.raises(hub.HubError):
            hub.shopping_insight(ENV, *args, client=net.client(), **kw)
    assert net.seen == []


def test_errors_are_classified_and_never_contain_keys():
    def boom(request):
        raise httpx.ConnectError("fake-id fake-secret")
    with pytest.raises(hub.HubUnavailable) as e:
        hub.search(ENV, "blog", "q", client=httpx.Client(transport=httpx.MockTransport(boom)))
    assert "fake" not in str(e.value)
    for status, exc in ((429, hub.HubQuotaExceeded), (500, hub.HubUnavailable), (401, hub.HubError), (403, hub.HubError)):
        client = Net({"errorCode": "x", "errorMessage": "fake-id"}, status).client()
        with pytest.raises(exc) as e:
            hub.search(ENV, "blog", "q", client=client)
        assert "fake" not in str(e.value) and f"{status}" in str(e.value)
    assert issubclass(hub.HubQuotaExceeded, hub.HubUnavailable)
    bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="not json")))
    with pytest.raises(hub.HubError):
        hub.search(ENV, "blog", "q", client=bad)
    with pytest.raises(hub.HubError):
        hub.search(ENV, "blog", "q", client=Net([1, 2]).client())
