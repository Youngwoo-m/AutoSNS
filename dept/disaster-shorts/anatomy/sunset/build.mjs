// 해넘이 온도 실험대 — 10/23 산행안전사고 1번 장면 모형 영상(anatomy 스킬, 세로 9:16, 8초).
// 나레이션: "단풍철 산 노을은 아름답지만 그 뒤엔 위험이 숨어 있습니다. 해가 지면 기온이 떨어져 저체온증 위험이 커집니다."
// 움직임: 해 램프가 호 레일을 따라 능선 뒤로 지고, 온도계 기둥이 내려가며, 체온계 바늘이 위험 구역으로, 장면 전체가 어스름해진다.
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "/Users/youngwoo/.claude/skills/anatomy/kit/iso-kit.mjs";
import * as G from "/Users/youngwoo/.claude/skills/anatomy/kit/lathe.mjs";
import { kitScript } from "/Users/youngwoo/.claude/skills/anatomy/scripts/inline-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const WIDTH = 450, HEIGHT = 800, BAND = { top: 160, height: 370 };
const PLATE = { x: -118, y: -56, w: 236, d: 116, r: 8 }, PLATE_H = 12, FOOT_H = 5;
const RY0 = -22, RY1 = 14;                                  // 능선 앞뒤
const RIDGE = [[-100, 0], [100, 0], [100, 42], [62, 64], [12, 72], [-60, 46]];
const RAIL_Y = -44, RAIL_R = 92, RAIL_C = [0, 4];           // 호 레일(뒤쪽, x-z 평면의 반원)
const THERMO = [92, 40], THERMO_H = 56;
const CONSOLE = { x: -112, y: 26, w: 52, d: 26, r: 3 }, C_TOP = 12, DIAL = [-86, 39], DIAL_R = 10, DIAL_TOP = 15;
const HIKER = [-30, 0];                                     // 능선 위 등산객 인형(겉면 높이에서)

const ridgeZ = (x) => {   // 능선 윗면 높이
  for (let i = 1; i < RIDGE.length; i++) {
    const a = RIDGE[(i + 1) % RIDGE.length], b = RIDGE[i];
    const [x0, z0] = i === RIDGE.length - 1 ? RIDGE[i] : RIDGE[i + 1], [x1, z1] = RIDGE[i === RIDGE.length - 1 ? 0 : i];
  }
  const top = [[-100, 0], [-60, 46], [12, 72], [62, 64], [100, 42]];
  for (let i = 0; i < top.length - 1; i++) if (x >= top[i][0] && x <= top[i + 1][0]) { const t = (x - top[i][0]) / (top[i + 1][0] - top[i][0]); return top[i][1] + t * (top[i + 1][1] - top[i][1]); }
  return 0;
};

const P = k.fitProjection(
  [...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0), [-RAIL_R, RAIL_Y, RAIL_C[1]], [RAIL_R, RAIL_Y, RAIL_C[1]], [0, RAIL_Y, RAIL_C[1] + RAIL_R + 8], [THERMO[0], THERMO[1], THERMO_H + 6]],
  WIDTH, BAND.height, { pad: 8, azimuth: +(process.env.AZ || 58), elevation: +(process.env.EL || 24) },
);
P.origin = [P.origin[0], P.origin[1] + BAND.top];
const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (pts, style) => k.dotsSvg(pts, style);
const byDepth = (pts) => [...pts].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));
const F = { o: [0, 0, 0], a: [0, 1, 0], u: [1, 0, 0], v: [0, 0, 1] };
const railAt = (ang) => [RAIL_C[0] + RAIL_R * Math.cos(ang), RAIL_Y, RAIL_C[1] + RAIL_R * Math.sin(ang)];

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

function rail() {   // 뒤쪽 호 레일과 두 기둥(레일 끝은 기둥 위에 닿는다)
  const out = [];
  for (const x of [-RAIL_R, RAIL_R]) {
    out.push(S(k.cylinder(x, RAIL_Y, 5, 0, 2, P, 24), { tone: "lo" }));
    out.push(S(k.cylinder(x, RAIL_Y, 2.2, 2, RAIL_C[1] - 2, P, 18), { tone: "mid", crease: "none" }));
    out.push(S(k.cylinder(x, RAIL_Y, 3, RAIL_C[1], 2, P, 18), { tone: "mid" }));
  }
  const pts = []; for (let i = 0; i <= 64; i++) pts.push(railAt(Math.PI * (i / 64)));
  const c = (r) => pts.map((p) => at([p[0] * (RAIL_R + r) / RAIL_R, p[1], RAIL_C[1] + (p[2] - RAIL_C[1]) * (RAIL_R + r) / RAIL_R]));
  out.push(`<path class="ss-rail" d="${k.pathOf([...c(1.6), ...c(-1.6).reverse()], true)}"/>`);
  // 레일 눈금(해 높이)
  const ticks = []; for (let i = 1; i < 18; i++) { const a = Math.PI * i / 18, p0 = railAt(a), r1 = (RAIL_R - 1.6) / RAIL_R, r2 = (RAIL_R - (i % 3 ? 4 : 6)) / RAIL_R;
    ticks.push(k.pathOf([at([p0[0] * r1, RAIL_Y, RAIL_C[1] + (p0[2] - RAIL_C[1]) * r1]), at([p0[0] * r2, RAIL_Y, RAIL_C[1] + (p0[2] - RAIL_C[1]) * r2])])); }
  out.push(L(ticks.join(""), { tone: "lo" }));
  return out.join("");
}

