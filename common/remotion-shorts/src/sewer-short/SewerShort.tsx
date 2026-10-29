import React from "react";
import { loadFont } from "@remotion/fonts";
import {
  AbsoluteFill, Audio, Easing, Img, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig,
} from "remotion";

// 글꼴은 Pretendard Bold 하나(CLAUDE.md) — 크기와 색으로 위계를 준다.
loadFont({ family: "SewerPretendard", url: staticFile("Pretendard-Bold.otf"), weight: "700" });

type Cam = { from: [number, number, number, number]; to: [number, number, number, number] }; // [scale, x%, y%, rotateDeg]
export type SewerScene = {
  image: string; seconds: number; tag: string; title: string; caption: string; mode: "scan" | "risk" | "safe"; cam: Cam;
};
export type SewerShortProps = { voice?: string; org: string; disclosure: string; scenes: SewerScene[] };

export const DEFAULT_PROPS: SewerShortProps = {
  voice: "voice.wav", org: "세명대학교 재난안전학과",
  disclosure: "AI 생성 그림 · AI 합성 음성(TTS) · 학습용 시각화",
  scenes: [
    { image: "d1.png", seconds: 3.6, tag: "1 지하 조사", title: "땅속 하수관,\n로봇이 먼저 봅니다", caption: "땅속 하수관을 로봇이 조사하고", mode: "scan",
      cam: { from: [1.0, 0, 6, -1.5], to: [1.32, 3, -6, 1.5] } },
    { image: "d2.png", seconds: 3.6, tag: "2 AI 예측", title: "인공지능이\n위험도를 예측", caption: "인공지능이 싱크홀 위험도를 예측합니다.", mode: "risk",
      cam: { from: [1.25, -3, 5, 2], to: [1.0, 2, -2, -1.5] } },
    { image: "d3.png", seconds: 3.8, tag: "3 예방 보수", title: "미리 고치면\n안전해집니다", caption: "위험 구간은 미리 보수해 안전하게 바꿉니다.", mode: "safe",
      cam: { from: [1.0, 3, -2, 1.5], to: [1.18, -2, 3, -1] } },
  ],
};
export const totalFrames = (p: SewerShortProps) => p.scenes.reduce((a, s) => a + Math.round(s.seconds * 30), 0);

const C = { bg: "#071522", teal: "#5eead4", blue: "#8fd3ff", title: "#ffffff", sub: "#9fb6c6", green: "#4ade80", yellow: "#facc15", red: "#f87171" };
const ease = Easing.bezier(0.16, 1, 0.3, 1);
const XFADE = 9; // 장면 사이 겹침(프레임) — 교차 디졸브

