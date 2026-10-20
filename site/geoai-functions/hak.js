// 세명대 학생회관 학생식당 식단 중계 — 룰렛 앱(geoai-na.netlify.app/dinner)용 Netlify 함수
// (/.netlify/functions/hak?date=YYYY-MM-DD, 날짜를 빼면 오늘 한국 시각).
// 포털 대시보드 위젯이 쓰는 주소는 로그인 없이 JSON 을 주지만 CORS 가 없어 여기서 대신 부른다.
// 포털 내부용 주소라 바뀌거나 막힐 수 있다 — 실패하면 앱은 학식 칸만 숨긴다. 결과는 30분 캐시.
const API = "https://portal.semyung.ac.kr/portlet/restaurant/menu";
const RES = "GH006"; // 학생회관_학생식당
const ORIGINS = ["https://geoai-na.netlify.app", "https://smuds-m.github.io"];

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

const today = () => new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10); // 한국 시각
// "백미밥<br>물만두떡국<br>" → ["백미밥","물만두떡국"]; '*'로 시작하는 줄은 안내문으로 따로 모은다
const split = (html) => String(html || "").split(/<br\s*\/?>/i)
  .map((s) => s.replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").trim()).filter(Boolean);

exports.handler = async (event) => {
  const origin = ORIGINS.includes(event.headers?.origin) ? event.headers.origin : undefined;
  const date = event.queryStringParameters?.date || today();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return reply(400, { ok: false, error: "date" }, origin);
  try {
    const r = await fetch(`${API}?resCd=${RES}&resDt=${date}`, { headers: { "User-Agent": "Mozilla/5.0" } });
    if (!r.ok) return reply(502, { ok: false, error: "upstream " + r.status }, origin);
    const it = (await r.json())?.[0];
    if (!it) return reply(200, { ok: true, date, open: false }, origin); // 주말·휴무
    const notes = [], meal = (k) => split(it[k]).filter((s) => (s.startsWith("*") ? (notes.push(s.replace(/^\*\s*/, "")), false) : true));
    const body = { ok: true, date, open: true, morning: meal("morningMenu"), lunch: meal("lunchMenu"), dinner: meal("dinnerMenu") };
    return reply(200, { ...body, notes: [...new Set(notes)] }, origin);
  } catch (e) {
    return reply(502, { ok: false, error: "upstream" }, origin);
  }
};
