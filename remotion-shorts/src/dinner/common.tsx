// 룰렛 앱 숏츠 공통 요소: 바탕·머리글·휴대폰 틀·디오라마·자막·바닥글 (1080×1920, 30fps)
import { loadFont } from "@remotion/fonts";
import React from "react";
import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { NARRATION } from "./narration";

// 지침: 제목·보조 모두 Pretendard Bold, 굵기 대신 크기와 색으로 위계
loadFont({ family: "Pretendard", url: staticFile("Pretendard-Bold.otf"), weight: "700" });

export const FPS = 30;
export const C = { ink: "#2B2118", sub: "#6B5747", accent: "#FF6B2C", bg1: "#FFF7EE", bg2: "#FFE6CC" };
export const sceneFrames = (i: number) => Math.ceil(NARRATION[i].sec * FPS);
export const asset = (f: string) => staticFile(`dinner1015/${f}`);

export const Backdrop: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill
    style={{
      background: `linear-gradient(170deg, ${C.bg1} 0%, ${C.bg2} 100%)`,
      fontFamily: "Pretendard",
      fontWeight: 700,
      color: C.ink,
    }}
  >
    {children}
  </AbsoluteFill>
);

// 머리글: 채널 꼬리표 · STEP · 제목 · 보조 문구 (위에서 살짝 내려오며 나타남)
export const Header: React.FC<{ step?: string; title: string; sub: string }> = ({ step, title, sub }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame, fps, config: { damping: 200 } });
  return (
    <div
      style={{
        position: "absolute",
        top: 96,
        left: 80,
        right: 80,
        textAlign: "center",
        opacity: p,
        transform: `translateY(${interpolate(p, [0, 1], [-30, 0])}px)`,
      }}
    >
      <div
        style={{
          display: "inline-block",
          background: C.ink,
          color: "#FFD9B0",
          fontSize: 34,
          padding: "10px 28px",
          borderRadius: 40,
        }}
      >
        재난안전과 GeoAI · 생활 앱 사용법
      </div>
      <div style={{ height: 34, marginTop: 22, fontSize: 38, color: C.accent, letterSpacing: 2 }}>{step ?? ""}</div>
      <div style={{ fontSize: 88, lineHeight: 1.12, marginTop: 6 }}>{title}</div>
      <div style={{ fontSize: 46, color: C.sub, marginTop: 14 }}>{sub}</div>
    </div>
  );
};

// 휴대폰 틀 안에 앱 화면(캡처 이미지 또는 영상). 아래에서 올라오며 등장.
export const Phone: React.FC<{ children: React.ReactNode; delay?: number }> = ({ children, delay = 4 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: frame - delay, fps, config: { damping: 18, mass: 0.8 } });
  const W = 520, H = 1102;
  return (
    <div
      style={{
        position: "absolute",
        left: (1080 - W) / 2,
        top: 470,
        width: W,
        height: H,
        background: "#1E1A17",
        borderRadius: 54,
        padding: 12,
        boxShadow: "0 30px 70px rgba(80,40,10,.28)",
        opacity: interpolate(p, [0, 1], [0, 1]),
        transform: `translateY(${interpolate(p, [0, 1], [120, 0])}px)`,
      }}
    >
      <div style={{ width: "100%", height: "100%", borderRadius: 44, overflow: "hidden", background: "#FFF8F0" }}>
        {children}
      </div>
    </div>
  );
};

export const Shot: React.FC<{ src: string }> = ({ src }) => (
  <Img src={asset(src)} style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "top" }} />
);

// 디오라마: 천천히 확대(켄 번스). 그림은 AI 생성이라 작은 표시를 단다.
export const Diorama: React.FC<{ src: string; size?: number; top?: number }> = ({ src, size = 900, top = 520 }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const p = spring({ frame, fps, config: { damping: 200 } });
  const zoom = interpolate(frame, [0, durationInFrames], [1, 1.08]);
  return (
    <div
      style={{
        position: "absolute",
        left: (1080 - size) / 2,
        top,
        width: size,
        height: size,
        borderRadius: 48,
        overflow: "hidden",
        boxShadow: "0 30px 70px rgba(80,40,10,.25)",
        opacity: p,
        transform: `scale(${interpolate(p, [0, 1], [0.92, 1])})`,
      }}
    >
      <Img src={asset(src)} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${zoom})` }} />
      <div
        style={{
          position: "absolute",
          right: 18,
          bottom: 16,
          fontSize: 26,
          color: "#fff",
          background: "rgba(0,0,0,.35)",
          padding: "4px 12px",
          borderRadius: 12,
        }}
      >
        AI 생성 그림
      </div>
    </div>
  );
};

// 자막: 나레이션 단어 타이밍으로 지금 읽는 줄을 보여 주고, 읽은 단어는 진하게
export const Captions: React.FC<{ index: number }> = ({ index }) => {
  const frame = useCurrentFrame();
  const t = frame / FPS;
  const words = NARRATION[index].words as readonly (readonly [number, number, string])[];
  const lines: (readonly [number, number, string])[][] = [];
  let cur: (readonly [number, number, string])[] = [];
  for (const w of words) {
    const len = cur.reduce((n, x) => n + x[2].length + 1, 0);
    if (cur.length && len + w[2].length > 15) { lines.push(cur); cur = []; }
    cur.push(w);
  }
  if (cur.length) lines.push(cur);
  const line = lines.find((l, k) => t < (lines[k + 1]?.[0][0] ?? Infinity)) ?? lines[lines.length - 1];
  if (!line) return null;
  return (
    <div style={{ position: "absolute", left: 80, right: 80, top: 1612, textAlign: "center" }}>
      <span
        style={{
          display: "inline-block",
          background: "rgba(43,33,24,.88)",
          borderRadius: 18,
          padding: "14px 26px",
          fontSize: 48,
          lineHeight: 1.3,
        }}
      >
        {line.map((w, k) => (
          <span key={k} style={{ color: t >= w[0] ? "#FFFFFF" : "rgba(255,255,255,.45)" }}>
            {w[2]}
            {k < line.length - 1 ? " " : ""}
          </span>
        ))}
      </span>
    </div>
  );
};

export const Footer: React.FC = () => (
  <div style={{ position: "absolute", left: 0, right: 0, top: 1770, textAlign: "center", fontSize: 40, color: C.sub }}>
    🔗 <span style={{ color: C.accent }}>url.kr/wok9nk</span> · 설치 없이 무료 · <span style={{ fontSize: 30 }}>AI 음성</span>
  </div>
);
