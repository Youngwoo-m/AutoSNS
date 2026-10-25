// 디오라마 장면 오른쪽 위에 얹는 계기판(anatomy 스킬). 정사각 400×400, 8초.
//   GAUGE=seismo|seismo2|thermo|compass|pressure node build.mjs   → gauge-<종류>.html
// seismo: 진동계(바늘 + 지진 기록 띠), thermo: 온도계 + 체온 위험 바늘, compass: 나침반, pressure: 압력계.
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "/Users/youngwoo/.claude/skills/anatomy/kit/iso-kit.mjs";
import { kitScript } from "/Users/youngwoo/.claude/skills/anatomy/scripts/inline-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const KIND = process.env.GAUGE || "seismo";
const W = 300, H = 300;
const BASE = { x: -46, y: -38, w: 92, d: 76, r: 6 }, BASE_H = 8;
const P = k.fitProjection([...k.boxCorners(BASE, -BASE_H - 3, 0), [0, 0, 40]], W, H, { pad: 18, azimuth: 40, elevation: 38 });
const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (pts, style) => k.dotsSvg(pts, style);

function base() {
  const out = [`<path class="iso-halo" d="${k.haloOf(BASE, -BASE_H - 3, BASE_H, P)}"/>`];
  for (const [x, y] of k.corners(BASE, 10).sort((a, b) => k.depthOf([...a, 0], P) - k.depthOf([...b, 0], P)))
    out.push(S(k.cylinder(x, y, 4, -BASE_H - 3, 3, P, 20), { tone: "lo" }));
  out.push(S(k.slabOf(BASE, -BASE_H, BASE_H, P, 6, 1.2), { tone: "mid" }));
  out.push(L(k.planOutline(k.insetPlan(BASE, 3.5), 0, P), { tone: "lo" }));
  out.push(D(k.corners(BASE, 6).map(([x, y]) => at([x, y, 0])), { size: 0.55 }));
  return out.join("");
}

// 앞면이 위를 보는 둥근 계기(바늘 축 = c, 반지름 R)
function dial(c, R, z, h, { span = 1.2, count = 24, every = 4, danger = false } = {}) {
  const [x, y] = c, top = z + h, out = [];
  out.push(S(k.cylinder(x, y, R + 2, z, h - 1.5, P, 56, 0.6), { tone: "mid" }));
  out.push(S(k.cylinder(x, y, R, z + h - 1.5, 1.5, P, 56, 0.4), { tone: "hi", crease: "lo" }));
  out.push(L(k.ring(x, y, R - 1.2, top, P, 56), { tone: "lo" }));
  const from = -span / 2 * Math.PI, tk = k.radialTicks(x, y, R - 1.4, count, every, top, [1.4, 3], P, from, span * Math.PI);
  out.push(L(tk.minor, { tone: "lo" }), L(tk.major, { tone: "mid" }));
  if (danger) { const arc = []; for (let i = 0; i <= 14; i++) { const a = from + span * Math.PI * (0.72 + 0.28 * i / 14); arc.push([x + Math.sin(a) * (R - 5.2), y - Math.cos(a) * (R - 5.2)]); } out.push(`<path class="gg-danger" d="${k.onTop(arc, top + 0.05, P)}"/>`); }
  out.push(L(k.ring(x, y, 1.6, top, P, 16), { tone: "mid" }));
  return out.join("");
}
const needleSrc = (c, R, top, span) => `(share) => { const a = ${-span / 2} * Math.PI + ${span} * Math.PI * share, x = ${c[0]}, y = ${c[1]}; return lineOnTop([x - Math.sin(a) * 2.4, y + Math.cos(a) * 2.4], [x + Math.sin(a) * ${R - 3.6}, y - Math.cos(a) * ${R - 3.6}], ${top + 0.2}, P); }`;
const needleOf = (c, R, top, span) => { const f = new Function("lineOnTop", "P", "return " + needleSrc(c, R, top, span))(k.lineOnTop, P); f.src = needleSrc(c, R, top, span); return f; };

