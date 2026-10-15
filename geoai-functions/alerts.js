// 재난 소식 한 줄 띠 — 세명대 통학 길잡이 하단 흐르는 글자용 Netlify 함수(/.netlify/functions/alerts).
// 재난특보: 기상청 기상특보 현황(공공데이터포털, wthr 와 같은 API) 중 충청북도가 들어간 줄
// 재난뉴스: 구글 뉴스 RSS 에서 제천·충북 재난·사고 기사 제목(재난 낱말이 든 것만)
// 재난문자: 재난안전데이터공유플랫폼 긴급재난문자 API — 키(SAFETYDATA_KEY)가 생기면 붙인다.
// 결과는 5분 캐시.
const WRN = "https://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnStatus";
const rss = (q) => "https://news.google.com/rss/search?" + new URLSearchParams({ q, hl: "ko", gl: "KR", ceid: "KR:ko" });
// 제천·충북 소식을 먼저, 모자라면 전국 재난 소식으로 채운다
const NEWS = [
  { url: rss("제천 화재 OR 제천 사고 OR 제천 재난 OR 충북 화재 OR 충북 사고 OR 충북 재난 when:3d"), local: true },
  { url: rss("지진 OR 태풍 OR 호우경보 OR 대설경보 OR 산불 OR 대형화재 when:1d"), local: false },
];
// 지역 기사는 제목에 제천·충북이 있어야, 전국 기사는 큰 재난 낱말이 있어야 띠에 올린다
const LOCAL = /제천|충북|충청북도/;
const BIG = /지진|태풍|호우|대설|한파|폭염|산불|대형\s?화재|붕괴|폭발|특보|경보|대피/;
const DISASTER = /재난|화재|사고|호우|폭우|폭염|대설|한파|지진|산사태|태풍|강풍|침수|붕괴|폭발|감염병|대피|안전|특보|주의보|경보|훈련|산불|가뭄|미세먼지/;
const ORIGINS = ["https://smuds-m.github.io", "http://localhost:8743", "https://geoai-na.netlify.app"];

const reply = (status, body, origin) => ({
  statusCode: status,
  headers: {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": origin || ORIGINS[0],
    "Vary": "Origin",
    "Cache-Control": "public, max-age=300",
    "Netlify-CDN-Cache-Control": "public, s-maxage=300",
  },
  body: JSON.stringify(body),
});

const unxml = (s) => String(s || "").replace(/<!\[CDATA\[|\]\]>/g, "")
  .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&").trim();

async function warnings() {
  const key = process.env.DATA_GO_KR_KEY;
  if (!key) return [];
  const j = await (await fetch(`${WRN}?${new URLSearchParams({ serviceKey: key, pageNo: 1, numOfRows: 10, dataType: "JSON" })}`)).json();
  const it = j?.response?.body?.items?.item?.[0] || {};
  const lines = (t) => String(t || "").split(/\r?\n/).map((s) => s.trim()).filter((s) => s.startsWith("o ") && !/없\s*음/.test(s));
  const now = lines(it.t6).filter((s) => /충청북도|충북/.test(s)).map((s) => ({ kind: "특보", text: s.replace(/^o\s*/, "") }));
  const pre = lines(it.t7).filter((s) => /충청북도|충북/.test(s)).map((s) => ({ kind: "예비특보", text: s.replace(/^o\s*/, "") }));
  return [...now, ...pre].map((x) => ({ ...x, url: "https://www.weather.go.kr/w/special-report/overall.do" }));
}

async function news() {
  const feeds = await Promise.all(NEWS.map(async (f) => ({ ...f, xml: await (await fetch(f.url, { headers: { "User-Agent": "Mozilla/5.0" } })).text().catch(() => "") })));
  const out = [], seen = new Set();
  for (const f of feeds) {
    let n = 0;
    for (const m of f.xml.matchAll(/<item>([\s\S]*?)<\/item>/g)) {
      const title = unxml((m[1].match(/<title>([\s\S]*?)<\/title>/) || [])[1]);
      const link = unxml((m[1].match(/<link>([\s\S]*?)<\/link>/) || [])[1]);
      const head = title.replace(/\s+-\s+[^-]+$/, "");          // 끝의 " - 언론사" 떼기
      // 같은 보도자료를 받아 쓴 기사 여러 개는 하나만: 두 글자 이상 낱말이 절반 가까이 겹치면 같은 기사로 본다
      const words = new Set(head.match(/[가-힣0-9]{2,}/g) || []);
      const dup = [...seen].some((w) => [...words].filter((x) => w.has(x)).length >= Math.min(words.size, w.size) * 0.4);
      const ok = f.local ? LOCAL.test(head) && DISASTER.test(head) : BIG.test(head);
      if (!ok || dup) continue;
      seen.add(words);
      out.push({ kind: "뉴스", text: head, url: link });
      if (++n >= (f.local ? 4 : 2)) break;
    }
  }
  return out;
}

exports.handler = async (event) => {
  const origin = ORIGINS.find((o) => o === event.headers?.origin);
  const [w, n] = await Promise.all([warnings().catch(() => []), news().catch(() => [])]);
  return reply(200, { ok: true, at: new Date().toISOString(), items: [...w, ...n] }, origin);
};
