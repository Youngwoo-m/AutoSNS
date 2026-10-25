// 산사태 실험 비탈 — 10/16 산사태편 1번 장면(전조 신호) 모형 영상(anatomy 스킬, 세로 9:16, 8초).
// 나레이션: "땅이 울리고 흙탕물이 솟구치면 산사태 신호입니다. 바람이 없는데 나무가 흔들려도 위험합니다."
// 근거: 국민안전24 산사태 국민행동요령(전조 현상). 움직임: 진동계 바늘(땅 울림), 비탈 틈의 흙탕물, 깃발은 늘어진 채 흔들리는 나무.
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "/Users/youngwoo/.claude/skills/anatomy/kit/iso-kit.mjs";
import * as G from "/Users/youngwoo/.claude/skills/anatomy/kit/lathe.mjs";
import { kitScript } from "/Users/youngwoo/.claude/skills/anatomy/scripts/inline-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const theme = process.argv.includes("--dark") ? "dark" : "light";
const WIDTH = 450, HEIGHT = 800;
const BAND = { top: 160, height: 370 };          // 숏츠 위 띠·아래 자막 사이

// ---- 배치 ----
const PLATE = { x: -128, y: -54, w: 262, d: 116, r: 8 };
const PLATE_H = 12, FOOT_H = 5;
const Y0 = -40, Y1 = 28;                          // 비탈 앞뒤
const surf = (x) => 80 - 0.318 * (x + 110);       // 비탈 겉면 높이
const SLOPE = G.unit3([1, 0, -0.318]);
const BLOCK = [-84, 36];                          // 미끄러질 흙덩이 x 범위
const BLOCK_T = 9;
const lineA = (x) => surf(x) - 14;                // 겉흙 아래 경계
const lineB = (x) => surf(x) - 32;                // 바위층 위 경계
const SPRING = [52, Y1 - 6];                      // 흙탕물이 솟는 틈
const POLE = [92, -46], POLE_TOP = 64;
const GAUGE = [104, 44], GAUGE_H = 30;
const SEIS = { x: -118, y: 34, w: 46, d: 24, r: 3 }, SEIS_TOP = 12, DIAL = [-95, 46], DIAL_R = 9, DIAL_TOP = 15;
const TREES = [[-56, -8, 34, 12], [-18, -24, 30, 10], [8, 8, 26, 9]];   // x, y, 줄기 높이, 잎 반지름

const P = k.fitProjection(
  [...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0), [-110, Y0, 80 + BLOCK_T + 40], [-110, Y1, 90], [POLE[0], POLE[1], POLE_TOP]],
  WIDTH, BAND.height, { pad: 8, azimuth: +(process.env.AZ || 62), elevation: +(process.env.EL || 26) },
);
P.origin = [P.origin[0], P.origin[1] + BAND.top];
const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (pts, style) => k.dotsSvg(pts, style);
const byDepth = (pts) => [...pts].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));
const F = { o: [0, 0, 0], a: [0, 1, 0], u: [1, 0, 0], v: [0, 0, 1] };   // 옆면(x, z) 다각형을 y 로 뽑는다
const face = (pts, y = Y1 + 0.05) => k.pathOf(pts.map(([x, z]) => at([x, y, z])), true);
const faceLine = (pts, y = Y1 + 0.05) => k.pathOf(pts.map(([x, z]) => at([x, y, z])));

function plate() {
  const out = [`<path class="iso-halo" d="${k.haloOf(PLATE, -PLATE_H - FOOT_H, PLATE_H, P)}"/>`];
  for (const [x, y] of byDepth(k.corners(PLATE, 22))) {
    out.push(S(k.cylinder(x, y, 7, -PLATE_H - FOOT_H, 1.6, P, 28), { tone: "lo" }));
    out.push(S(k.cylinder(x, y, 5.4, -PLATE_H - FOOT_H + 1.6, FOOT_H - 1.6, P, 28), { tone: "mid" }));
  }
  out.push(S(k.slabOf(PLATE, -PLATE_H, PLATE_H, P, 8, 1.6), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(PLATE, 5), 0, P), { tone: "lo" }));
  const screws = k.corners(PLATE, 10);
  out.push(L(screws.map(([x, y]) => k.ring(x, y, 2.2, 0, P, 16)).join(""), { tone: "lo" }));
  out.push(D(screws.map(([x, y]) => at([x, y, 0])), { size: 0.5 }));
  return out.join("");
}

