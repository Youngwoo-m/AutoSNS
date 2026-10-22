// 길 잃음 지형 테이블 — 10/27 산행안전사고 2편 1번 장면 모형 영상(anatomy 스킬, 세로 9:16, 8초).
// 나레이션: "산에서 길을 잘못 들면 당황하기 쉽습니다. 당황해서 계속 걸으면 더 깊은 곳으로 들어갈 수 있습니다."
// 움직임: 능선 길(점선) 위 등산객 핀이 길을 벗어나 등고선 층을 따라 두 산 사이 계곡 깊은 곳으로 내려가고, 나침반 바늘은 흔들린다.
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "/Users/youngwoo/.claude/skills/anatomy/kit/iso-kit.mjs";
import * as G from "/Users/youngwoo/.claude/skills/anatomy/kit/lathe.mjs";
import { kitScript } from "/Users/youngwoo/.claude/skills/anatomy/scripts/inline-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const WIDTH = 450, HEIGHT = 800, BAND = { top: 160, height: 370 };
const PLATE = { x: -122, y: -66, w: 240, d: 132, r: 8 }, PLATE_H = 12, FOOT_H = 5;
const GROUND = { x: -112, y: -60, w: 220, d: 96, r: 4 }, G_TOP = 3, STEP = 7;
const MA = { c: [-60, -22], r: [50, 40, 30, 20, 10] };     // 왼쪽 산(높음)
const MB = { c: [62, -30], r: [44, 33, 22, 11] };          // 오른쪽 산
const CONSOLE = { x: -108, y: 42, w: 56, d: 22, r: 3 }, C_TOP = 11, DIAL = [-80, 53], DIAL_R = 9.5, DIAL_TOP = 14;
const top = (m, i) => G_TOP + STEP * (i + 1);
const P = k.fitProjection([...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0), [MA.c[0], MA.c[1], top(MA, 4) + 10]],
  WIDTH, BAND.height, { pad: 6, azimuth: +(process.env.AZ || 32), elevation: +(process.env.EL || 52) });
P.origin = [P.origin[0], P.origin[1] + BAND.top];
const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (pts, style) => k.dotsSvg(pts, style);
const byDepth = (pts) => [...pts].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));

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
  out.push(S(k.slabOf(GROUND, 0, G_TOP, P, 4, 0.5), { tone: "lo" }));
  return out.join("");
}

// 등고선 층: 살짝 찌그러진 원(산마다 다른 모양) — 볼록하게 유지
const blob = (cx, cy, r, i) => { const pts = []; for (let s = 0; s < 48; s++) { const a = (s / 48) * Math.PI * 2; const rr = r * (1 + 0.08 * Math.cos(2 * a + i) + 0.04 * Math.sin(3 * a)); pts.push([cx + rr * Math.cos(a) * 1.15, cy + rr * Math.sin(a)]); } return pts; };
function mountain(m) {
  const out = [];
  m.r.forEach((r, i) => {
    const ring = blob(m.c[0] + i * 1.5, m.c[1] - i * 1, r, i);
    out.push(S(k.extrude(ring, G_TOP + STEP * i, STEP, P), { tone: i === m.r.length - 1 ? "hi" : "mid" }));
  });
  return out.join("");
}

// 길 잃은 경로: 능선 길에서 벗어나 층을 내려가 두 산 사이 계곡으로, 앞쪽 깊은 곳까지
const dir = (() => { const dx = (4 - MA.c[0]) / 1.15, dy = 2 - MA.c[1], n = Math.hypot(dx, dy); return [dx / n, dy / n]; })();
const onA = (r, i) => [MA.c[0] + 3 + r * dir[0] * 1.15, MA.c[1] - 2 + r * dir[1], top(MA, i)];
const lost = [onA(24, 2), onA(33, 1), onA(43, 0), [4, 2, G_TOP], [4, -14, G_TOP], [5, -32, G_TOP], [4, -50, G_TOP]];
const A0 = Math.atan2(dir[1], dir[0]);
// 바른 길(능선 길): 왼쪽 산 3층 위를 도는 점선 — 정해진 점들(작은 점 표시)
const trail = []; for (let s = 0; s <= 20; s++) { const a = A0 - 2.2 + (s / 20) * 2.2; const r = 24; trail.push([MA.c[0] + 3 + r * Math.cos(a) * 1.15, MA.c[1] - 2 + r * Math.sin(a), top(MA, 2)]); }

function console_() {
  const out = [S(k.slabOf(CONSOLE, 0, C_TOP, P, 4, 0.8), { tone: "mid", inner: L(k.sideSeam(CONSOLE, 3, P, 4), { tone: "faint" }) })];
  out.push(D(k.corners(CONSOLE, 3).map(([x, y]) => at([x, y, C_TOP])), { size: 0.45 }));
  const [x, y] = DIAL;
  out.push(S(k.cylinder(x, y, DIAL_R, C_TOP, DIAL_TOP - C_TOP, P, 48, 0.6), { tone: "hi", crease: "lo" }));
  out.push(L(k.ring(x, y, DIAL_R - 1.3, DIAL_TOP, P, 48), { tone: "lo" }));
  const tk = k.radialTicks(x, y, DIAL_R - 1.5, 32, 8, DIAL_TOP, [0.9, 2.2], P);
  out.push(L(tk.minor, { tone: "lo" }), L(tk.major, { tone: "mid" }));
  // 접힌 지도(콘솔 위 얇은 판 + 닫힌 칸)
  const map = { x: -96 + 34, y: 45, w: 14, d: 15, r: 0.6 };
  out.push(S(k.slabOf(map, C_TOP, 0.5, P, 2), { tone: "hi", crease: "lo" }));
  out.push(L(k.planOutline({ x: map.x + 1.5, y: map.y + 1.5, w: 5, d: 12, r: 0.3 }, C_TOP + 0.5, P, 2) + k.planOutline({ x: map.x + 7.5, y: map.y + 1.5, w: 5, d: 12, r: 0.3 }, C_TOP + 0.5, P, 2), { tone: "faint" }));
  return out.join("");
}

