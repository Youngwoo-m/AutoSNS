// 축압식 ABC 분말 소화기 — anatomy 키트로 만든 아이소메트릭 인터랙티브 그림.
//   node build.mjs           → fire-extinguisher.html (다크)
//   node build.mjs --light   → fire-extinguisher-light.html
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";

const KIT = join(homedir(), ".claude/skills/anatomy");
const k = await import(join(KIT, "kit/iso-kit.mjs"));
const G = await import(join(KIT, "kit/lathe.mjs"));
const { tubePieces, tubeSvg } = await import(join(KIT, "kit/tube.mjs"));
const { kitScript } = await import(join(KIT, "scripts/inline-kit.mjs"));

const HERE = dirname(fileURLToPath(import.meta.url));
const theme = process.argv.includes("--light") ? "light" : "dark";

// ── 진짜 수치(모델) ──────────────────────────────────────────────
// 지시압력계 사용 가능 범위 0.7~0.98 MPa(녹색). 눈금 0~1.5 MPa, 270° 범위.
const GAUGE_MAX = 1.5;
const GREEN = [0.7, 0.98];
const P_FULL = 0.86; // 충전 상태(녹색 안)
const DEG = Math.PI / 180;

// ── 월드(1 단위 ≈ 2 mm) ─────────────────────────────────────────
const WIDTH = 600;
const HEIGHT = 470;
const R = 30; // 몸통 반지름(지름 약 120 mm)
const Z0 = 4; // 몸통 바닥(받침 컵 안)
const SHOULDER = 200; // 몸통 원통부 끝(s)
const NECK = 238; // 목 끝 높이(z)
const VALVE_TOP = 280;
const A_VIEW = 45 * DEG; // 보는 사람 쪽
const A_RIGHT = -45 * DEG; // 화면 오른쪽(호스 쪽)
const dirOf = (a) => [Math.cos(a), Math.sin(a), 0];
const DV = dirOf(A_VIEW);
const DR = dirOf(A_RIGHT);
const at3 = (d, r, z) => [d[0] * r, d[1] * r, z];

const PLATE = { x: -62, y: -62, w: 124, d: 124, r: 10 };
const PLATE_H = 8;
const FOOT_H = 5;
const CUP_H = 30;

const WIN = { a0: -8 * DEG, a1: 98 * DEG, z0: 46, z1: 186 }; // 절개창
const H_FULL = 158; // 분말 높이(가득)
const H_EMPTY = Z0 + 9;

const GAUGE_Z = 258;
const GAUGE_S0 = 12; // 밸브 축에서 압력계 뒷면까지
const GAUGE_T = 5;
const GAUGE_R = 12;
const GC = at3(DV, GAUGE_S0 + GAUGE_T, GAUGE_Z); // 압력계 앞면 중심
const UP = [0, 0, 1];
const SIDE = [DR[0], DR[1], 0]; // 압력계 면의 오른쪽

const P = k.fitProjection(
  [...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0), [0, 0, VALVE_TOP + 12], [-66, 0, 286], at3(DR, 52, 250), at3(DR, 46, 70)],
  WIDTH,
  HEIGHT,
  { pad: 34, azimuth: 45 },
);

const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (pts, style) => k.dotsSvg(pts, style);
const poly = (pts) => "M" + pts.map((p) => at(p).map((v) => v.toFixed(1)).join(" ")).join("L");
const ringPts = (r, z, a0, a1, n = 48) => Array.from({ length: n + 1 }, (_, i) => {
  const a = a0 + ((a1 - a0) * i) / n;
  return [r * Math.cos(a), r * Math.sin(a), z];
});
const VERT = G.frameOf([0, 0, 0], [0, 0, 1], [1, 0, 0], [0, 1, 0]);
const frameAt = (z) => G.frameOf([0, 0, z], [0, 0, 1], [1, 0, 0], [0, 1, 0]);