function pole() {   // 바람 깃발: 바람이 없으니 늘어져 있다
  const [x, y] = POLE, out = [];
  out.push(S(k.cylinder(x, y, 5, 0, 2, P, 24), { tone: "lo" }));
  out.push(S(k.cylinder(x, y, 1.3, 2, POLE_TOP - 2, P, 16), { tone: "mid", crease: "none" }));
  out.push(S(k.cylinder(x, y, 2, POLE_TOP, 1.6, P, 16), { tone: "mid" }));
  // 늘어진 깃발: 기둥 옆 x+1.3 에서 아래로 처진 얇은 천(y 평면)
  const fx = x + 1.3, fy = y;
  out.push(`<path class="ls-flag" d="${k.pathOf([[fx, POLE_TOP - 1], [fx + 6, POLE_TOP - 3], [fx + 7.5, POLE_TOP - 22], [fx + 2.5, POLE_TOP - 25], [fx, POLE_TOP - 18]].map(([px, pz]) => at([px, fy, pz])), true)}"/>`);
  out.push(L(k.pathOf([[fx + 3, POLE_TOP - 3.6], [fx + 4.6, POLE_TOP - 22.6]].map(([px, pz]) => at([px, fy, pz]))), { tone: "faint" }));
  return out.join("");
}

function wedge() {
  const out = [];
  const poly = [[-110, 0], [110, 0], [110, surf(110)], [-110, surf(-110)]];
  out.push(S(G.prismOf(F, poly, Y0, Y1, P), { tone: "mid" }));
  // 앞면(단면) 지층선 — 앞면 가장자리에서 가장자리까지
  const pts = (fn) => { const a = []; for (let x = -110; x <= 110; x += 4) { const z = fn(x); if (z >= 0) a.push([x, z]); else { a.push([x - 4 + 4 * (fn(x - 4) / (fn(x - 4) - z)), 0]); break; } } return a; };
  out.push(L(faceLine(pts(lineA)), { tone: "mid" }));
  out.push(L(faceLine(pts(lineB)), { tone: "mid" }));
  // 바위층 무늬(닫힌 작은 돌 윤곽)
  let seed = 5; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const stones = [];
  for (let i = 0; i < 26; i++) {
    const x = -104 + rnd() * 140, top = lineB(x) - 4, z = 3 + rnd() * Math.max(0, top - 3);
    if (top < 6) continue;
    const r = 1.4 + rnd() * 1.6, ring = [];
    for (let s = 0; s < 7; s++) { const a = (s / 7) * Math.PI * 2; ring.push([x + r * Math.cos(a) * (1 + 0.3 * rnd()), z + r * 0.7 * Math.sin(a)]); }
    stones.push(face(ring));
  }
  out.push(L(stones.join(""), { tone: "lo" }));
  out.push(`<path data-part="water" class="ls-water" d=""/>`);
  // 겉면 위 굳은 흙(흙덩이 위·아래 부분)에 풀 점
  out.push(D([-104, -98, -92, 44, 52, 60, 70, 82, 94].map((x) => at([x, (Y0 + Y1) / 2 + ((x * 7) % 20) - 10, surf(x)])), { size: 0.45, tone: "lo" }));
  return out.join("");
}