let body = [base()], live = "", needle;
if (KIND.startsWith("seismo")) {
  const C = [-14, -6], R = 22, Z = 0, Hh = 9;
  body.push(dial(C, R, Z, Hh, { span: 1.2 }));
  // 기록 띠: 오른쪽 받침 위 종이 띠, 파형은 띠 가장자리에서 가장자리까지
  const strip = { x: 16, y: -30, w: 24, d: 60, r: 1.5 };
  body.push(S(k.slabOf(strip, 0, 5, P, 3, 0.4), { tone: "mid" }), S(k.slabOf(k.insetPlan(strip, 2), 5, 0.6, P, 2), { tone: "hi", crease: "lo" }));
  body.push(S(k.cylinder(strip.x + strip.w / 2, strip.y + 2, 3, 5, 3, P, 18), { tone: "mid" }), S(k.cylinder(strip.x + strip.w / 2, strip.y + strip.d - 2, 3, 5, 3, P, 18), { tone: "mid" }));
  needle = needleOf(C, R, Z + Hh, 1.2);
  body.push(`<path data-part="trace" class="gg-trace" d=""/>`, `<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" style="stroke-width:1.6" d="${needle(0.5)}"/>`);
  const late = KIND === "seismo2";
  live = `
  const strip = ${JSON.stringify(strip)}, late = ${late};
  const needle = ${needle.src};
  const env = (t, a, b, r) => Math.max(0, Math.min(1, (t - a) / r, (b - t) / r));
  const amp = (t) => late ? 0.15 + 0.85 * env(t, 3.6, 8.6, 0.5) : 0.25 + 0.75 * env(t, 0.2, 8.6, 0.5);
  let seed = 4; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  let nAt = 0.5, nv = 0, tt = -1; const hist = [];
  window.__render = (T) => { while (tt < T) { const dt = 1 / 120; tt += dt; const a = amp(Math.max(0, tt));
      nv += ((0.5 - nAt) * 700 - nv * 16 + (rnd() - 0.5) * 1400 * a) * dt; nAt = Math.max(0.05, Math.min(0.95, nAt + nv * dt));
      hist.push(nAt); if (hist.length > 360) hist.shift(); }
    q("needle").setAttribute("d", needle(nAt));
    const pts = []; const y0 = strip.y + 3, y1 = strip.y + strip.d - 3, n = hist.length;
    for (let i = 0; i < n; i += 3) { const y = y0 + (y1 - y0) * (i / 359); pts.push([strip.x + strip.w / 2 + (hist[i] - 0.5) * (strip.w - 6), y]); }
    q("trace").setAttribute("d", onTop(pts, 5.7, P));
  };`;
} else if (KIND === "thermo") {
  const TH = { x: -30, y: -6, w: 14, d: 10, r: 3 }, TH_H = 46;
  body.push(S(k.slabOf(TH, 0, TH_H, P, 3, 0.6), { tone: "mid" }));
  body.push(S(k.cylinder(-23, 4.5, 4, 2, 6, P, 20), { tone: "hi" }));
  const groove = k.pathOf([[-24.6, 10], [-21.4, 10], [-21.4, TH_H - 4], [-24.6, TH_H - 4]].map(([x, z]) => at([x, 4.05, z])), true);
  const ticks = []; for (let z = 12, i = 0; z <= TH_H - 6; z += 3, i++) ticks.push(k.pathOf([at([-21.4, 4.05, z]), at([i % 5 ? -18.8 : -17.4, 4.05, z])]));
  body.push(L(groove, { tone: "lo" }), L(ticks.join(""), { tone: "lo" }));
  body.push(`<path data-part="col" class="gg-col" d=""/>`);
  const C = [16, 4], R = 20; body.push(dial(C, R, 0, 9, { span: 1.2, danger: true }));
  needle = needleOf(C, R, 9, 1.2);
  body.push(`<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" style="stroke-width:1.6" d="${needle(0.3)}"/>`);
  live = `
  const needle = ${needle.src};
  const ease = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
  window.__render = (t) => { const lv = ${TH_H - 6} - 26 * ease((t - 0.8) / 6.2);
    q("col").setAttribute("d", pathOf([iso([-23, 4.1, 10], P), iso([-23, 4.1, lv], P)]));
    q("needle").setAttribute("d", needle(0.3 + 0.62 * ease((t - 2) / 5.4))); };`;
} else if (KIND === "compass") {
  const C = [0, 0], R = 30, Hh = 8;
  body.push(dial(C, R, 0, Hh, { span: 2, count: 36, every: 9 }));
  body.push(`<path data-part="needle" class="gg-north" d=""/><path data-part="south" class="gg-south" d=""/>`);
  live = `
  const ease = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
  const tip = (a, r) => [Math.sin(a) * r, -Math.cos(a) * r];
  window.__render = (t) => { const sh = ease((t - 1.4) / 1.5), a = 0.12 * Math.sin(t * 2) + sh * (0.95 * Math.sin(t * 5.3) + 0.5 * Math.sin(t * 9.1 + 1));
    const w = 3.2, n = tip(a, ${R - 5}), s = tip(a + Math.PI, ${R - 5}), l = tip(a - Math.PI / 2, w), r = tip(a + Math.PI / 2, w), z = ${Hh} + 0.3;
    q("needle").setAttribute("d", onTop([n, l, r], z, P, true)); q("south").setAttribute("d", onTop([s, l, r], z, P, true)); };`;
} else if (KIND === "rain" || KIND === "level") {
  // 우량계: 원통 안 물기둥이 차오른다 / 수위계: 바닥판 위 물이 차올라 수위 막대의 위험 구간에 닿는다
  const rain = KIND === "rain", TH = 44;
  if (rain) {
    body.push(S(k.cylinder(0, 0, 14, 0, 3, P, 40), { tone: "lo" }));
    body.push(S(k.cylinder(0, 0, 11, 3, TH, P, 48), { tone: "mid", inner: L(k.sideArc(0, 0, 11, 13, P, 32) + k.sideArc(0, 0, 11, 23, P, 32) + k.sideArc(0, 0, 11, 33, P, 32), { tone: "faint" }) }));
    body.push(`<path data-part="water" class="gg-water" d=""/>`);
    body.push(S(k.cylinder(0, 0, 14.5, 3 + TH, 3, P, 48), { tone: "mid" }));
    body.push(L(k.ring(0, 0, 12.5, 6 + TH, P, 48), { tone: "lo" }));
  } else {
    body.push(S(k.slabOf({ x: 4, y: -4, w: 8, d: 8, r: 1 }, 0, 50, P, 2, 0.4), { tone: "hi", crease: "lo" }));
    const t = []; for (let z = 4, i = 0; z <= 48; z += 3, i++) t.push(k.pathOf([at([12, 4, z]), at([12, 4 - (i % 5 ? 2.4 : 3.8), z])]));
    body.push(L(t.join(""), { tone: "lo" }));
    body.push(`<path class="gg-danger" d="${k.pathOf([at([12.05, 0, 22]), at([12.05, 0, 34])])}"/>`);
    body.push(`<path data-part="water" class="gg-water" d=""/>`);
    // 유리 수조 윤곽(위·아래 테두리와 보이는 세 모서리)
    const B = { x: -38, y: -32, w: 76, d: 64, r: 2 };
    body.push(L(k.planOutline(B, 34, P, 2) + [[B.x + B.w, B.y + B.d], [B.x, B.y + B.d], [B.x + B.w, B.y]].map(([x, y]) => k.segment([x, y, 0], [x, y, 34], P)).join(""), { tone: "mid" }));
  }
  live = `
  const ease = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
  const rain = ${rain}, TH = ${TH};
  window.__render = (t) => {
    const f = 0.12 + 0.8 * ease((t - 0.4) / 6.8);
    const p = rain ? cylinder(0, 0, 10.8, 3, (TH - 2) * f, P, 48) : slabOf({ x: -38, y: -32, w: 76, d: 64, r: 2 }, 0, 1 + 29 * f, P, 2);
    q("water").setAttribute("d", p.fill);
  };`;
} else if (KIND === "wind" || KIND === "humid") {
  // 풍속계(바늘이 위험 쪽으로 오름) / 습도계(바늘이 건조 쪽으로 내림, 위험 구역은 왼쪽 낮은 쪽)
  const C = [0, -2], R = 30, Hh = 9, humid = KIND === "humid";
  body.push(dial(C, R, 0, Hh, { span: 1.4, danger: !humid }));
  if (humid) { const arc = []; for (let i = 0; i <= 14; i++) { const a = -0.7 * Math.PI + 1.4 * Math.PI * (0.28 * i / 14); arc.push([Math.sin(a) * (R - 5.2), -2 - Math.cos(a) * (R - 5.2)]); } body.push(`<path class="gg-danger" d="${k.onTop(arc, Hh + 0.05, P)}"/>`); }
  if (!humid) for (let i = 0; i < 3; i++) { const a = i * 2 * Math.PI / 3; body.push(S(k.cylinder(26 + 9 * Math.cos(a), 24 + 9 * Math.sin(a), 3, 0, 4, P, 16), { tone: "mid" })); }
  needle = needleOf(C, R, Hh, 1.4);
  body.push(`<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" style="stroke-width:1.8" d="${needle(humid ? 0.8 : 0.1)}"/>`);
  live = `
  const needle = ${needle.src};
  const ease = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
  const humid = ${humid};
  window.__render = (t) => { const e = ease((t - 0.5) / 6.5), j = 0.02 * Math.sin(t * (humid ? 3 : 11));
    q("needle").setAttribute("d", needle(humid ? 0.8 - 0.68 * e + j : 0.1 + 0.8 * e + j)); };`;
} else {   // pressure
  const C = [0, -2], R = 30, Hh = 9;
  body.push(dial(C, R, 0, Hh, { span: 1.4, danger: true }));
  needle = needleOf(C, R, Hh, 1.4);
  body.push(`<path data-part="needle" class="iso-line" data-tone="lit" data-free="start" style="stroke-width:1.8" d="${needle(0.05)}"/>`);
  live = `
  const needle = ${needle.src};
  const ease = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };
  window.__render = (t) => q("needle").setAttribute("d", needle(0.05 + 0.85 * ease((t - 0.5) / 6.5) + 0.015 * Math.sin(t * 13)));`;
}

