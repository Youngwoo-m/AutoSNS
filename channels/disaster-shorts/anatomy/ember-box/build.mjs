// 바람·습도 실험 상자 — 산불편 견본(anatomy 스킬, Figure 크기, SVG 만).
// 바람이 셀수록 불씨가 멀리 날고, 습도가 낮을수록 떨어진 불씨가 낙엽에 옮겨붙는다.
// 근거: 국민안전24 산불 국민행동요령 "날씨가 건조하며 바람이 많이 부는 날은 매우 위험합니다".
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import * as k from "/Users/youngwoo/.claude/skills/anatomy/kit/iso-kit.mjs";
import { kitScript } from "/Users/youngwoo/.claude/skills/anatomy/scripts/inline-kit.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const theme = process.argv.includes("--light") ? "light" : "dark";
const PORTRAIT = process.argv.includes("--portrait");   // 숏츠용 세로(9:16) 영상 페이지
const WIDTH = PORTRAIT ? 450 : 600, HEIGHT = PORTRAIT ? 800 : 380;
// 세로 영상: 위쪽 시리즈 띠·꼬리표(~400/1920)와 아래 자막(~1250/1920 아래)을 피해 그림을 가운데 띠에 둔다
const BAND = PORTRAIT ? { top: 160, height: 370 } : { top: 0, height: HEIGHT };

// ---- 모델(장면과 숫자가 같은 식을 쓴다) ----
const M = 8;                 // 1 m = 8 단위
const AIR_TIME = 2.0;        // 불씨가 공중에 머무는 시간(단순 모형)
const TEMP = 15;             // 기온 15℃ 가정

// ---- 배치 ----
const PLATE = { x: -160, y: -62, w: 330, d: 124, r: 8 };
const PLATE_H = 12, FOOT_H = 5;
const CH = { x: -116, w: 266 };                       // 실험 통로
const FLOOR_TOP = 4, WALL_TOP = 34, FRONT_TOP = 12;
const TRAY = { x: -66, y: -27, w: 208, d: 42, r: 2 };
const TRAY_TOP = 6.5;
const BRAZ = [-80, -6], COAL_Z = 20.4;
const FAN = { x: -152, y: -38, w: 36, d: 62, r: 3 }, FAN_TOP = 44, FAN_C = [-116, -6, 22];
const FAN_KNOB = [-134, -6];
const HUM = [-138, 44], HUM_KNOB_Z = 28;
const CONSOLE = { x: 96, y: 28, w: 64, d: 28, r: 3 }, CONSOLE_TOP = 12, DIAL_R = 10, DIAL_TOP = 15;
const WIND_DIAL = [114, 42], HUM_DIAL = [142, 42];
const SWEEP_FROM = -0.75 * Math.PI, SWEEP = 1.5 * Math.PI;

const P = k.fitProjection(
  [...k.boxCorners(PLATE, -PLATE_H - FOOT_H, 0), [CH.x, -36, WALL_TOP + 2], [CH.x + CH.w, -36, WALL_TOP + 2], [FAN.x, FAN.y, FAN_TOP + 5]],
  WIDTH, BAND.height, PORTRAIT ? { pad: 6, azimuth: +(process.env.AZ || 34), elevation: +(process.env.EL || 42) } : { pad: 30, azimuth: 58, elevation: 32 },
);
if (PORTRAIT) P.origin = [P.origin[0], P.origin[1] + BAND.top];
const at = (p) => k.iso(p, P);
const S = (paths, style) => k.solidSvg(paths, style);
const L = (d, style) => k.lineSvg(d, style);
const D = (points, style) => k.dotsSvg(points, style);
const byDepth = (pts) => [...pts].sort((a, b) => k.depthOf([a[0], a[1], 0], P) - k.depthOf([b[0], b[1], 0], P));
const faceX = (x, pts) => k.pathOf(pts.map(([y, z]) => at([x, y, z])), true);
const faceY = (y, pts) => k.pathOf(pts.map(([x, z]) => at([x, y, z])), true);

// 결정적인 난수(빌드마다 같은 그림)
let seed = 7;
const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

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

