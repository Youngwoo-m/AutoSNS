// 좁은 통로 압력 실험대 — 10/30 다중운집사고 1번 장면 모형 영상(anatomy 스킬, 세로 9:16, 8초).
// 나레이션: "보행 속도가 느려지고 몸이 닿으면 위험 신호입니다. 좁은 길과 비탈길은 사고 위험이 높습니다."
// 움직임: 넓은 입구로 들어온 구슬(사람)이 좁은 통로에서 느려지고 서로 닿으며 쌓이고, 바닥 감지판의 압력계 바늘이 위험 구역으로.
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "/Users/youngwoo/.claude/skills/anatomy/kit/iso-kit.mjs";
import { kitScript } from "/Users/youngwoo/.claude/skills/anatomy/scripts/inline-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const WIDTH = 450, HEIGHT = 800, BAND = { top: 160, height: 370 };
const PLATE = { x: -128, y: -50, w: 256, d: 108, r: 8 }, PLATE_H = 12, FOOT_H = 5;
const FLOOR = { x: -116, y: -34, w: 228, d: 56, r: 2 }, FLOOR_TOP = 3;
const BACK_Y = -30, WALL_H = 9, FRONT_H = 3.5, NARROW = [-30, -10];       // 좁은 통로 y 범위(폭 20)
const FUNNEL_X = [-70, -36];                                // 깔때기 구간
const WIDE = [-30, 18];                                     // 넓은 입구 y 범위
const SENSOR = { x: 30, y: -29, w: 44, d: 18, r: 1 };       // 바닥 압력 감지판
const EXIT_X = 104;
const CONSOLE = { x: 60, y: 30, w: 50, d: 22, r: 3 }, C_TOP = 11, DIAL = [85, 41], DIAL_R = 9.5, DIAL_TOP = 14;
const R = 3.1;                                              // 구슬 반지름

const P = k.fitProjection([...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0), [FLOOR.x, BACK_Y - 4, FLOOR_TOP + WALL_H + 4]],
  WIDTH, BAND.height, { pad: 4, azimuth: +(process.env.AZ || 42), elevation: +(process.env.EL || 46) });
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
  return out.join("");
}

function floor() {
  const out = [S(k.slabOf(FLOOR, 0, FLOOR_TOP, P, 3, 0.5), { tone: "mid" })];
  // 감지판(바닥에 묻힌 얇은 판) + 둘레 홈
  out.push(S(k.slabOf(SENSOR, FLOOR_TOP, 0.4, P, 2), { tone: "hi", crease: "lo" }));
  out.push(L(k.planOutline(k.insetPlan(SENSOR, 1.5), FLOOR_TOP + 0.4, P, 2), { tone: "lo" }));
  // 바닥 격자(통로 안, 칸마다 닫힌 사각 홈)
  const cells = [];
  for (let x = -112; x < 100; x += 12) cells.push(k.planOutline({ x: x + 1, y: NARROW[0] + 1, w: 10, d: NARROW[1] - NARROW[0] - 2, r: 0.6 }, FLOOR_TOP, P, 2));
  out.push(L(cells.join(""), { tone: "faint" }));
  return out.join("");
}

function backWall() {
  const out = [S(k.slabOf({ x: FLOOR.x, y: BACK_Y - 4, w: FLOOR.w - 4, d: 4, r: 0.5 }, FLOOR_TOP, WALL_H, P, 2, 0.4), { tone: "mid" })];
  out.push(D([-100, -60, -20, 20, 60].map((x) => at([x, BACK_Y - 2, FLOOR_TOP + WALL_H])), { size: 0.45 }));
  return out.join("");
}