// ── 받침대 ────────────────────────────────────────────────────────
function stand() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PLATE, -PLATE_H - FOOT_H, PLATE_H, P)}"/>`];
  const byDepth = (pts) => [...pts].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));
  for (const [x, y] of byDepth(k.corners(PLATE, 16))) {
    out.push(S(k.cylinder(x, y, 7, -PLATE_H - FOOT_H, 1.6, P, 28), { tone: "lo" }));
    out.push(S(k.cylinder(x, y, 5.4, -PLATE_H - FOOT_H + 1.6, FOOT_H - 1.6, P, 28), { tone: "mid" }));
  }
  out.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 8, 1.2), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(PLATE, 5), 0, P), { tone: "lo" }));
  const screws = k.corners(PLATE, 10);
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 2.2, 0, P, 16)).join(""), { tone: "lo" }));
  out.push(D(screws.map(([x, y]) => at([x, y, 0])), { size: 0.5 }));
  // 명판: 보는 쪽 앞 모서리
  const tag = { x: 14, y: 40, w: 40, d: 14, r: 1.5 };
  out.push(S(k.slabOf(tag, 0, 0.8, P, 3), { tone: "lo", crease: "none" }));
  out.push(D([at([tag.x + 2.5, tag.y + 7, 0.8]), at([tag.x + tag.w - 2.5, tag.y + 7, 0.8])], { size: 0.4 }));
  out.push(k.faceTextSvg(k.topMatrix([tag.x + tag.w / 2, tag.y + 7], 0.8, P, "x"), "ABC 분말 3.3kg", { size: 3.2, tone: "mid", anchor: "middle" }));
  return out.join("");
}

// 받침 컵: 전체 링(뒤) → 몸통 → 앞쪽 반원 벽
const CUP_IN = R + 1.4;
const CUP_OUT = R + 5;
const cupFull = () => S(G.ringBand(0, CUP_H, CUP_IN, CUP_OUT, VERT, P), { tone: "mid" });
function cupFront() {
  const a0 = A_VIEW - Math.PI / 2;
  const a1 = A_VIEW + Math.PI / 2;
  const outer = ringPts(CUP_OUT, 0, a0, a1, 40).map(([x, y]) => [x, y]);
  const inner = ringPts(CUP_IN, 0, a1, a0, 40).map(([x, y]) => [x, y]);
  const out = [S(k.extrude([...outer, ...inner], 0, CUP_H, P, { convex: false }), { tone: "mid" })];
  out.push(L(G.arcOf(VERT, CUP_H - 6, CUP_OUT, P), { tone: "faint" }));
  return out.join("");
}

// ── 몸통 ──────────────────────────────────────────────────────────
const BODY_PROFILE = [
  [0, 25], [2.4, 29.2, 1], [5, 30], [SHOULDER, 30], [SHOULDER + 8, 29.2, 1], [SHOULDER + 16, 26.6, 1],
  [SHOULDER + 24, 21.5, 1], [SHOULDER + 29, 15.2, 1], [SHOULDER + 31, 11],
];
const BODY_F = frameAt(Z0);
function shell() {
  const seams = [
    L(G.arcOf(BODY_F, SHOULDER, R, P), { tone: "faint" }),
    L(G.arcOf(BODY_F, 32, R, P), { tone: "faint" }),
    L(G.arcOf(BODY_F, 196, R, P), { tone: "faint" }),
  ].join("");
  const out = [S(G.solidOf(BODY_PROFILE, BODY_F, P), { tone: "hi", inner: seams })];
  // 목(밸브와 잇는 나사부)
  const neckF = frameAt(Z0 + SHOULDER + 31);
  out.push(S(G.solidOf([[0, 10.5], [NECK - (Z0 + SHOULDER + 31), 10.5]], neckF, P), { tone: "mid" }));
  return out.join("");
}