function fan() {
  const out = [];
  const flange = { x: -156, y: -42, w: 40, d: 70, r: 2 };
  out.push(S(k.slabOf(flange, 0, 3, P, 3, 0.5), { tone: "lo" }));
  out.push(D(k.corners(flange, 3).map(([x, y]) => at([x, y, 3])), { size: 0.45 }));
  out.push(S(k.slabOf(FAN, 3, FAN_TOP - 3, P, 3, 0.8), { tone: "mid", inner: L(k.sideSeam(FAN, 10, P, 3), { tone: "faint" }) }));
  // 앞면(y = 24) 통풍 슬롯 — 닫힌 윤곽
  const yf = FAN.y + FAN.d;
  for (const x of [-147, -141, -135, -129, -123]) out.push(L(faceY(yf, [[x - 1.2, 16], [x + 1.2, 16], [x + 1.2, 36], [x - 1.2, 36]]), { tone: "lo" }));
  // 위: 이름판(규칙선 3줄) + 풍속 손잡이
  const tag = { x: -149, y: -34, w: 12, d: 18, r: 1 };
  out.push(S(k.slabOf(tag, FAN_TOP, 0.6, P, 3), { tone: "lo", crease: "none" }));
  out.push(L(k.planOutline(k.insetPlan(tag, 1.4), FAN_TOP + 0.6, P, 3), { tone: "faint" }));
  [[-29, 12], [-25, 9], [-21, 10]].forEach(([y, len]) =>
    out.push(L(k.lineOnTop([-145, y], [-145 + Math.min(len, 5), y], FAN_TOP + 0.6, P), { tone: "lo", free: true })));
  out.push(S(k.cylinder(FAN_KNOB[0], FAN_KNOB[1], 7.5, FAN_TOP, 1.2, P, 32), { tone: "lo" }));
  out.push(L(k.radialTicks(FAN_KNOB[0], FAN_KNOB[1], 7.3, 10, 5, FAN_TOP + 1.2, [1.0, 1.8], P, SWEEP_FROM, SWEEP).minor +
    k.radialTicks(FAN_KNOB[0], FAN_KNOB[1], 7.3, 10, 5, FAN_TOP + 1.2, [1.0, 1.8], P, SWEEP_FROM, SWEEP).major, { tone: "lo" }));
  out.push(S(k.cylinder(FAN_KNOB[0], FAN_KNOB[1], 5, FAN_TOP + 1.2, 4, P, 32), { tone: "mid" }));
  out.push(L(k.knurl(FAN_KNOB[0], FAN_KNOB[1], 5, FAN_TOP + 1.2, FAN_TOP + 5.2, 30, P), { tone: "lo" }));
  // 송풍구(x = −116 면): 테두리·보호망 링·허브
  const [fx, fy, fz] = FAN_C;
  out.push(L(k.sideRing([fx + 0.1, fy, fz], 16, "x", P, 64), { tone: "mid" }));
  out.push(L(k.sideRing([fx + 0.1, fy, fz], 12.5, "x", P, 56), { tone: "lo" }));
  out.push(L(k.sideRing([fx + 0.1, fy, fz], 8, "x", P, 40), { tone: "faint" }));
  out.push(L(k.sideRing([fx + 0.1, fy, fz], 3.2, "x", P, 24), { tone: "mid" }));
  out.push(D([[fy - 14.5, fz + 14.5], [fy + 14.5, fz + 14.5], [fy - 14.5, fz - 14.5], [fy + 14.5, fz - 14.5]].map(([y, z]) => at([fx + 0.1, y, z])), { size: 0.45 }));
  return out.join("");
}

const blades = (phase) => [0, 1, 2].map((i) => {
  const a = phase + (i * 2 * Math.PI) / 3;
  const [fx, fy, fz] = FAN_C;
  const pt = (r, t) => [fx + 0.1, fy + r * Math.cos(t), fz + r * Math.sin(t)];
  return k.pathOf([pt(3.3, a - 0.32), pt(7, a - 0.12), pt(12.1, a + 0.12), pt(12.1, a + 0.62), pt(7, a + 0.5), pt(3.3, a + 0.38)].map((q) => k.iso(q, P)), true);
}).join("");