const Overlay: React.FC<{ mode: SewerScene["mode"] }> = ({ mode }) => {
  const f = useCurrentFrame();
  if (mode === "scan") {
    const y = interpolate(f % 60, [0, 60], [900, 1500]);
    return (
      <>
        <div style={{ position: "absolute", left: 0, right: 0, top: y, height: 6, background: C.teal, opacity: 0.8, boxShadow: `0 0 40px 12px ${C.teal}88` }} />
        {[0, 1, 2].map((i) => {
          const p = ((f + i * 20) % 60) / 60;
          return <div key={i} style={{ position: "absolute", left: 640 - 150 * p, top: 1180 - 150 * p, width: 300 * p, height: 300 * p, borderRadius: "50%", border: `4px solid ${C.teal}`, opacity: 1 - p }} />;
        })}
      </>
    );
  }
  if (mode === "risk") {
    const lg = [["정상", C.green], ["주의", C.yellow], ["고위험", C.red]] as const;
    return (
      <div style={{ position: "absolute", left: 70, top: 1080, display: "flex", flexDirection: "column", gap: 14 }}>
        {lg.map(([t, c], i) => (
          <div key={t} style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 40, color: C.title, background: "#071522cc", padding: "10px 26px", borderRadius: 40,
            opacity: interpolate(f, [18 + i * 10, 30 + i * 10], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
            <span style={{ width: 28, height: 28, borderRadius: 14, background: c, boxShadow: `0 0 ${14 + 8 * Math.sin(f / 5)}px ${c}` }} />{t}
          </div>
        ))}
      </div>
    );
  }
  const k = interpolate(f, [30, 60], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", left: 70, top: 1080, display: "flex", alignItems: "center", gap: 18, fontSize: 44, color: C.title, background: "#071522cc", padding: "14px 32px", borderRadius: 44, opacity: k }}>
      <span style={{ width: 32, height: 32, borderRadius: 16, background: C.green, boxShadow: `0 0 26px ${C.green}` }} />위험 → 안전
    </div>
  );
};

const SceneView: React.FC<{ s: SewerScene; org: string; disclosure: string }> = ({ s, org, disclosure }) => {
  const f = useCurrentFrame();
  const { durationInFrames: d } = useVideoConfig();
  const t = interpolate(f, [0, d], [0, 1], { extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  const [a, b] = [s.cam.from, s.cam.to];
  const L = (i: number) => a[i] + (b[i] - a[i]) * t;
  const inO = interpolate(f, [0, XFADE], [0, 1], { extrapolateRight: "clamp" });
  const rise = (delay: number) => ({
    opacity: interpolate(f, [delay, delay + 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }),
    translate: interpolate(f, [delay, delay + 18], ["0px 40px", "0px 0px"], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease }),
  });
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: "SewerPretendard", fontWeight: 700, opacity: inO }}>
      {/* 시네마틱 카메라: 천천히 접근 + 완만한 회전·이동 */}
      <AbsoluteFill style={{ overflow: "hidden" }}>
        <Img src={staticFile(s.image)} style={{ width: "100%", height: "100%", objectFit: "cover", transformOrigin: "50% 55%",
          transform: `translate(${L(1)}%, ${L(2)}%) scale(${L(0)}) rotate(${L(3)}deg)` }} />
      </AbsoluteFill>
      <AbsoluteFill style={{ background: "linear-gradient(180deg,#071522ee 0%,#07152200 26%,#07152200 58%,#071522f2 100%)" }} />
      <AbsoluteFill style={{ boxShadow: "inset 0 0 220px 40px #000000aa" }} />
      <Overlay mode={s.mode} />
      <div style={{ position: "absolute", left: 70, top: 110, fontSize: 36, color: C.teal, ...rise(0) }}>{s.tag}</div>
      <div style={{ position: "absolute", left: 70, right: 70, top: 176, fontSize: 96, lineHeight: 1.22, whiteSpace: "pre-line", color: C.title, textShadow: "0 6px 30px #000a", ...rise(6) }}>{s.title}</div>
      <div style={{ position: "absolute", left: 60, right: 60, top: 1470, padding: "26px 32px", fontSize: 52, lineHeight: 1.4, color: C.title, background: "#071522d9", borderLeft: `10px solid ${C.teal}`, ...rise(14) }}>{s.caption}</div>
      <div style={{ position: "absolute", left: 70, right: 70, top: 1738, fontSize: 38, color: C.blue }}>{org}</div>
      <div style={{ position: "absolute", left: 70, right: 70, top: 1802, fontSize: 28, color: C.sub }}>{disclosure}</div>
    </AbsoluteFill>
  );
};

export const SewerShort: React.FC<SewerShortProps> = (props) => {
  let from = 0;
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      {props.voice ? <Audio src={staticFile(props.voice)} /> : null}
      {props.scenes.map((s, i) => {
        const len = Math.round(s.seconds * 30);
        const at = from;
        from += len;
        // 다음 장면 디졸브 동안 이 장면이 남도록 뒤로 XFADE 만큼 더 둔다(마지막 제외)
        const extra = i < props.scenes.length - 1 ? XFADE : 0;
        return (
          <Sequence key={i} from={at} durationInFrames={len + extra} name={`장면 ${i + 1}`}>
            <SceneView s={s} org={props.org} disclosure={props.disclosure} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