// ── 절개창(내부) ──────────────────────────────────────────────────
function windowPath(r) {
  const top = ringPts(r, WIN.z1, WIN.a0, WIN.a1, 40);
  const bot = ringPts(r, WIN.z0, WIN.a1, WIN.a0, 40);
  return poly([...top, ...bot]) + "Z";
}
function interior() {
  const out = [];
  out.push(`<clipPath id="fx-win"><path d="${windowPath(R)}"/></clipPath>`);
  out.push(`<g clip-path="url(#fx-win)">`);
  out.push(`<path class="iso-shade" data-shade="3" d="${windowPath(R)}"/>`);
  // 안쪽 뒷벽의 세로 줄(원통 안쪽 면임을 보여 줌)
  const ribs = [];
  for (let a = A_VIEW + Math.PI - 70 * DEG; a <= A_VIEW + Math.PI + 70 * DEG + 1e-6; a += 14 * DEG) {
    ribs.push(poly([[(R - 1.6) * Math.cos(a), (R - 1.6) * Math.sin(a), WIN.z0 - 4], [(R - 1.6) * Math.cos(a), (R - 1.6) * Math.sin(a), WIN.z1 + 4]]));
  }
  out.push(L(ribs.join(""), { tone: "faint" }));
  out.push(`<g data-part="gas"></g>`);
  out.push(`<path data-part="powder-band" class="iso-shade" data-shade="1" d=""/>`);
  out.push(`<path data-part="powder-top" class="iso-top" d=""/>`);
  out.push(`<path data-part="powder-rim" class="iso-line" data-tone="mid" d=""/>`);
  out.push(`<g data-part="grain"></g>`);
  // 사이펀관
  out.push(S(k.cylinder(0, 0, 3, Z0 + 7, NECK - Z0 - 7, P, 24), { tone: "hi", crease: "lo" }));
  out.push(L(k.ring(0, 0, 1.8, Z0 + 7, P, 16), { tone: "lo" }));
  out.push(`<path data-part="flow-tube" class="iso-line" data-tone="hi" data-flow="" style="opacity:0;stroke-width:1.2;stroke-dasharray:2.2 3.2" d="${poly([[0, 0, Z0 + 8], [0, 0, WIN.z1 + 6]])}"/>`);
  out.push(`</g>`);
  // 절단면 테두리: 바깥(R)과 안쪽(R − 두께)
  out.push(L(windowPath(R - 1.6), { tone: "faint" }));
  out.push(L(windowPath(R), { tone: "hi" }));
  return out.join("");
}

// ── 밸브 머리 ─────────────────────────────────────────────────────
const VALVE_F = frameAt(NECK);
const VALVE_PROFILE = [[0, 12.5], [3, 12.5], [3, 13.6], [16, 13.6], [18, 12.4, 1], [30, 11.6, 1], [33, 9.4], [VALVE_TOP - NECK, 9.4]];
function handle() {
  // 운반 손잡이(고정) — 밸브 왼쪽 뒤로 뻗음
  const plan = { x: -64, y: -6, w: 54, d: 12, r: 3 };
  const out = [S(k.slabOf(plan, 262, 4, P, 4, 0.5), { tone: "mid" })];
  for (const x of [-56, -44, -32]) out.push(L(k.lineOnTop([x, -6], [x, 6], 266, P), { tone: "faint" }));
  return out.join("");
}
function valve() {
  const seams = L(G.arcOf(VALVE_F, 3, 13.6, P), { tone: "faint" });
  const out = [S(G.solidOf(VALVE_PROFILE, VALVE_F, P), { tone: "mid", inner: seams })];
  // 밸브 축(레버가 누르는 막대)
  out.push(S(k.cylinder(0, 0, 3.2, VALVE_TOP, 4, P, 20), { tone: "mid" }));
  // 호스 출구 보스(화면 오른쪽)
  const boss = G.frameAlong([0, 0, 252], DR);
  out.push(S(G.disc(9, 18, 5.2, boss, P), { tone: "mid" }));
  out.push(S(G.disc(18, 21, 6.4, boss, P), { tone: "mid" }));
  // 압력계 보스
  const gb = G.frameAlong([0, 0, GAUGE_Z], DV);
  out.push(S(G.disc(9, GAUGE_S0, 4.2, gb, P), { tone: "mid" }));
  return out.join("");
}
const PIN = { x: -18, y0: -12, y1: 11, z: 274, r: 1.6 };
function pin() {
  const f = G.frameOf([PIN.x, 0, PIN.z], [0, 1, 0], [1, 0, 0], [0, 0, 1]);
  const out = [S(G.disc(PIN.y0, PIN.y1, PIN.r, f, P), { tone: "hi", crease: "lo" })];
  // 고리
  const loop = [];
  for (let i = 0; i <= 40; i++) {
    const t = (i / 40) * Math.PI * 2;
    loop.push([PIN.x, PIN.y1 + 6.5 - 6.5 * Math.cos(t), PIN.z - 6.5 * Math.sin(t)]);
  }
  for (const piece of tubePieces(loop, 0.9, P, { closed: true, maxLength: 400 })) out.push(tubeSvg(piece, { tone: "hi" }));
  return out.join("");
}
// 지지 갈퀴(핀이 지나가는 두 귀) — 밸브 머리에서 뒤쪽으로
function fork() {
  const out = [];
  for (const y of [-10.6, 7.6]) {
    out.push(S(k.slabOf({ x: -22, y, w: 12, d: 3, r: 0.8 }, 264, 16, P, 2, 0.3), { tone: "mid" }));
  }
  return out.join("");
}
function lever() {
  const plan = { x: -62, y: -5.5, w: 72, d: 11, r: 3 };
  const out = [S(k.slabOf(plan, 284, 4, P, 4, 0.5), { tone: "mid" })];
  for (const x of [-54, -42, -30]) out.push(L(k.lineOnTop([x, -5.5], [x, 5.5], 288, P), { tone: "faint" }));
  // 축 누름 패드
  out.push(S(k.cylinder(0, 0, 4.2, 282, 2, P, 20), { tone: "mid" }));
  out.push(D([at([4, 0, 288]), at([-56, 0, 288])], { size: 0.45 }));
  return out.join("");
}