function block() {   // 미끄러지는 흙덩이 + 나무
  const [a, b] = BLOCK;
  const poly = [[a, surf(a)], [b, surf(b)], [b, surf(b) + BLOCK_T], [a, surf(a) + BLOCK_T]];
  const out = [S(G.prismOf(F, poly, Y0 + 2, Y1, P), { tone: "hi", crease: "lo" })];
  out.push(L(faceLine([[a, surf(a) + 4], [b, surf(b) + 4]]), { tone: "faint" }));
  return out.join("");
}

function tree([x, y, h, r]) {
  const z0 = surf(x) + BLOCK_T;
  const out = [];
  out.push(S(k.cylinder(x, y, 1.5, z0, h * 0.55, P, 14), { tone: "mid", crease: "none" }));
  out.push(S(G.sphereOf([x, y, z0 + h * 0.55 + r * 0.8], r, P), { tone: "hi" }));
  out.push(S(G.sphereOf([x + r * 0.35, y + r * 0.2, z0 + h * 0.55 + r * 1.55], r * 0.7, P), { tone: "hi" }));
  return out.join("");
}

function gauge() {   // 우량계: 물 높이 선이 오른다
  const [x, y] = GAUGE, out = [];
  out.push(S(k.cylinder(x, y, 8, 0, 2, P, 32), { tone: "lo" }));
  out.push(S(k.cylinder(x, y, 6, 2, GAUGE_H, P, 32), { tone: "mid" }));
  out.push(S(k.cylinder(x, y, 7.6, GAUGE_H + 2, 2.4, P, 32), { tone: "mid" }));
  out.push(L(k.ring(x, y, 5.6, GAUGE_H + 4.4, P, 32), { tone: "lo" }));
  const t = k.sideTicks(4, GAUGE_H, 2, 5, y + 6, GAUGE_H + 2, [1, 2], P, "x");
  return out.join("");
}

function seis() {   // 진동계(땅 울림)
  const out = [];
  out.push(S(k.slabOf(SEIS, 0, SEIS_TOP, P, 4, 0.8), { tone: "mid", inner: L(k.sideSeam(SEIS, 3, P, 4), { tone: "faint" }) }));
  out.push(D(k.corners(SEIS, 3).map(([x, y]) => at([x, y, SEIS_TOP])), { size: 0.45 }));
  const [x, y] = DIAL;
  out.push(S(k.cylinder(x, y, DIAL_R, SEIS_TOP, DIAL_TOP - SEIS_TOP, P, 48, 0.6), { tone: "hi", crease: "lo" }));
  out.push(L(k.ring(x, y, DIAL_R - 1.3, DIAL_TOP, P, 48), { tone: "lo" }));
  const tk = k.radialTicks(x, y, DIAL_R - 1.5, 20, 5, DIAL_TOP, [0.9, 2], P, -0.6 * Math.PI, 1.2 * Math.PI);
  out.push(L(tk.minor, { tone: "lo" }), L(tk.major, { tone: "mid" }));
  out.push(L(k.ring(x, y, 1.1, DIAL_TOP, P, 14), { tone: "mid" }));
  // 옆 단추 두 개
  for (const bx of [-111, -104]) { out.push(S(k.cylinder(bx, 46, 2.4, SEIS_TOP, 2, P, 18), { tone: "mid" })); }
  return out.join("");
}

const needle = (share) => { const a = -0.6 * Math.PI + 1.2 * Math.PI * share, [x, y] = DIAL; return k.lineOnTop([x - Math.sin(a) * 1.6, y + Math.cos(a) * 1.6], [x + Math.sin(a) * (DIAL_R - 2.6), y - Math.cos(a) * (DIAL_R - 2.6)], DIAL_TOP + 0.2, P); };