const svg = k.figureSvg({ width: W, height: H, className: "gg", label: "계기판", body });
const CSS = `<style>
.gg-trace{fill:none;stroke:#dc2626;stroke-width:1.1;stroke-linejoin:round}
.gg-col{stroke:#dc2626;stroke-width:3;stroke-linecap:round;fill:none}
.gg-danger{stroke:#dc2626;stroke-width:2.4;fill:none}
.gg-north{fill:#dc2626;stroke:#991b1b;stroke-width:.5}
.gg-water{fill:#3b82c4;fill-opacity:.55;stroke:#1d4ed8;stroke-width:.6}
.gg-south{fill:var(--anatomy-shade-1);stroke:var(--anatomy-mid);stroke-width:.5}
</style>`;
const page = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>${k.ISO_CSS}
html,body{margin:0;width:400px;height:400px;overflow:hidden;background:var(--anatomy-card)}
.iso-stage{width:400px!important;height:400px!important;box-sizing:border-box;border:6px solid #1f2937;border-radius:0;padding:0!important;margin:0!important}
.iso-stage svg{display:block;width:388px!important;height:388px!important;max-width:none!important}</style></head>
<body class="iso" data-theme="light">${CSS}<div class="iso-stage">${svg}</div>
<script type="module">${(kitScript() + `const P = ${JSON.stringify(P)}; const svgEl = document.querySelector("svg"), q = (n) => svgEl.querySelector('[data-part="' + n + '"]');` + live + "\nwindow.__render(0);").replace(/<\/(script)/gi, "<\\/$1")}</script></body></html>`;
writeFileSync(join(HERE, `gauge-${KIND}.html`), page);
console.log("wrote", KIND);