function ridge() {
  const out = [S(G.prismOf(F, RIDGE, RY0, RY1, P), { tone: "mid" })];
  // 앞면 지층 비슷한 숲 경계선(가장자리에서 가장자리로)
  const edge = (dz) => { const a = []; for (let x = -100; x <= 100; x += 4) { const z = ridgeZ(x) - dz; if (z > 0) a.push(at([x, RY1 + 0.05, z])); } return a; };
  out.push(L(k.pathOf(edge(10)), { tone: "faint", free: true }));
  // 단풍 나무(윗면 위 작은 구) — 색이 이 장면의 주제
  let seed = 9; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const trees = [];
  for (let i = 0; i < 44; i++) { const x = -90 + rnd() * 186, y = RY0 + 3 + rnd() * (RY1 - RY0 - 6); trees.push([x, y, ridgeZ(x)]); }
  trees.sort((a, b) => k.depthOf(a, P) - k.depthOf(b, P));
  for (const [x, y, z] of trees) {
    out.push(S(k.cylinder(x, y, 0.6, z, 2.6, P, 10), { tone: "mid", crease: "none" }));
    out.push(`<g class="ss-leaf">${S(G.sphereOf([x, y, z + 4.6], 2.3, P, { steps: 20 }), { tone: "hi" })}</g>`);
  }
  // 등산객 인형
  const [hx, hy] = HIKER, hz = ridgeZ(hx);
  out.push(S(k.cylinder(hx, hy, 1.6, hz, 6, P, 14), { tone: "hi" }));
  out.push(S(k.cylinder(hx - 1.4, hy - 1.2, 1.4, hz + 2.5, 3, P, 12), { tone: "mid" }));
  out.push(S(G.sphereOf([hx, hy, hz + 7.6], 1.7, P, { steps: 20 }), { tone: "hi" }));
  return out.join("");
}

function thermo() {
  const [x, y] = THERMO, out = [];
  out.push(S(k.cylinder(x, y, 8, 0, 2, P, 32), { tone: "lo" }));
  out.push(S(k.slabOf({ x: x - 5, y: y - 3, w: 10, d: 6, r: 2 }, 2, THERMO_H, P, 3, 0.4), { tone: "mid" }));
  out.push(S(k.cylinder(x, y + 3.3, 2.8, 4, 5, P, 18), { tone: "hi" }));   // 구부(아래 둥근 통)
  // 앞면 홈과 눈금 — 눈금은 홈 가장자리에서 자란다
  const t = k.sideTicks(12, THERMO_H - 4, 3, 5, y + 3, x + 2.2, [1.2, 2.2], P, "z");
  out.push(L(k.pathOf([[x - 1.2, 9], [x + 1.2, 9], [x + 1.2, THERMO_H - 2], [x - 1.2, THERMO_H - 2]].map(([px, pz]) => at([px, y + 3, pz])), true), { tone: "lo" }));
  const ticks = []; for (let z = 12, i = 0; z <= THERMO_H - 4; z += 3, i++) ticks.push(k.pathOf([at([x + 1.2, y + 3, z]), at([x + (i % 5 ? 2.6 : 3.8), y + 3, z])]));
  out.push(L(ticks.join(""), { tone: "lo" }));
  return out.join("");
}

function console_() {
  const out = [S(k.slabOf(CONSOLE, 0, C_TOP, P, 4, 0.8), { tone: "mid", inner: L(k.sideSeam(CONSOLE, 3, P, 4), { tone: "faint" }) })];
  out.push(D(k.corners(CONSOLE, 3).map(([x, y]) => at([x, y, C_TOP])), { size: 0.45 }));
  const [x, y] = DIAL;
  out.push(S(k.cylinder(x, y, DIAL_R, C_TOP, DIAL_TOP - C_TOP, P, 48, 0.6), { tone: "hi", crease: "lo" }));
  out.push(L(k.ring(x, y, DIAL_R - 1.3, DIAL_TOP, P, 48), { tone: "lo" }));
  const tk = k.radialTicks(x, y, DIAL_R - 1.5, 20, 5, DIAL_TOP, [0.9, 2], P, -0.6 * Math.PI, 1.2 * Math.PI);
  out.push(L(tk.minor, { tone: "lo" }), L(tk.major, { tone: "mid" }));
  // 위험 구역(오른쪽 끝) 굵은 호
  const arc = []; for (let i = 0; i <= 12; i++) { const a = 0.25 * Math.PI + 0.35 * Math.PI * i / 12; arc.push([x + Math.sin(a) * (DIAL_R - 3.6), y - Math.cos(a) * (DIAL_R - 3.6)]); }
  out.push(`<path class="ss-danger" d="${k.onTop(arc, DIAL_TOP + 0.05, P)}"/>`);
  out.push(L(k.ring(x, y, 1.1, DIAL_TOP, P, 14), { tone: "mid" }));
  return out.join("");
}