const svg = k.figureSvg({
  width: WIDTH, height: HEIGHT, className: "ls",
  label: "산사태 실험 비탈. 비탈 단면에 겉흙·풍화층·바위층이 보이고, 지하수가 차오른다. 진동계 바늘이 떨리고 비탈 틈에서 흙탕물이 솟으며, 깃발은 늘어져 바람이 없는데 나무가 흔들린다.",
  body: [
    plate(), pole(), wedge(),
    `<g data-part="block">${block()}<g data-part="trees">${TREES.map(tree).join("")}</g></g>`,
    `<g data-part="mud" class="ls-mud"></g>`,
    `<g data-part="rain" class="ls-rain"></g>`,
    gauge(),
    `<path data-part="level" class="iso-line" data-tone="lit" d=""/>`,
    seis(),
    `<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" d="${needle(0.5)}" style="stroke-width:1.1"/>`,
  ],
});

const CSS = `<style>
.iso .ls{--mud:#8a5a2b;--water:#3b82c4}
.iso[data-theme="dark"] .ls{--mud:#c08a55;--water:#5aa6e6}
.ls-water{fill:var(--water);opacity:.28}
.ls-mud circle{fill:var(--mud)}
.ls-rain circle{fill:var(--anatomy-lo)}
.ls-flag{fill:var(--anatomy-shade-2);stroke:var(--anatomy-mid);stroke-width:.6;stroke-linejoin:round}
</style>`;