// ── 압력계 ────────────────────────────────────────────────────────
const onFace = (rad, theta, lift = 0) => [
  GC[0] + rad * (Math.sin(theta) * SIDE[0] + Math.cos(theta) * UP[0]) + lift * DV[0],
  GC[1] + rad * (Math.sin(theta) * SIDE[1] + Math.cos(theta) * UP[1]) + lift * DV[1],
  GC[2] + rad * (Math.sin(theta) * SIDE[2] + Math.cos(theta) * UP[2]),
];
const thetaOf = (v) => (-135 + (270 * v) / GAUGE_MAX) * DEG;
function gauge() {
  const gf = G.frameAlong([0, 0, GAUGE_Z], DV);
  const out = [S(G.disc(GAUGE_S0, GAUGE_S0 + GAUGE_T, GAUGE_R, gf, P), { tone: "mid" })];
  out.push(S(G.ringBand(GAUGE_S0 + GAUGE_T, GAUGE_S0 + GAUGE_T + 0.8, GAUGE_R - 1.4, GAUGE_R, gf, P), { tone: "mid" }));
  const arc = (r, v0, v1, n = 40) => poly(Array.from({ length: n + 1 }, (_, i) => onFace(r, thetaOf(v0 + ((v1 - v0) * i) / n), 0.05)));
  // 구간: 부족(빨강) · 정상(녹색) · 과충전(빨강)
  out.push(`<path class="iso-line" data-tone="red" style="stroke-width:1.6" d="${arc(8.4, 0, GREEN[0])}"/>`);
  out.push(`<path class="iso-line" data-tone="green" style="stroke-width:1.6" d="${arc(8.4, GREEN[0], GREEN[1])}"/>`);
  out.push(`<path class="iso-line" data-tone="red" style="stroke-width:1.6" d="${arc(8.4, GREEN[1], GAUGE_MAX)}"/>`);
  const minor = [];
  const major = [];
  for (let i = 0; i <= 15; i++) {
    const v = i / 10;
    const long = i % 5 === 0;
    (long ? major : minor).push(poly([onFace(9.6, thetaOf(v), 0.05), onFace(long ? 7.0 : 7.8, thetaOf(v), 0.05)]));
  }
  out.push(L(minor.join(""), { tone: "lo" }), L(major.join(""), { tone: "mid" }));
  return out.join("");
}
const needleD = (v) => poly([onFace(1.6, thetaOf(v) + Math.PI, 0.1), onFace(8.0, thetaOf(v), 0.1)]);

// ── 호스와 노즐 ───────────────────────────────────────────────────
const HOSE_R = 2.8;
const NOZ_TOP = 120;
const NOZ_LEN = 44;
const HOSE_ROUTE = G.fillet([at3(DR, 21, 252), at3(DR, 36, 252), at3(DR, 42, 238), at3(DR, 42, NOZ_TOP)], 9, 9, { P, tube: HOSE_R });
function hose() {
  const out = [];
  for (const piece of tubePieces(HOSE_ROUTE, HOSE_R, P, { maxLength: 30 })) out.push(tubeSvg(piece, { tone: "hi" }));
  out.push(`<path data-part="flow-hose" class="iso-line" data-tone="hi" style="opacity:0;stroke-width:1;stroke-dasharray:2.2 3.2" d="${poly(HOSE_ROUTE)}"/>`);
  return out.join("");
}
function nozzleClip() {
  // 몸통에서 노즐까지 받침 돌기
  const f = G.frameAlong([0, 0, 96], DR);
  return S(G.disc(R - 0.4, 42 - 5.4, 2.2, f, P), { tone: "mid" });
}
function nozzle() {
  const f = G.frameAlong(at3(DR, 42, NOZ_TOP), [0, 0, -1]);
  const prof = [[0, 4.2], [7, 4.2], [7, 3.4], [NOZ_LEN - 6, 5.8, 1], [NOZ_LEN, 7.6]];
  const out = [S(G.solidOf(prof, f, P), { tone: "hi" })];
  out.push(S(G.ringBand(22, 26, 5.0, 6.2, f, P), { tone: "mid" })); // 고정 밴드
  return out.join("");
}
const NOZ_TIP = at3(DR, 42, NOZ_TOP - NOZ_LEN);