function channel() {
  const out = [];
  out.push(S(k.slabOf({ x: CH.x, y: -34, w: CH.w, d: 56, r: 1 }, 0, FLOOR_TOP, P, 3, 0.5), { tone: "mid" }));
  // 뒷벽 + 안쪽 판 이음선 + 위 테두리
  out.push(S(k.slabOf({ x: CH.x, y: -34, w: CH.w, d: 4, r: 0.6 }, FLOOR_TOP, WALL_TOP - FLOOR_TOP, P, 2, 0.4), { tone: "mid" }));
  out.push(L([-66, -16, 34, 84, 134].map((x) => k.segment([x, -30, FLOOR_TOP], [x, -30, WALL_TOP], P)).join(""), { tone: "faint" }));
  const lip = { x: CH.x, y: -36, w: CH.w, d: 8, r: 1 };
  out.push(S(k.slabOf(lip, WALL_TOP, 2, P, 2, 0.4), { tone: "mid" }));
  out.push(D([-96, -56, -16, 24, 64, 104, 140].map((x) => at([x, -32, WALL_TOP + 2])), { size: 0.45 }));
  return out.join("");
}

function tray() {
  const out = [];
  out.push(S(k.slabOf(TRAY, FLOOR_TOP, TRAY_TOP - FLOOR_TOP, P, 3, 0.5), { tone: "hi", crease: "lo" }));
  const leaves = [];
  for (let i = 0; i < 90; i++) {
    const cx = TRAY.x + 4 + rnd() * (TRAY.w - 8), cy = TRAY.y + 4 + rnd() * (TRAY.d - 8);
    const ang = rnd() * Math.PI, a = 1.6 + rnd() * 1.4, b = a * (0.35 + rnd() * 0.2);
    const pts = [];
    for (let s = 0; s < 10; s++) {
      const t = (s / 10) * Math.PI * 2, u = a * Math.cos(t), v = b * Math.sin(t);
      pts.push([cx + u * Math.cos(ang) - v * Math.sin(ang), cy + u * Math.sin(ang) + v * Math.cos(ang)]);
    }
    leaves.push({ d: k.onTop(pts, TRAY_TOP, P, true), tone: i % 3 ? "faint" : "lo" });
  }
  out.push(L(leaves.filter((l) => l.tone === "faint").map((l) => l.d).join(""), { tone: "faint" }));
  out.push(L(leaves.filter((l) => l.tone === "lo").map((l) => l.d).join(""), { tone: "lo" }));
  return out.join("");
}

function brazier() {
  const out = [];
  const [x, y] = BRAZ;
  out.push(S(k.cylinder(x, y, 10, FLOOR_TOP, 1.4, P, 40), { tone: "lo" }));
  out.push(S(k.cylinder(x, y, 8, FLOOR_TOP + 1.4, 13.6, P, 40), {
    tone: "mid", inner: L(k.sideArc(x, y, 8, 9, P, 24) + k.sideArc(x, y, 8, 15, P, 24), { tone: "faint" }),
  }));
  out.push(S(k.slabOf({ x: x + 7.4, y: y - 2, w: 3, d: 4, r: 0.8 }, 13, 2.4, P, 2), { tone: "mid", crease: "none" }));
  out.push(S(k.cylinder(x, y, 8.8, 19, 1.4, P, 40), { tone: "mid" }));
  out.push(L(k.ring(x, y, 7, COAL_Z, P, 32), { tone: "lo" }));
  out.push(L(k.lineOnTop([x - 7, y], [x + 7, y], COAL_Z, P) + k.lineOnTop([x, y - 7], [x, y + 7], COAL_Z, P), { tone: "faint" }));
  const coals = [];
  for (let i = 0; i < 14; i++) {
    const r = 5.5 * Math.sqrt(rnd()), a = rnd() * Math.PI * 2;
    coals.push(at([x + r * Math.cos(a), y + r * Math.sin(a), COAL_Z]));
  }
  out.push(`<g class="eb-coals">${coals.map(([cx, cy]) => `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="0.9"/>`).join("")}</g>`);
  return out.join("");
}

function outlet() {
  const out = [];
  out.push(S(k.slabOf({ x: 146, y: -30, w: 4, d: 48, r: 0.4 }, FLOOR_TOP, WALL_TOP - FLOOR_TOP, P, 2, 0.4), { tone: "mid" }));
  const lines = [];
  for (let y = -26; y <= 14; y += 3.2) lines.push(k.segment([150, y, FLOOR_TOP], [150, y, WALL_TOP], P));
  out.push(L(lines.join(""), { tone: "faint" }));
  return out.join("");
}

