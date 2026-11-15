// 개인 홈페이지(geoai-na.web.app) 서버 기능: 옛 Netlify 함수 5개 + 문제 접수 양식.
const { onRequest } = require("firebase-functions/v2/https");
const { defineSecret } = require("firebase-functions/params");
const admin = require("firebase-admin");
admin.initializeApp();

const DATA_GO_KR_KEY = defineSecret("DATA_GO_KR_KEY");
const KAKAO_REST_KEY = defineSecret("KAKAO_REST_KEY");
const COLLECTOR_KEY = defineSecret("COLLECTOR_KEY");
const OPTS = { region: "asia-northeast3", memory: "256MiB", timeoutSeconds: 30, maxInstances: 5 };

// Netlify 함수(exports.handler) 를 그대로 감싼다. 키는 환경변수 이름 그대로 process.env 로 들어온다.
const adapt = (file, secrets) => onRequest({ ...OPTS, secrets }, async (req, res) => {
  const out = await require(file).handler({ headers: req.headers, queryStringParameters: req.query, httpMethod: req.method });
  for (const [k, v] of Object.entries(out.headers || {})) if (!/^netlify-/i.test(k)) res.set(k, v);
  res.status(out.statusCode || 200).send(out.body || "");
});
exports.hak = adapt("./legacy/hak.js", []);
exports.wthr = adapt("./legacy/wthr.js", [DATA_GO_KR_KEY]);
exports.alerts = adapt("./legacy/alerts.js", [DATA_GO_KR_KEY]);
exports.busarr = adapt("./legacy/busarr.js", [DATA_GO_KR_KEY]);
exports.kroute = adapt("./legacy/kroute.js", [KAKAO_REST_KEY]);

const FORMS = new Set(["engineer-questions", "civil-engineer-questions", "building-engineer-questions", "safety-engineer-questions"]);
const clip = (v, n) => String(v ?? "").trim().slice(0, n);

// 접수 알림: 카카오톡 '나에게 보내기'. 리프레시 토큰은 시크릿 KAKAO_REFRESH_TOKEN 이 처음 값이고,
// 카카오가 새 토큰을 주면 Firestore _config/kakao 에 저장해 다음부터 그 값을 쓴다(2달 만료 대비).
const KAKAO_REFRESH_TOKEN = defineSecret("KAKAO_REFRESH_TOKEN");
const KAKAO_CLIENT_SECRET = defineSecret("KAKAO_CLIENT_SECRET"); // 앱의 REST API 키에 붙은 클라이언트 시크릿
// 알림용 카카오 앱('지오서비스')의 REST 키. 길찾기(kroute)의 KAKAO_REST_KEY 와 다른 앱일 수 있어 따로 둔다.
const KAKAO_MSG_REST_KEY = defineSecret("KAKAO_MSG_REST_KEY");
const EXAM = {
  "engineer-questions": ["측량및지형공간정보기술사", "questions"],
  "civil-engineer-questions": ["토목시공기술사", "civil-questions"],
  "building-engineer-questions": ["건축시공기술사", "building-questions"],
  "safety-engineer-questions": ["건설안전기술사", "safety-questions"],
};
const withTimeout = (p, ms) => Promise.race([p, new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), ms))]);

async function kakaoAccessToken() {
  const ref = admin.firestore().doc("_config/kakao");
  const saved = (await ref.get()).get("refresh_token");
  const r = await fetch("https://kauth.kakao.com/oauth/token", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded;charset=utf-8" },
    body: new URLSearchParams({
      grant_type: "refresh_token", client_id: KAKAO_MSG_REST_KEY.value().trim(), client_secret: KAKAO_CLIENT_SECRET.value().trim(),
      refresh_token: saved || KAKAO_REFRESH_TOKEN.value().trim(),
    }),
  });
  const j = await r.json();
  if (!r.ok || !j.access_token) throw new Error(`kakao token ${r.status} ${j.error_code || j.error || ""}`);
  if (j.refresh_token) await ref.set({ refresh_token: j.refresh_token, updated_at: new Date().toISOString() });
  return j.access_token;
}

async function notifyKakao({ form, title, topic, nickname }) {
  const [exam, path] = EXAM[form];
  const text = [`[문제 접수] ${exam}`, `분야: ${topic || "선택 안 함"}`, `닉네임: ${nickname || "없음"}`, `제목: ${title}`].join("\n").slice(0, 200);
  const url = `https://geoai-na.web.app/${path}/`;
  const r = await fetch("https://kapi.kakao.com/v2/api/talk/memo/default/send", {
    method: "POST",
    headers: { Authorization: `Bearer ${await kakaoAccessToken()}`, "Content-Type": "application/x-www-form-urlencoded;charset=utf-8" },
    body: new URLSearchParams({ template_object: JSON.stringify({ object_type: "text", text, link: { web_url: url, mobile_web_url: url }, button_title: "페이지 열기" }) }),
  });
  if (!r.ok) throw new Error(`kakao send ${r.status} ${await r.text()}`);
}

// 문제 접수: 허니팟·동의·길이를 확인하고 Firestore 에 쌓는다. 수집기가 collect 로 가져간다.
// 저장한 뒤 카톡으로 알린다. 알림이 실패해도 접수는 성공으로 돌려준다.
exports.submit = onRequest({ ...OPTS, secrets: [KAKAO_MSG_REST_KEY, KAKAO_REFRESH_TOKEN, KAKAO_CLIENT_SECRET] }, async (req, res) => {
  if (req.method !== "POST") return res.status(405).send("POST only");
  const b = req.body || {};
  if (b["bot-field"]) return res.status(200).send("ok"); // 봇은 성공처럼 보이게 버린다
  const form = clip(b["form-name"], 60);
  const title = clip(b.title, 120), question = clip(b.question, 5000);
  if (!FORMS.has(form) || !title || question.length < 10 || b.consent !== "동의") return res.status(400).send("invalid");
  const topic = clip(b.topic, 80), nickname = clip(b.nickname, 40);
  await admin.firestore().collection("submissions").add({
    form, title, question, topic, reference: clip(b.reference, 500), nickname,
    consent: "동의", created_at: new Date().toISOString(),
  });
  try { await withTimeout(notifyKakao({ form, title, topic, nickname }), 8000); }
  catch (e) { console.error("카톡 알림 실패:", e.message); }
  res.status(200).send("ok");
});

// 수집기용: 헤더 x-collector-key 가 맞을 때만 ?form= 의 접수분을 돌려준다.
exports.collect = onRequest({ ...OPTS, secrets: [COLLECTOR_KEY] }, async (req, res) => {
  if (req.get("x-collector-key") !== COLLECTOR_KEY.value()) return res.status(401).send("unauthorized");
  const form = clip(req.query.form, 60);
  if (!FORMS.has(form)) return res.status(400).send("form");
  const snap = await admin.firestore().collection("submissions").where("form", "==", form).limit(1000).get();
  res.json(snap.docs.sort((a, b) => a.get("created_at").localeCompare(b.get("created_at"))).map((d) => ({ id: d.id, created_at: d.get("created_at"), data: { ...d.data(), "bot-field": "" } })));
});