const needle = (ang) => { const [x, y] = DIAL, r = DIAL_R - 2.4; return k.onTop([[x + Math.sin(ang + Math.PI) * r * 0.6, y - Math.cos(ang + Math.PI) * r * 0.6], [x + Math.sin(ang) * r, y - Math.cos(ang) * r]], DIAL_TOP + 0.2, P); };

const mounts = [[MA, mountain(MA)], [MB, mountain(MB)]].sort((a, b) => k.depthOf([a[0].c[0], a[0].c[1], 0], P) - k.depthOf([b[0].c[0], b[0].c[1], 0], P));
const svg = k.figureSvg({
  width: WIDTH, height: HEIGHT, className: "lt",
  label: "길 잃음 지형 테이블. 두 산의 등고선 층 사이로 계곡이 있고, 능선 길을 걷던 등산객 핀이 길을 벗어나 계곡 깊은 곳으로 내려간다. 앞의 나침반 바늘은 흔들린다.",
  body: [plate(), ...mounts.map((m) => m[1]),
    `<path class="lt-trail" d="${k.pathOf(trail.map(at))}"/>`,
    `<path data-part="trace" class="lt-trace" d=""/>`,
    `<g data-part="pin"><path class="lt-pin" d="${k.cylinder(0, 0, 2.6, 0, 11, P, 16).fill}"/>${S(G.sphereOf([0, 0, 14], 4, P, { steps: 28 }), { tone: "hi", lit: true })}</g>`,
    console_(),
    `<path data-part="needle" class="lt-needle" d="${needle(0)}"/>`],
});

const CSS = `<style>
.lt-trail{fill:none;stroke:#15803d;stroke-width:1.6;stroke-dasharray:3 2.6}
.lt-trace{fill:none;stroke:#dc2626;stroke-width:1.8;stroke-dasharray:2.4 2.2;opacity:.9}
.lt-pin{fill:#dc2626;stroke:#991b1b;stroke-width:.5}
.lt [data-part="pin"] path[class*="iso"]{}
.lt-needle{stroke:#dc2626;stroke-width:1.3;stroke-linecap:round;fill:none}
</style>`;

const live = `
const P = ${JSON.stringify(P)};
const DIAL = ${JSON.stringify(DIAL)}, DIAL_R = ${DIAL_R}, DIAL_TOP = ${DIAL_TOP};
const trail = ${JSON.stringify(trail)}, lost = ${JSON.stringify(lost)};
const needle = ${needle.toString().replace(/k\.onTop/g, "onTop")};
const svg = document.querySelector("svg"), q = (n) => svg.querySelector('[data-part="' + n + '"]');
const pin = q("pin"), trace = q("trace"), nd = q("needle");
const ease = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
const along = (pts, s) => { const seg = []; let tot = 0; for (let i = 1; i < pts.length; i++) { const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); seg.push(d); tot += d; }
  let want = s * tot; for (let i = 0; i < seg.length; i++) { if (want <= seg[i]) { const f = want / seg[i], a = pts[i], b = pts[i + 1];
    // 층을 내려갈 때는 끝에서 계단처럼 떨어진다
    const z = f > 0.85 ? a[2] + (b[2] - a[2]) * ((f - 0.85) / 0.15) : a[2]; return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, z]; } want -= seg[i]; } return pts[pts.length - 1]; };
window.__render = (t) => {
  // 0~1.6초 능선 길을 따라 걷다가 → 길을 벗어나 계곡으로(1.6~7.4초)
  let p, path = [];
  if (t < 1.6) { const s = 0.15 + 0.45 * (t / 1.6) * (0.6 / 0.6); p = along(trail.slice(8), Math.min(1, t / 1.6)); }
  else { const s = ease((t - 1.6) / 5.8); p = along(lost, s); for (let i = 0; i <= 40; i++) { const u = (i / 40) * s; path.push(iso(along(lost, u), P)); } }
  pin.setAttribute("transform", translateAlong(P, p));
  trace.setAttribute("d", path.length > 1 ? pathOf(path) : "");
  // 나침반: 처음엔 북쪽에 머물다가 길을 벗어나면서 크게 흔들린다(당황)
  const shake = ease((t - 1.4) / 1.5);
  const ang = 0.15 * Math.sin(t * 2) + shake * (0.9 * Math.sin(t * 5.3) + 0.5 * Math.sin(t * 9.1 + 1));
  nd.setAttribute("d", needle(ang));
};
window.__render(0);
`;

const page = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>${k.ISO_CSS}
html,body{margin:0;width:1080px;height:1920px;overflow:hidden;background:var(--anatomy-card)}
.iso-stage,.iso-stage svg{display:block;width:1080px;height:1920px}</style></head>
<body class="iso" data-theme="light">${CSS}<div class="iso-stage">${svg}</div>
<script type="module">${(kitScript() + live).replace(/<\/(script)/gi, "<\\/$1")}</script></body></html>`;
writeFileSync(join(HERE, "lost-video.html"), page);
console.log("wrote");