function frontWall() {
  const out = [];
  const wall = { x: CH.x, y: 18, w: CH.w, d: 4, r: 0.6 };
  out.push(S(k.slabOf(wall, FLOOR_TOP, FRONT_TOP - FLOOR_TOP, P, 2, 0.4), { tone: "mid" }));
  out.push(D([-100, -60, -20, 20, 60, 100, 140].map((x) => at([x, 20, FRONT_TOP])), { size: 0.45 }));
  return out.join("");
}

function humidifier() {
  const out = [];
  const [x, y] = HUM;
  out.push(S(k.slabOf({ x: x - 4, y: 24, w: 8, d: 12, r: 1 }, 16, 4, P, 2, 0.3), { tone: "mid" }));
  out.push(S(k.cylinder(x, y, 10, 0, 2, P, 40), { tone: "lo" }));
  out.push(S(k.cylinder(x, y, 9, 2, 24, P, 40), {
    tone: "mid", inner: L(k.sideArc(x, y, 9, 8, P, 24) + k.sideArc(x, y, 9, 20, P, 24), { tone: "faint" }),
  }));
  out.push(S(k.cylinder(x, y, 6, 26, 2, P, 32), { tone: "mid" }));
  out.push(L(k.radialTicks(x, y, 5.8, 10, 5, HUM_KNOB_Z, [0.9, 1.6], P, SWEEP_FROM, SWEEP).major + k.radialTicks(x, y, 5.8, 10, 5, HUM_KNOB_Z, [0.9, 1.6], P, SWEEP_FROM, SWEEP).minor, { tone: "lo" }));
  out.push(S(k.cylinder(x, y, 3.6, HUM_KNOB_Z, 4, P, 28), { tone: "mid" }));
  out.push(L(k.knurl(x, y, 3.6, HUM_KNOB_Z, HUM_KNOB_Z + 4, 22, P), { tone: "lo" }));
  return out.join("");
}

function frontParts() {
  const out = [];
  // 거리 눈금자(0 = 불씨 통, 1 m 마다, 5 m 마다 굵게)
  const strip = { x: BRAZ[0] - 4, y: 30, w: 20 * M + 8, d: 7, r: 1 };
  out.push(S(k.slabOf(strip, 0, 0.6, P, 3), { tone: "lo", crease: "none" }));
  const t = k.topTicks(BRAZ[0], BRAZ[0] + 20 * M, M, 5, strip.y, 0.6, [2.2, 4], P);
  out.push(L(t.minor, { tone: "lo" }), L(t.major, { tone: "mid" }));
  out.push(D([at([strip.x + 2, strip.y + 5, 0.6]), at([strip.x + strip.w - 2, strip.y + 5, 0.6])], { size: 0.45 }));
  // 이름판
  const tag = { x: -120, y: 30, w: 30, d: 14, r: 1.2 };
  out.push(S(k.slabOf(tag, 0, 0.8, P, 3), { tone: "lo", crease: "none" }));
  out.push(L(k.planOutline(k.insetPlan(tag, 1.6), 0.8, P, 3), { tone: "faint" }));
  [[34.5, 18], [38, 13], [41.5, 15]].forEach(([y, len]) => out.push(L(k.lineOnTop([-116, y], [-116 + len, y], 0.8, P), { tone: "lo", free: true })));
  out.push(D([at([tag.x + 2.4, tag.y + 2.4, 0.8]), at([tag.x + tag.w - 2.4, tag.y + tag.d - 2.4, 0.8])], { size: 0.45 }));
  return out.join("");
}