const needle = (share) => { const a = -0.6 * Math.PI + 1.2 * Math.PI * share, [x, y] = DIAL; return k.lineOnTop([x - Math.sin(a) * 1.6, y + Math.cos(a) * 1.6], [x + Math.sin(a) * (DIAL_R - 2.6), y - Math.cos(a) * (DIAL_R - 2.6)], DIAL_TOP + 0.2, P); };
const column = (level) => { const [x, y] = THERMO; return k.pathOf([at([x, y + 3.05, 9]), at([x, y + 3.05, level])]); };

const svg = k.figureSvg({
  width: WIDTH, height: HEIGHT, className: "ss",
  label: "해넘이 온도 실험대. 뒤쪽 호 레일을 따라 해 램프가 단풍 든 능선 뒤로 지고, 오른쪽 온도계 기둥이 내려가며, 앞의 체온계 바늘이 위험 구역으로 움직인다.",
  body: [
    plate(), rail(),
    `<g data-part="sun">${S(G.sphereOf([0, 0, 0], 7, P, { steps: 40 }), { tone: "hi", lit: true })}</g>`,
    ridge(), thermo(),
    `<path data-part="column" class="ss-col" d="${column(40)}"/>`,
    console_(),
    `<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" d="${needle(0.3)}" style="stroke-width:1.1"/>`,
    `<rect data-part="dusk" class="ss-dusk" x="0" y="0" width="${WIDTH}" height="${HEIGHT}" opacity="0"/>`,
  ],
});

const CSS = `<style>
.iso .ss{--sun:#f59e0b;--leaf:#d9622b;--col:#dc2626;--dusk:#1e2a4a}
.ss [data-part="sun"] path{fill:var(--sun)!important;stroke:#b45309}
.ss-leaf path{fill:var(--leaf)!important;stroke:#9a3412}
.ss-rail{fill:var(--anatomy-shade-2);stroke:var(--anatomy-mid);stroke-width:.6}
.ss-col{stroke:var(--col);stroke-width:2.2;stroke-linecap:round;fill:none}
.ss-danger{stroke:#2563eb;stroke-width:1.6;fill:none}
.ss-dusk{fill:var(--dusk);pointer-events:none}
</style>`;

const live = `
const P = ${JSON.stringify(P)};
const RAIL_C = ${JSON.stringify(RAIL_C)}, RAIL_R = ${RAIL_R}, RAIL_Y = ${RAIL_Y}, THERMO = ${JSON.stringify(THERMO)}, DIAL = ${JSON.stringify(DIAL)}, DIAL_R = ${DIAL_R}, DIAL_TOP = ${DIAL_TOP}, THERMO_H = ${THERMO_H};
const needle = ${needle.toString().replace(/k\.lineOnTop/g, "lineOnTop")};
const svg = document.querySelector("svg"), q = (n) => svg.querySelector('[data-part="' + n + '"]');
const sun = q("sun"), col = q("column"), nd = q("needle"), dusk = q("dusk");
const ease = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
window.__render = (t) => {
  // 해: 0초 높이 60° → 5.6초 레일 끝(0°, 능선 뒤로 숨음)
  const s = ease(t / 5.6), ang = Math.PI * ((62 - 40 * s) / 180);
  const p = [RAIL_C[0] + RAIL_R * Math.cos(ang), RAIL_Y, RAIL_C[1] + RAIL_R * Math.sin(ang)];
  sun.setAttribute("transform", translateAlong(P, p)); sun.setAttribute("opacity", (1 - 0.6 * ease((t - 4.2) / 1.8)).toFixed(3));
  // 기온과 체온 위험: 해가 진 뒤 따라 내려간다
  const cool = ease((t - 0.8) / 6.2);
  const [x, y] = THERMO; col.setAttribute("d", pathOf([iso([x, y + 3.05, 9], P), iso([x, y + 3.05, 44 - 28 * cool], P)]));
  nd.setAttribute("d", needle(0.3 + 0.62 * ease((t - 2) / 5.4)));
  dusk.setAttribute("opacity", (0.32 * ease((t - 3) / 4.5)).toFixed(3));
};
window.__render(0);
`;

const page = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>${k.ISO_CSS}
html,body{margin:0;width:1080px;height:1920px;overflow:hidden;background:var(--anatomy-card)}
.iso-stage,.iso-stage svg{display:block;width:1080px;height:1920px}</style></head>
<body class="iso" data-theme="light">${CSS}<div class="iso-stage">${svg}</div>
<script type="module">${(kitScript() + live).replace(/<\/(script)/gi, "<\\/$1")}</script></body></html>`;
writeFileSync(join(HERE, "sunset-video.html"), page);
console.log("wrote");
