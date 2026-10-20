// 기상특보 현황 중계 — 룰렛 앱(geoai-na.netlify.app/dinner)용 Netlify 함수(/.netlify/functions/wthr).
// 공공데이터포털 API 는 브라우저에서 직접 부를 수 없고(CORS 없음) 키를 숨겨야 해서 여기서 대신 부른다.
// 키는 Netlify 환경변수 DATA_GO_KR_KEY(디코딩 키). 결과는 10분 캐시.
const API = "https://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnStatus";

// "o 폭염경보 : 충청북도(청주, 제천)\r\n" → 줄 단위, '없음'은 빈 목록
const lines = (t) => String(t || "").split(/\r?\n/).map((s) => s.trim())
  .filter((s) => s.startsWith("o ") && !/^o\s*없\s*음/.test(s));

const reply = (status, body) => ({
  statusCode: status,
  headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "public, max-age=600" },
  body: JSON.stringify(body),
});

exports.handler = async () => {
  const key = process.env.DATA_GO_KR_KEY;
  if (!key) return reply(500, { ok: false, error: "no key" });
  const url = `${API}?${new URLSearchParams({ serviceKey: key, pageNo: 1, numOfRows: 10, dataType: "JSON" })}`;
  try {
    const j = await (await fetch(url)).json();
    const it = j?.response?.body?.items?.item?.[0] || {};
    return reply(200, { ok: j?.response?.header?.resultCode === "00", tmFc: String(it.tmFc || ""),
      now: lines(it.t6), pre: lines(it.t7) });
  } catch (e) {
    return reply(502, { ok: false, error: "upstream" });
  }
};