function consoleParts() {
  const out = [];
  out.push(S(k.slabOf(CONSOLE, 0, CONSOLE_TOP, P, 4, 0.8), { tone: "mid", inner: L(k.sideSeam(CONSOLE, 3, P, 4), { tone: "faint" }) }));
  out.push(D(k.corners(CONSOLE, 3).map(([x, y]) => at([x, y, CONSOLE_TOP])), { size: 0.45 }));
  for (const [x, y] of [WIND_DIAL, HUM_DIAL]) {
    out.push(S(k.cylinder(x, y, DIAL_R, CONSOLE_TOP, DIAL_TOP - CONSOLE_TOP, P, 56, 0.6), { tone: "hi", crease: "lo" }));
    out.push(L(k.ring(x, y, DIAL_R - 1.4, DIAL_TOP, P, 56), { tone: "lo" }));
    const tk = k.radialTicks(x, y, DIAL_R - 1.6, 20, 2, DIAL_TOP, [1.0, 2.1], P, SWEEP_FROM, SWEEP);
    out.push(L(tk.minor, { tone: "lo" }), L(tk.major, { tone: "mid" }));
    out.push(L(k.ring(x, y, 1.2, DIAL_TOP, P, 16), { tone: "mid" }));
  }
  return out.join("");
}

// 바늘·손잡이 지시선(라이브 코드와 같은 식)
const dirAt = (share) => SWEEP_FROM + SWEEP * Math.min(1, Math.max(0, share));
const needle = (c, share, r = DIAL_R - 3) => { const a = dirAt(share); return k.lineOnTop([c[0] - Math.sin(a) * 2, c[1] + Math.cos(a) * 2], [c[0] + Math.sin(a) * r, c[1] - Math.cos(a) * r], DIAL_TOP + 0.2, P); };
const pointer = (c, z, r, share) => { const a = dirAt(share); return k.lineOnTop([c[0], c[1]], [c[0] + Math.sin(a) * r, c[1] - Math.cos(a) * r], z, P); };

const START = { wind: 2, hum: 80 };
const svg = k.figureSvg({
  width: WIDTH, height: HEIGHT, className: "eb",
  label: "바람·습도 실험 상자. 왼쪽 송풍기가 통로로 바람을 보내고, 가운데 불씨 통에서 불씨가 날아 낙엽 판 위에 떨어진다. 앞의 가습기로 습도를 바꾸고, 계기판의 두 바늘이 풍속과 습도를 보여 준다. 바람이 셀수록 불씨가 멀리 날고, 건조할수록 떨어진 불씨가 낙엽에 옮겨붙는다.",
  body: [
    plate(), fan(),
    `<path data-part="blades" class="eb-blades" d="${blades(0)}"/>`,
    `<path data-part="fan-pointer" class="iso-line" data-tone="hi" data-free="end" d="${pointer(FAN_KNOB, FAN_TOP + 5.2, 4.2, START.wind / 10)}" style="stroke-width:0.9"/>`,
    channel(), tray(), brazier(),
    `<g data-part="spots" class="eb-spots"></g>`,
    `<g data-part="embers" class="eb-embers"></g>`,
    outlet(), frontWall(), humidifier(),
    `<path data-part="hum-pointer" class="iso-line" data-tone="hi" data-free="end" d="${pointer(HUM, HUM_KNOB_Z + 4, 3, (START.hum - 20) / 70)}" style="stroke-width:0.9"/>`,
    frontParts(), consoleParts(),
    `<path data-part="wind-needle" class="iso-line" data-tone="lit" data-free="start" d="${needle(WIND_DIAL, START.wind / 10)}" style="stroke-width:1.1"/>`,
    `<path data-part="hum-needle" class="iso-line" data-tone="hi" data-free="start" d="${needle(HUM_DIAL, START.hum / 100)}" style="stroke-width:1.1"/>`,
  ],
});

const CSS = `<style>
.iso .eb{--ember:#c2410c;--ember-core:#ea580c}
.iso[data-theme="dark"] .eb{--ember:#ff8a3d;--ember-core:#ffd28a}
.eb-coals circle{fill:var(--ember);opacity:.9}
.eb-embers circle{fill:var(--ember-core);stroke:var(--ember);stroke-width:.5}
.eb-spots path{fill:var(--ember);stroke:none}\n.eb-blades{fill:var(--anatomy-shade-1);stroke:var(--anatomy-mid);stroke-width:.6;stroke-linejoin:round}
</style>`;