function frontWalls() {
  const out = [];
  // 넓은 입구 앞벽 → 깔때기 사선벽 → 좁은 통로 앞벽
  out.push(S(k.slabOf({ x: FLOOR.x, y: WIDE[1], w: FUNNEL_X[0] - FLOOR.x, d: 4, r: 0.5 }, FLOOR_TOP, FRONT_H, P, 2, 0.4), { tone: "mid" }));
  const t = 4, [a, b] = FUNNEL_X;
  out.push(S(k.extrude([[a, WIDE[1]], [a + 2.5, WIDE[1]], [b + 2.5, NARROW[1]], [b, NARROW[1]], [b, NARROW[1] + t], [a, WIDE[1] + t]], FLOOR_TOP, FRONT_H, P), { tone: "mid" }));
  out.push(S(k.slabOf({ x: b, y: NARROW[1], w: EXIT_X - 4 - b, d: 4, r: 0.5 }, FLOOR_TOP, FRONT_H, P, 2, 0.4), { tone: "mid" }));
  out.push(D([-100, -80, -10, 30, 70].map((x) => at([x, x < a ? WIDE[1] + 2 : NARROW[1] + 2, FLOOR_TOP + FRONT_H])), { size: 0.45 }));
  // 출구 문틀(좁은 틈)
  out.push(S(k.slabOf({ x: EXIT_X - 4, y: BACK_Y - 4, w: 4, d: 7, r: 0.4 }, FLOOR_TOP, WALL_H + 4, P, 2), { tone: "mid" }));
  out.push(S(k.slabOf({ x: EXIT_X - 4, y: NARROW[1] - 3, w: 4, d: 7, r: 0.4 }, FLOOR_TOP, WALL_H + 4, P, 2), { tone: "mid" }));
  out.push(S(k.slabOf({ x: EXIT_X - 4, y: BACK_Y - 4, w: 4, d: NARROW[1] + 4 - BACK_Y + 4, r: 0.4 }, FLOOR_TOP + WALL_H + 4, 2, P, 2, 0.3), { tone: "mid" }));
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
  const arc = []; for (let i = 0; i <= 12; i++) { const a = 0.25 * Math.PI + 0.35 * Math.PI * i / 12; arc.push([x + Math.sin(a) * (DIAL_R - 3.4), y - Math.cos(a) * (DIAL_R - 3.4)]); }
  out.push(`<path class="cr-danger" d="${k.onTop(arc, DIAL_TOP + 0.05, P)}"/>`);
  out.push(L(k.ring(x, y, 1.1, DIAL_TOP, P, 14), { tone: "mid" }));
  // 감지판과 계기를 잇는 바닥 홈(케이블 덮개): 감지판 앞 가장자리 → 콘솔 뒷면
  out.push(S(k.slabOf({ x: 50, y: NARROW[1] + 4, w: 4, d: CONSOLE.y - NARROW[1] - 4, r: 0.6 }, 0, 1.2, P, 2), { tone: "lo", crease: "none" }));
  return out.join("");
}

const needle = (share) => { const a = -0.6 * Math.PI + 1.2 * Math.PI * share, [x, y] = DIAL; return k.lineOnTop([x - Math.sin(a) * 1.6, y + Math.cos(a) * 1.6], [x + Math.sin(a) * (DIAL_R - 2.4), y - Math.cos(a) * (DIAL_R - 2.4)], DIAL_TOP + 0.2, P); };

const svg = k.figureSvg({
  width: WIDTH, height: HEIGHT, className: "cr",
  label: "좁은 통로 압력 실험대. 넓은 입구로 들어온 구슬들이 깔때기를 지나 좁은 통로에서 느려지고 서로 닿으며 쌓인다. 바닥 감지판의 압력계 바늘이 위험 구역으로 올라간다.",
  body: [plate(), floor(), backWall(), `<g data-part="balls"></g>`, frontWalls(), console_(),
    `<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" d="${needle(0.05)}" style="stroke-width:1.1"/>`],
});

const CSS = `<style>
.cr [data-part="balls"] .b{fill:var(--anatomy-shade-2);stroke:var(--anatomy-mid);stroke-width:.5}
.cr [data-part="balls"] .h{fill:var(--anatomy-top);stroke:none}
.cr [data-part="balls"] .tight{fill:#f3b4a0;stroke:#b4432a}
.cr-danger{stroke:#dc2626;stroke-width:1.6;fill:none}
</style>`;