const live = `
const P = ${JSON.stringify(P)};
const surf = ${surf.toString()}, lineB = (x) => surf(x) - 32;
const Y1 = ${Y1}, Y0 = ${Y0}, SLOPE = ${JSON.stringify(SLOPE)}, SPRING = ${JSON.stringify(SPRING)};
const GAUGE = ${JSON.stringify(GAUGE)}, GAUGE_H = ${GAUGE_H}, DIAL = ${JSON.stringify(DIAL)}, DIAL_R = ${DIAL_R}, DIAL_TOP = ${DIAL_TOP};
const needle = ${needle.toString().replace(/k\.lineOnTop/g, "lineOnTop")};
const svg = document.querySelector("svg"), q = (n) => svg.querySelector('[data-part="' + n + '"]');
const el = { water: q("water"), block: q("block"), trees: q("trees"), mud: q("mud"), rain: q("rain"), level: q("level"), needle: q("needle") };
const NS = "http://www.w3.org/2000/svg";
let seed = 3; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const env = (t, a, b, ramp) => Math.max(0, Math.min(1, (t - a) / ramp, (b - t) / ramp));
let t = 0, needleAt = 0.5, nv = 0, mudT = 0, rainT = 0;
const mud = [], rain = [];
function waterPath(h) {
  const up = [], lo = [];
  for (let x = -110; x <= 110; x += 4) { const b = lineB(x), top = Math.min(surf(x) - 2, b + h); if (top <= 0) continue; up.push([x, Math.max(top, 0)]); lo.unshift([x, Math.max(b, 0)]); }
  return pathOf([...up, ...lo].map(([x, z]) => iso([x, Y1 + 0.1, z], P)), true);
}
function step(dt, vt) {
  t += dt;
  // 이야기: 0~4초 땅 울림 + 흙탕물, 3.5~7초 나무 흔들림(깃발은 그대로), 6~8초 흙덩이가 조금 미끄러짐
  const STORY = ${+(process.env.STORY || 1)};
  // 1(10/16): 땅 울림+흙탕물 → 나무 흔들림 → 흙덩이 / 2(10/20): 흙탕물이 먼저 크게 → 4초부터 땅 울림 → 흙덩이
  const rumble = STORY === 2 ? 0.15 + 0.85 * env(vt, 3.6, 7.8, 0.5) : 0.25 + 0.75 * env(vt, 0.2, 7.6, 0.5);
  const sway = STORY === 2 ? 0 : env(vt, 3.4, 7.8, 0.5), slide = Math.max(0, Math.min(1, (vt - 6) / 1.6));
  const spurt = STORY === 2 ? 1.6 : 1;
  // 바늘: 진동 = 감쇠 스프링에 흔들림을 넣는다
  const kick = (rnd() - 0.5) * 900 * rumble;
  nv += ((0.5 - needleAt) * 520 - nv * 14 + kick) * dt; needleAt += nv * dt;
  needleAt = Math.max(0.05, Math.min(0.95, needleAt));
  // 흙탕물
  mudT += dt; if (vt < (STORY === 2 ? 4.4 : 5.2) && mudT > (STORY === 2 ? 0.012 : 0.02)) { mudT = 0; const node = document.createElementNS(NS, "circle"); node.setAttribute("r", (1.2 + rnd() * 1.0).toFixed(2)); el.mud.appendChild(node);
    mud.push({ node, x: SPRING[0], y: SPRING[1] + (rnd() - 0.5) * 6, z: surf(SPRING[0]) + 0.5, vx: 8 + rnd() * 10, vy: (rnd() - 0.5) * 4, vz: (14 + rnd() * 12 * (0.5 + rumble)) * spurt, age: 0 }); }
  for (let i = mud.length - 1; i >= 0; i--) { const m = mud[i]; m.age += dt; m.vz -= 60 * dt; m.x += m.vx * dt; m.y += m.vy * dt; m.z += m.vz * dt;
    const ground = m.x < 110 ? surf(m.x) : 0; if (m.z < ground || m.age > 1.4) { m.node.remove(); mud.splice(i, 1); continue; }
    const [sx, sy] = iso([m.x, m.y, m.z], P); m.node.setAttribute("cx", sx.toFixed(1)); m.node.setAttribute("cy", sy.toFixed(1)); }
  // 비
  rainT += dt; while (rainT > 0.02) { rainT -= 0.02; const node = document.createElementNS(NS, "circle"); node.setAttribute("r", "0.55"); el.rain.appendChild(node);
    const x = -112 + rnd() * 240, y = Y0 + rnd() * (Y1 - Y0); rain.push({ node, x, y, z: 140, floor: x < 110 ? surf(x) + 2 : 0 }); }
  for (let i = rain.length - 1; i >= 0; i--) { const r = rain[i]; r.z -= 170 * dt; if (r.z < r.floor) { r.node.remove(); rain.splice(i, 1); continue; }
    const [sx, sy] = iso([r.x, r.y, r.z], P); r.node.setAttribute("cx", sx.toFixed(1)); r.node.setAttribute("cy", sy.toFixed(1)); }
  // 그리기
  el.water.setAttribute("d", waterPath(13 + 4 * Math.min(1, vt / 6)));
  const lv = 12 + 10 * Math.min(1, (vt + 2) / 8);
  el.level.setAttribute("d", sideArc(GAUGE[0], GAUGE[1], 6, 2 + lv, P, 20));
  el.needle.setAttribute("d", needle(needleAt));
  const d = 7 * slide * slide * (3 - 2 * slide);
  el.block.setAttribute("transform", translateAlong(P, [SLOPE[0] * d, SLOPE[1] * d, SLOPE[2] * d]));
  const jx = (Math.sin(t * 31) * 0.6 + Math.sin(t * 19.3) * 0.5) * 1.4 * sway, jy = Math.sin(t * 23.7) * 0.4 * sway;
  el.trees.setAttribute("transform", "translate(" + jx.toFixed(2) + " " + jy.toFixed(2) + ")");
}
let vt = -2;
window.__render = (tt) => { while (vt < tt - 1e-9) { const dt = 1 / 120; vt += dt; step(dt, Math.max(0, vt)); } };
window.__render(0);
`;

const page = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>${k.ISO_CSS}
html,body{margin:0;width:1080px;height:1920px;overflow:hidden;background:var(--anatomy-card)}
.iso-stage,.iso-stage svg{display:block;width:1080px;height:1920px}</style></head>
<body class="iso" data-theme="${theme}">${CSS}<div class="iso-stage">${svg}</div>
<script type="module">${(kitScript() + live).replace(/<\/(script)/gi, "<\\/$1")}</script></body></html>`;
writeFileSync(join(HERE, process.env.OUT || (theme === "dark" ? "landslide-video-dark.html" : "landslide-video.html")), page);
console.log("wrote", theme);
