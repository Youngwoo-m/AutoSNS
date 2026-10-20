// 제천 시내버스 실시간 도착 중계 — 세명대 통학 길잡이용 Netlify 함수(/.netlify/functions/busarr?nodes=JCB...,JCB...).
// 공공데이터포털 TAGO 버스도착정보는 브라우저에서 직접 부를 수 없고(CORS 없음) 키를 숨겨야 해서 여기서 대신 부른다.
// 키는 Netlify 환경변수 DATA_GO_KR_KEY(디코딩 키, 개발계정 하루 10,000건). 결과는 30초 캐시.
const API = "https://apis.data.go.kr/1613000/ArvlInfoInqireService/getSttnAcctoArvlPrearngeInfoList";
const CITY = 33030;   // 제천시
const ORIGINS = ["https://smuds-m.github.io", "http://localhost:8743", "https://geoai-na.netlify.app"];

const reply = (status, body, origin) => ({
  statusCode: status,
  headers: {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": origin || ORIGINS[0],
    "Vary": "Origin",
    "Cache-Control": status === 200 ? "public, max-age=30" : "no-store",
    ...(status === 200 ? { "Netlify-CDN-Cache-Control": "public, s-maxage=30" } : {}),
  },
  body: JSON.stringify(body),
});

const list = (j) => {
  const it = j?.response?.body?.items?.item;
  return !it ? [] : Array.isArray(it) ? it : [it];
};

exports.handler = async (event) => {
  const origin = ORIGINS.find((o) => o === event.headers?.origin);
  const key = process.env.DATA_GO_KR_KEY;
  if (!key) return reply(500, { ok: false, error: "no key" }, origin);
  const nodes = String(event.queryStringParameters?.nodes || "").split(",").filter((n) => /^[A-Z]{3}\d{9}$/.test(n)).slice(0, 3);
  if (!nodes.length) return reply(400, { ok: false, error: "nodes" }, origin);
  try {
    const all = await Promise.all(nodes.map(async (node) => {
      const url = `${API}?${new URLSearchParams({ serviceKey: key, cityCode: CITY, nodeId: node, _type: "json", numOfRows: 40 })}`;
      const j = await (await fetch(url)).json();
      return list(j).map((x) => ({
        node, stop: x.nodenm, no: String(x.routeno), min: Math.max(0, Math.round((+x.arrtime || 0) / 60)),
        prev: +x.arrprevstationcnt || 0, low: /저상/.test(x.vehicletp || ""),
      }));
    }));
    const buses = all.flat().sort((a, b) => a.min - b.min);
    return reply(200, { ok: true, at: new Date().toISOString(), buses }, origin);
  } catch (e) {
    return reply(502, { ok: false, error: "upstream" }, origin);
  }
};
