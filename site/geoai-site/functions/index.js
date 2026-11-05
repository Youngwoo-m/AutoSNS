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

// 문제 접수: 허니팟·동의·길이를 확인하고 Firestore 에 쌓는다. 수집기가 collect 로 가져간다.
exports.submit = onRequest({ ...OPTS }, async (req, res) => {
  if (req.method !== "POST") return res.status(405).send("POST only");
  const b = req.body || {};
  if (b["bot-field"]) return res.status(200).send("ok"); // 봇은 성공처럼 보이게 버린다
  const form = clip(b["form-name"], 60);
  const title = clip(b.title, 120), question = clip(b.question, 5000);
  if (!FORMS.has(form) || !title || question.length < 10 || b.consent !== "동의") return res.status(400).send("invalid");
  await admin.firestore().collection("submissions").add({
    form, title, question, topic: clip(b.topic, 80), reference: clip(b.reference, 500), nickname: clip(b.nickname, 40),
    consent: "동의", created_at: new Date().toISOString(),
  });
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