// ── 조립 ──────────────────────────────────────────────────────────
const svg = k.figureSvg({
  width: WIDTH,
  height: HEIGHT,
  label:
    "받침대에 세운 축압식 ABC 분말 소화기. 몸통 앞쪽을 잘라 안의 분말 약제, 그 위의 질소 가스, 바닥까지 내려간 사이펀관을 보여 준다. 안전핀을 뽑고 누름 손잡이를 누르면 밸브가 열려 질소 압력이 분말을 사이펀관으로 밀어 올리고, 호스와 노즐로 나간다. 그만큼 압력계 바늘과 분말 높이가 내려간다.",
  body: [
    stand(),
    cupFull(),
    shell(),
    interior(),
    cupFront(),
    nozzleClip(),
    handle(),
    fork(),
    valve(),
    `<g data-part="pin">${pin()}</g>`,
    `<g data-part="lever">${lever()}</g>`,
    gauge(),
    `<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" style="stroke-width:1.1" d="${needleD(P_FULL)}"/>`,
    D([at(onFace(0, 0, 0.12))], { size: 0.9, tone: "hi" }),
    hose(),
    nozzle(),
    `<g data-part="puff" style="opacity:0"></g>`,
  ],
});

const live = `
const P = ${JSON.stringify(P)};
const R = ${R}, Z0 = ${Z0}, H_FULL = ${H_FULL}, H_EMPTY = ${H_EMPTY}, P_FULL = ${P_FULL};
const GREEN = ${JSON.stringify(GREEN)}, GAUGE_MAX = ${GAUGE_MAX};
const A_VIEW = ${A_VIEW}, DEG = Math.PI / 180;
const GC = ${JSON.stringify(GC)}, UP = [0, 0, 1], SIDE = ${JSON.stringify(SIDE)}, DV = ${JSON.stringify(DV)};
const NOZ_TIP = ${JSON.stringify(NOZ_TIP)};
const WIN = ${JSON.stringify(WIN)};
const svg = document.querySelector(".iso-stage svg");
const stage = document.querySelector(".iso-stage");
const $ = (n) => svg.querySelector('[data-part="' + n + '"]');
const needle = $("needle"), pin = $("pin"), lever = $("lever");
const band = $("powder-band"), top = $("powder-top"), rim = $("powder-rim"), grain = $("grain"), gas = $("gas");
const flowTube = $("flow-tube"), flowHose = $("flow-hose"), puff = $("puff");
const readout = document.querySelector("[data-readout]");
const still = matchMedia("(prefers-reduced-motion: reduce)");
const at = (p) => iso(p, P);
const poly = (pts) => "M" + pts.map((p) => at(p).map((v) => v.toFixed(1)).join(" ")).join("L");
const ringPts = (r, z, a0, a1, n) => Array.from({ length: n + 1 }, (_, i) => { const a = a0 + (a1 - a0) * i / n; return [r * Math.cos(a), r * Math.sin(a), z]; });
const onFace = ${onFace.toString()};
const thetaOf = ${thetaOf.toString()};
const needleD = ${needleD.toString()};
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const ease = (t) => t * t * (3 - 2 * t);
// 질소 점(한 번만)
(function () {
  let s = "";
  for (let i = 0; i < 30; i++) {
    const a = A_VIEW + Math.PI + (((i * 47) % 140) - 70) * DEG, rr = 4 + ((i * 13) % 22), z = WIN.z0 + ((i * 29) % 140);
    const q = at([rr * Math.cos(a), rr * Math.sin(a), z]);
    s += '<circle cx="' + q[0].toFixed(1) + '" cy="' + q[1].toFixed(1) + '" r="0.45" data-z="' + z + '"/>';
  }
  gas.setAttribute("class", "iso-dots"); gas.setAttribute("data-tone", "lo"); gas.innerHTML = s;
})();
const gasDots = [...gas.querySelectorAll("circle")];
function drawPowder(h) {
  const r = R - 1.6, a0 = A_VIEW - Math.PI / 2, a1 = A_VIEW + Math.PI / 2;
  const front = ringPts(r, h, a0, a1, 40), floor = ringPts(r, Z0 + 2, a1, a0, 40);
  band.setAttribute("d", poly([...front, ...floor]) + "Z");
  const full = ringPts(r, h, 0, Math.PI * 2, 72);
  top.setAttribute("d", poly(full) + "Z");
  rim.setAttribute("d", poly(front));
  let g = "";
  for (let i = 0; i < 46; i++) {
    const a = A_VIEW + (((i * 53) % 150) - 75) * DEG, z = Z0 + 6 + ((i * 31) % 160);
    if (z > h - 3) continue;
    const q = at([r * Math.cos(a), r * Math.sin(a), z]);
    g += '<circle cx="' + q[0].toFixed(1) + '" cy="' + q[1].toFixed(1) + '" r="0.4"/>';
  }
  grain.setAttribute("class", "iso-dots"); grain.setAttribute("data-tone", "lo"); grain.innerHTML = g;
  for (const c of gasDots) c.style.opacity = +c.dataset.z > h + 3 ? "1" : "0";
}
function drawPuff(amount, t) {
  if (amount <= 0.01) { puff.style.opacity = "0"; return; }
  let s = "";
  for (let i = 0; i < 24; i++) {
    const ph = ((t * 1.6 + i / 24) % 1), ang = (i * 137.5) * DEG;
    const spread = 2 + ph * 22, z = NOZ_TIP[2] - 2 - ph * 46;
    const q = at([NOZ_TIP[0] + Math.cos(ang) * spread, NOZ_TIP[1] + Math.sin(ang) * spread, Math.max(2, z)]);
    s += '<circle cx="' + q[0].toFixed(1) + '" cy="' + q[1].toFixed(1) + '" r="' + (0.5 + ph * 1.4).toFixed(2) + '" style="opacity:' + (1 - ph).toFixed(2) + '"/>';
  }
  puff.innerHTML = '<g class="iso-dots" data-tone="hi">' + s + "</g>";
  puff.style.opacity = String(amount);
}
// 단계: 대기 → 핀 뽑기 → 누르기 → 방사(압력·분말 감소) → 놓기 → 빈 상태 → 재충전
const T = { rest: 1.6, pin: 1.1, press: 0.7, spray: 6.0, release: 0.6, empty: 1.8, refill: 1.6 };
const CYCLE = Object.values(T).reduce((a, b) => a + b, 0);
const TAU = 1.9;
function stateAt(t) {
  let u = t % CYCLE;
  const out = { pin: 0, press: 0, spray: 0, frac: 1, phase: "rest" };
  const step = (n) => { const d = T[n]; const v = Math.min(u / d, 1); u -= d; return v; };
  const r = step("rest"); if (u < 0) return out;
  out.pin = ease(step("pin")); out.phase = "pin"; if (u < 0) return out;
  out.press = ease(step("press")); out.phase = "press"; if (u < 0) return out;
  const s = step("spray"); out.phase = "spray"; out.spray = Math.min(1, s * 8); out.frac = Math.exp(-s * T.spray / TAU); if (u < 0) return out;
  out.frac = Math.exp(-T.spray / TAU); const rel = ease(step("release")); out.press = 1 - rel; out.spray = 1 - rel; out.phase = "release"; if (u < 0) return out;
  out.press = 0; out.spray = 0; step("empty"); out.phase = "empty"; if (u < 0) return out;
  const f = ease(step("refill")); out.phase = "refill"; out.frac = Math.exp(-T.spray / TAU) + (1 - Math.exp(-T.spray / TAU)) * f; out.pin = 1 - f;
  return out;
}
let clock = 0, last = 0, frame = 0, visible = false, manual = null;
function render(s, tSec) {
  const pressure = P_FULL * s.frac;
  const h = H_EMPTY + (H_FULL - H_EMPTY) * s.frac;
  needle.setAttribute("d", needleD(pressure));
  pin.setAttribute("transform", translateAlong(P, [0, 26 * s.pin, 0]));
  lever.setAttribute("transform", translateAlong(P, [0, 0, -5 * s.press]));
  drawPowder(h);
  flowTube.style.opacity = flowHose.style.opacity = String(s.spray);
  flowTube.style.strokeDashoffset = flowHose.style.strokeDashoffset = String(-tSec * 18);
  drawPuff(s.spray, tSec);
  const ok = pressure >= GREEN[0] && pressure <= GREEN[1];
  const word = s.phase === "spray" ? "방사 중" : s.phase === "pin" ? "안전핀 뽑는 중" : s.phase === "press" ? "손잡이 누름" : ok ? "사용 가능" : "압력 부족 · 재충전 필요";
  const text = "압력 " + pressure.toFixed(2) + " MPa · " + word;
  if (readout.textContent !== text) readout.textContent = text;
  stage.setAttribute("aria-valuetext", text);
}
function tick(now) {
  const dt = last ? Math.min((now - last) / 1000, 1 / 20) : 1 / 60; last = now;
  clock += dt;
  render(stateAt(clock), clock);
  frame = visible ? requestAnimationFrame(tick) : 0;
}
const run = () => { if (!frame && visible && !still.matches) { last = 0; frame = requestAnimationFrame(tick); } };
new IntersectionObserver((e) => { visible = e[e.length - 1].isIntersecting; if (visible) run(); }, { rootMargin: "120px 0px" }).observe(stage);
const jump = () => { const s = T.rest + T.pin + T.press; clock = (clock % CYCLE) < s ? s - 0.01 : 0; if (still.matches) render(stateAt(clock), clock); };
stage.addEventListener("click", jump);
stage.addEventListener("keydown", (ev) => { if (ev.key === " " || ev.key === "Enter") { ev.preventDefault(); jump(); } });
render(stateAt(0), 0);
`;