const live = `
const P = ${JSON.stringify(P)};
const M = ${M}, AIR = ${AIR_TIME}, TEMP = ${TEMP};
const BRAZ = ${JSON.stringify(BRAZ)}, COAL_Z = ${COAL_Z}, TRAY = ${JSON.stringify(TRAY)}, TRAY_TOP = ${TRAY_TOP}, FLOOR_TOP = ${FLOOR_TOP};
const FAN_C = ${JSON.stringify(FAN_C)}, FAN_KNOB = ${JSON.stringify(FAN_KNOB)}, FAN_TOP = ${FAN_TOP}, HUM = ${JSON.stringify(HUM)}, HUM_KNOB_Z = ${HUM_KNOB_Z};
const WIND_DIAL = ${JSON.stringify(WIND_DIAL)}, HUM_DIAL = ${JSON.stringify(HUM_DIAL)}, DIAL_R = ${DIAL_R}, DIAL_TOP = ${DIAL_TOP};
const SWEEP_FROM = ${SWEEP_FROM}, SWEEP = ${SWEEP};
const dirAt = ${dirAt.toString()};
const needle = ${needle.toString().replace(/k\.lineOnTop/g, "lineOnTop")};
const pointer = ${pointer.toString().replace(/k\.lineOnTop/g, "lineOnTop")};
const blades = ${blades.toString().replace(/k\.pathOf/g, "pathOf").replace(/k\.iso/g, "iso")};
// 가는 낙엽의 평형 함수율(Simard 1968), 기온 ℃·습도 %
function emc(h, t) {
  if (h < 10) return 0.03229 + 0.281073 * h - 0.000578 * h * t;
  if (h < 50) return 2.22749 + 0.160107 * h - 0.01478 * t;
  return 21.0606 + 0.005565 * h * h - 0.00035 * h * t - 0.483199 * h;
}
const catchOf = (h) => Math.min(0.92, Math.max(0.02, (20 - emc(h, TEMP)) / 16));   // 함수율 4%→거의 다 붙고, 20% 넘으면 거의 안 붙는 근사
const riskOf = (p) => p >= 0.75 ? "매우 높음" : p >= 0.5 ? "높음" : p >= 0.25 ? "보통" : "낮음";
const stage = document.querySelector(".iso-stage"), svg = stage.querySelector("svg");
const q = (n) => svg.querySelector('[data-part="' + n + '"]');
const el = { blades: q("blades"), fp: q("fan-pointer"), hp: q("hum-pointer"), wn: q("wind-needle"), hn: q("hum-needle"), spots: q("spots"), embers: q("embers") };
const coals = svg.querySelector(".eb-coals");
const readout = document.querySelector("[data-readout]");
const still = matchMedia("(prefers-reduced-motion: reduce)");
const NS = "http://www.w3.org/2000/svg";
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const TOUR = [[2, 80], [5, 60], [8, 35], [9, 25], [4, 30]];
let wind = TOUR[0][0], hum = TOUR[0][1], tw = wind, th = hum;
let touring = true, clock = 0, phase = 0, spawn = 0, idle = 0, frame = 0, last = 0, visible = false, t = 0;
let seed = 11; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
const embers = [], spots = [];
function surfaceAt(x, y) { return x > TRAY.x && x < TRAY.x + TRAY.w && y > TRAY.y && y < TRAY.y + TRAY.d ? TRAY_TOP : FLOOR_TOP; }
function launch() {
  const node = document.createElementNS(NS, "circle"); node.setAttribute("r", "1.05"); el.embers.appendChild(node);
  const a = rnd() * Math.PI * 2, r = 4 * Math.sqrt(rnd());
  const x0 = BRAZ[0] + r * Math.cos(a), y0 = BRAZ[1] + r * Math.sin(a);
  const dist = wind * AIR * M * (0.75 + rnd() * 0.4);
  const y1 = clamp(y0 + (rnd() - 0.5) * 30, -28, 16);
  const x1 = x0 + dist, z1 = dist < 9 ? COAL_Z : surfaceAt(x1, y1);
  embers.push({ node, x0, y0, x1, y1, z1, apex: 9 + wind * 1.4 + rnd() * 4, age: 0, home: dist < 9 });
}
function land(e) {
  if (e.home) return;
  const onTray = e.z1 === TRAY_TOP, lit = onTray && rnd() < catchOf(hum);
  const node = document.createElementNS(NS, "path"); el.spots.appendChild(node);
  spots.push({ node, x: e.x1, y: e.y1, z: e.z1, lit, age: 0 });
}
function drawSpots(dt) {
  for (let i = spots.length - 1; i >= 0; i--) {
    const s = spots[i]; s.age += dt;
    const life = s.lit ? 5 : 0.8;
    if (s.age > life) { s.node.remove(); spots.splice(i, 1); continue; }
    const grow = s.lit ? 0.7 + 3.3 * (1 - Math.exp(-s.age / 0.9)) : 0.8;
    const fade = s.lit ? (s.age < 3 ? 0.85 : 0.85 * (1 - (s.age - 3) / 2)) : 0.8 * (1 - s.age / life);
    s.node.setAttribute("d", ring(s.x, s.y, grow, s.z + 0.05, P, 18));
    s.node.setAttribute("opacity", fade.toFixed(3));
  }
}
function drawEmbers(dt) {
  for (let i = embers.length - 1; i >= 0; i--) {
    const e = embers[i]; e.age += dt;
    const s = e.age / AIR;
    if (s >= 1) { land(e); e.node.remove(); embers.splice(i, 1); continue; }
    const x = e.x0 + (e.x1 - e.x0) * s, y = e.y0 + (e.y1 - e.y0) * s, z = COAL_Z + e.apex * 4 * s * (1 - s) + (e.z1 - COAL_Z) * s;
    const [sx, sy] = iso([x, y, z], P);
    e.node.setAttribute("cx", sx.toFixed(1)); e.node.setAttribute("cy", sy.toFixed(1));
    e.node.setAttribute("opacity", (s < 0.1 ? s / 0.1 : 1).toFixed(2));
  }
}
function drawGauges() {
  el.blades.setAttribute("d", blades(phase));
  el.fp.setAttribute("d", pointer(FAN_KNOB, FAN_TOP + 5.2, 4.2, wind / 10));
  el.hp.setAttribute("d", pointer(HUM, HUM_KNOB_Z + 4, 3, (hum - 20) / 70));
  el.wn.setAttribute("d", needle(WIND_DIAL, wind / 10));
  el.hn.setAttribute("d", needle(HUM_DIAL, hum / 100));
  const text = "풍속 " + tw.toFixed(0) + " m/s · 습도 " + th.toFixed(0) + "% · 불씨 약 " + (tw * AIR).toFixed(0) + " m · 낙엽 착화 " + riskOf(catchOf(th));
  if (readout.textContent !== text) readout.textContent = text;
  stage.setAttribute("aria-valuetext", text);
}
// 영상: 0~1초 약풍·습함 → 3초까지 강풍·건조로 → 6.3초까지 유지 → 8초에 처음 상태로(루프)
const videoTarget = (tt) => tt < 1 || tt >= 6.3 ? [2, 80] : [9, 25];
function step(dt) {
  t += dt;
  if (window.__video) { const st = videoTarget(t - 2); tw = st[0]; th = st[1]; }   // 앞의 2초는 미리 돌리기
  else if (touring) { clock += dt; const st = TOUR[Math.floor(clock / 4.5) % TOUR.length]; tw = st[0]; th = st[1]; }
  wind += (tw - wind) * (1 - Math.exp(-dt / 0.6)); hum += (th - hum) * (1 - Math.exp(-dt / 0.8));
  phase += dt * wind * 2.4;
  spawn += dt; if (spawn > 0.22) { spawn = 0; if (embers.length < 40) launch(); }
  coals.setAttribute("opacity", (0.75 + 0.25 * Math.sin(t * 7.3) * Math.sin(t * 2.1)).toFixed(2));
  drawEmbers(dt); drawSpots(dt); drawGauges();
}
function tick(now) {
  const dt = last ? Math.min((now - last) / 1000, 1 / 30) : 1 / 60; last = now;
  step(dt);
  frame = visible ? requestAnimationFrame(tick) : 0;
}
// 정해진 시계로 한 장씩 그리기(영상 녹화용): 2초 앞서 돌려 불씨가 이미 날고 있게 한다
window.__render = (tt) => { while (t < tt + 2 - 1e-9) step(1 / 120); };
function stillFrame() {   // 움직임 줄이기: 불씨 경로 위 몇 점과 내려앉은 자리만 그린다
  el.embers.replaceChildren(); el.spots.replaceChildren(); embers.length = 0; spots.length = 0;
  wind = tw; hum = th;
  for (let i = 0; i < 7; i++) { launch(); embers[embers.length - 1].age = AIR * (0.12 + i * 0.12); }
  drawEmbers(0);
  for (let i = 0; i < 5; i++) { launch(); const e = embers.pop(); e.node.remove(); land(e); spots[spots.length - 1].age = 1.2; }
  drawSpots(0); drawGauges();
}
const run = () => { if (still.matches) { stillFrame(); return; } if (!frame && visible) { last = 0; frame = requestAnimationFrame(tick); } };
const steer = (w, h) => { touring = false; tw = clamp(Math.round(w), 0, 10); th = clamp(Math.round(h / 5) * 5, 20, 90); clearTimeout(idle); idle = setTimeout(() => { touring = !still.matches; clock = 0; run(); }, 3600); run(); };
if (!window.__video) new IntersectionObserver((en) => { visible = en[en.length - 1].isIntersecting; if (visible) run(); }, { rootMargin: "120px 0px" }).observe(stage);
stage.addEventListener("pointermove", (ev) => {
  const b = svg.getBoundingClientRect();
  steer(clamp(((ev.clientX - b.left) / b.width - 0.15) / 0.7, 0, 1) * 10, 90 - clamp(((ev.clientY - b.top) / b.height - 0.15) / 0.7, 0, 1) * 70);
});
stage.addEventListener("keydown", (ev) => {
  const m = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowUp: [0, 10], ArrowDown: [0, -10] }[ev.key];
  if (!m) return; ev.preventDefault(); steer(tw + m[0], th + m[1]);
});
if (still.matches) touring = false;
drawGauges();
`;