const live = `
const P = ${JSON.stringify(P)};
const R = ${R}, FLOOR_TOP = ${FLOOR_TOP}, NARROW = ${JSON.stringify(NARROW)}, WIDE = ${JSON.stringify(WIDE)}, FUNNEL_X = ${JSON.stringify(FUNNEL_X)}, EXIT_X = ${EXIT_X}, SENSOR = ${JSON.stringify(SENSOR)};
const DIAL = ${JSON.stringify(DIAL)}, DIAL_R = ${DIAL_R}, DIAL_TOP = ${DIAL_TOP};
const needle = ${needle.toString().replace(/k\.lineOnTop/g, "lineOnTop")};
const svg = document.querySelector("svg"), g = svg.querySelector('[data-part="balls"]'), nd = svg.querySelector('[data-part="needle"]');
const NS = "http://www.w3.org/2000/svg";
let seed = 21; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const K = Math.sqrt(1.6) * P.scale;   // 화면 단위/세계 단위
const balls = [];
let t = 0, spawnT = 0, exitT = 0, gauge = 0.05, gv = 0;
// 통로 폭: x 에 따라 넓은 입구 → 좁은 통로
const bounds = (x) => { const s = Math.max(0, Math.min(1, (x - FUNNEL_X[0]) / (FUNNEL_X[1] - FUNNEL_X[0]))); return [WIDE[0] + (NARROW[0] - WIDE[0]) * s + R + 0.3, WIDE[1] + (NARROW[1] - WIDE[1]) * s - R - 0.3]; };
function spawn() {
  const [lo, hi] = bounds(-112);
  const node = document.createElementNS(NS, "g");
  node.innerHTML = '<circle class="b"/><circle class="h"/>';
  g.appendChild(node);
  balls.push({ node, x: -114, y: lo + rnd() * (hi - lo), vx: 0, vy: 0, out: false });
}
function step(dt) {
  t += dt;
  spawnT += dt; const rate = 0.16 - 0.05 * Math.min(1, t / 6); if (spawnT > rate && balls.length < 70) { spawnT = 0; spawn(); }
  exitT += dt;
  for (const b of balls) {           // 오른쪽으로 걷는 힘 + 벽
    b.vx += (22 - b.vx) * 2.2 * dt; b.vy *= 1 - 3 * dt;
    const [lo, hi] = bounds(b.x);
    if (b.y < lo) { b.y = lo; b.vy = Math.abs(b.vy) * 0.2; } if (b.y > hi) { b.y = hi; b.vy = -Math.abs(b.vy) * 0.2; }
  }
  // 서로 밀어내기(몸이 닿으면 겹치지 않게)
  for (let i = 0; i < balls.length; i++) for (let j = i + 1; j < balls.length; j++) {
    const a = balls[i], c = balls[j], dx = c.x - a.x, dy = c.y - a.y, d = Math.hypot(dx, dy), m = 2 * R;
    if (d < m && d > 1e-6) { const push = (m - d) / 2, nx = dx / d, ny = dy / d; a.x -= nx * push; a.y -= ny * push; c.x += nx * push; c.y += ny * push;
      const rv = (c.vx - a.vx) * nx + (c.vy - a.vy) * ny; if (rv < 0) { a.vx += rv * nx * 0.5; a.vy += rv * ny * 0.5; c.vx -= rv * nx * 0.5; c.vy -= rv * ny * 0.5; } }
  }
  // 출구는 좁아서 0.55초에 한 명씩만 나간다
  for (const b of balls) {
    b.x += b.vx * dt; b.y += b.vy * dt;
    if (b.x > EXIT_X - 4 - R && !b.out) { if (exitT > 0.55) { exitT = 0; b.out = true; } else { b.x = EXIT_X - 4 - R; b.vx = 0; } }
  }
  for (let i = balls.length - 1; i >= 0; i--) if (balls[i].x > EXIT_X + 14) { balls[i].node.remove(); balls.splice(i, 1); }
  // 압력: 감지판 위 구슬 수와 서로 닿은 정도
  let on = 0; for (const b of balls) if (b.x > SENSOR.x && b.x < SENSOR.x + SENSOR.w) on++;
  const target = Math.min(0.95, 0.05 + on / 16);
  gv += ((target - gauge) * 60 - gv * 11) * dt; gauge += gv * dt;
}
function draw() {
  balls.sort((a, b) => depthOf([a.x, a.y, 0], P) - depthOf([b.x, b.y, 0], P));
  for (const b of balls) {
    g.appendChild(b.node);
    const [sx, sy] = iso([b.x, b.y, FLOOR_TOP + R], P), r = R * K * 0.92;
    let near = 0; for (const c of balls) if (c !== b && Math.hypot(c.x - b.x, c.y - b.y) < 2 * R + 0.25) near++;
    const [bc, hc] = b.node.children;
    bc.setAttribute("cx", sx.toFixed(1)); bc.setAttribute("cy", sy.toFixed(1)); bc.setAttribute("r", r.toFixed(2));
    bc.setAttribute("class", near >= 3 ? "b tight" : "b");
    hc.setAttribute("cx", (sx - r * 0.35).toFixed(1)); hc.setAttribute("cy", (sy - r * 0.35).toFixed(1)); hc.setAttribute("r", (r * 0.35).toFixed(2));
  }
  nd.setAttribute("d", needle(Math.max(0.03, Math.min(0.97, gauge))));
}
let vt = -2.5;
window.__render = (tt) => { while (vt < tt - 1e-9) { vt += 1 / 120; step(1 / 120); } draw(); };
window.__render(0);
`;

const page = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>${k.ISO_CSS}
html,body{margin:0;width:1080px;height:1920px;overflow:hidden;background:var(--anatomy-card)}
.iso-stage,.iso-stage svg{display:block;width:1080px;height:1920px}</style></head>
<body class="iso" data-theme="light">${CSS}<div class="iso-stage">${svg}</div>
<script type="module">${(kitScript() + live).replace(/<\/(script)/gi, "<\\/$1")}</script></body></html>`;
writeFileSync(join(HERE, "crowd-video.html"), page);
console.log("wrote");