const FONT_CSS = `<style>
@font-face{font-family:"Pretendard";font-weight:100 900;font-display:block;src:url("Pretendard-Bold.otf") format("opentype")}
body,.iso,.iso-plate{--anatomy-mono:"Pretendard",ui-sans-serif,sans-serif;font-family:"Pretendard",ui-sans-serif,sans-serif}
.iso-face-text{font-family:"Pretendard",sans-serif}
.iso-plate [data-readout]{font-size:1.06em}
</style>`;

const body = FONT_CSS + k.plateHtml({
  fig: "그림 1",
  title: "축압식 분말 소화기",
  hint: "누르면 바로 방사 · 두면 순서대로 작동",
  readout: `압력 ${P_FULL.toFixed(2)} MPa · 사용 가능`,
  keys: [
    { mark: "lit", label: "압력계 바늘 — 녹색(0.7~0.98 MPa) 안이면 사용 가능" },
    { mark: "green", label: "녹색 구간: 정상 압력 · 빨간 구간: 부족 또는 과충전" },
    { mark: "raised", label: "분말 약제와 사이펀관 — 위쪽은 압력을 만드는 질소 가스" },
    { mark: "dashed", label: "방사 중 분말 흐름: 사이펀관 → 밸브 → 호스 → 노즐" },
  ],
  caption:
    "질소가 미리 채워져 있어 늘 압력이 걸린 '축압식'이다. 안전핀을 뽑고 손잡이를 누르면 밸브가 열리고, 질소가 분말을 바닥까지 내려간 사이펀관으로 밀어 올려 노즐로 내보낸다. 분말이 나간 만큼 압력도 빠진다. 바늘이 녹색 밖이면 쓸 수 없으니 미리 점검한다. 그림은 방사 시간을 줄여 보여 준다(3.3kg은 실제로 약 10~15초).",
  body: `<div class="iso-stage" tabindex="0" role="img" aria-label="축압식 분말 소화기: 클릭하거나 스페이스를 누르면 방사 장면으로 넘어갑니다" aria-valuetext="">${svg}</div>`,
});

const name = theme === "light" ? "fire-extinguisher-light.html" : "fire-extinguisher.html";
writeFileSync(join(HERE, name), k.pageHtml({ title: "축압식 분말 소화기", theme, body, script: kitScript() + live }));
console.log("wrote", name);