const body = CSS + k.plateHtml({
  fig: "Fig 1",
  title: "바람·습도 실험 상자",
  hint: "가로: 바람 세기 · 세로: 습도",
  readout: `풍속 ${START.wind} m/s · 습도 ${START.hum}% · 불씨 약 ${START.wind * AIR_TIME} m · 낙엽 착화 낮음`,
  keys: [
    { mark: "lit", label: "풍속계 바늘: 송풍기 손잡이로 바꾼 바람 세기" },
    { mark: "raised", label: "낙엽 판: 불씨가 떨어지는 곳, 눈금자는 불씨 통에서 1 m 간격" },
  ],
  caption: "건조하고 바람이 많이 부는 날 소각이 왜 위험한지 보여 주는 단순 모형입니다. 불씨가 공중에 2초 머문다고 보고 날아가는 거리를 풍속 × 2초로, 떨어진 불씨가 붙는 정도를 습도에 따른 낙엽 함수율(Simard 식, 기온 15℃)로 계산합니다. 근거: 행정안전부 국민안전24 산불 국민행동요령.",
  body: `<div class="iso-stage" tabindex="0" role="slider" aria-label="바람·습도 실험 상자: 좌우 화살표는 바람, 위아래 화살표는 습도" aria-valuemin="0" aria-valuemax="10" aria-valuenow="2">${svg}</div>`,
});

if (PORTRAIT) {
  // 영상 페이지: 카드 없이 1080×1920 종이 위에 그림만. readout 은 숨김
  const page = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>${k.ISO_CSS}
html,body{margin:0;width:1080px;height:1920px;overflow:hidden;background:var(--anatomy-card)}
.iso-stage,.iso-stage svg{display:block;width:1080px;height:1920px}[data-readout]{display:none}</style></head>
<body class="iso" data-theme="${theme}">${CSS}<div class="iso-stage">${svg}</div><span data-readout></span>
<script>window.__video = 1;</script><script type="module">${(kitScript() + live).replace(/<\/(script)/gi, "<\\/$1")}</script></body></html>`;
  writeFileSync(join(HERE, "ember-box-video.html"), page);
  console.log("wrote ember-box-video.html");
} else {
  const name = theme === "light" ? "ember-box-light.html" : "ember-box.html";
  writeFileSync(join(HERE, name), k.pageHtml({ title: "바람·습도 실험 상자", theme, body, script: kitScript() + live }));
  console.log("wrote", name);
}
