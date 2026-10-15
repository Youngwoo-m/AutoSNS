// 카카오맵 대중교통 경로 조회 중계 — 세명대 통학 길잡이(smuds-m.github.io/semyung-shuttle)용 Netlify 함수
// (/.netlify/functions/kroute?sx=&sy=&ex=&ey=). 카카오 REST 키는 브라우저에 두면 안 돼서 여기서 대신 부른다.
// 키는 Netlify 환경변수 KAKAO_REST_KEY(지오서비스 앱 — 계정의 카카오맵 무료 쿼터 앱, 하루 1,000건).
// 카카오 API 는 시내 구간만 찾고(시외·기차 X) 출발 시각 없이 소요시간만 준다. 결과는 30분 캐시.
const API = "https://dapi.kakao.com/v2/routing/publictraffic";
const ORIGINS = ["https://smuds-m.github.io", "http://localhost:8743", "https://geoai-na.netlify.app"];

const reply = (status, body, origin) => ({
  statusCode: status,
  headers: {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": origin || ORIGINS[0],
    "Vary": "Origin",
    "Cache-Control": status === 200 ? "public, max-age=1800" : "no-store",
    ...(status === 200 ? { "Netlify-CDN-Cache-Control": "public, s-maxage=1800, durable" } : {}),
  },
  body: JSON.stringify(body),
});

// 좌표는 소수 4자리(약 10m)로 맞춰 캐시가 잘 맞게 한다
const coord = (v, lo, hi) => {
  const n = Math.round(Number(v) * 1e4) / 1e4;
  return Number.isFinite(n) && n >= lo && n <= hi ? n : null;
};

// 앱이 쓰는 만큼만 줄인 경로: 분·원·미터 단위
function slim(r) {
  const p = r.properties || {};
  return {
    min: Math.round((p.totalTime || 0) / 60), fare: p.fare?.value || 0, transfers: p.transfers || 0,
    steps: (r.steps || []).map((s) => {
      const q = s.properties || {};
      const stops = q.stops || [];
      return {
        type: q.type, min: Math.round((q.time || 0) / 60), m: q.distance || 0,
        from: stops[0]?.name || "", to: stops[stops.length - 1]?.name || "", n: Math.max(stops.length - 1, 0),
        names: [...new Set((q.vehicles || []).map((v) => v.name).filter(Boolean))].slice(0, 4),
      };
    }),
  };
}

exports.handler = async (event) => {
  const origin = ORIGINS.find((o) => o === event.headers?.origin);
  if (event.httpMethod === "OPTIONS") return { statusCode: 204, headers: { "Access-Control-Allow-Origin": origin || ORIGINS[0], "Access-Control-Allow-Methods": "GET" } };
  const key = process.env.KAKAO_REST_KEY;
  if (!key) return reply(500, { status: "ERROR", error: "no key" }, origin);
  const q = event.queryStringParameters || {};
  const sx = coord(q.sx, 124, 132), sy = coord(q.sy, 33, 39), ex = coord(q.ex, 124, 132), ey = coord(q.ey, 33, 39);
  if ([sx, sy, ex, ey].includes(null)) return reply(400, { status: "INVALID_REQUEST" }, origin);
  const url = `${API}?${new URLSearchParams({ start_x: sx, start_y: sy, end_x: ex, end_y: ey })}`;
  try {
    const res = await fetch(url, { headers: { Authorization: `KakaoAK ${key}` } });
    if (res.status === 429) return reply(429, { status: "QUOTA" }, origin);
    const j = await res.json();
    if (!res.ok) return reply(502, { status: "UPSTREAM", code: res.status, msg: j?.msg || "" }, origin);
    return reply(200, { status: j.status, routes: (j.routes || []).slice(0, 3).map(slim) }, origin);
  } catch (e) {
    return reply(502, { status: "UPSTREAM" }, origin);
  }
};
