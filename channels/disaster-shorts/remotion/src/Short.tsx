// 재난 유형별 숏츠 본문 — tools/assemble.py 가 만든 props.json 으로 그린다(10/15 Remotion 전환).
// 장면 영상(속도 맞춤·정지 채움은 파이썬이 미리 함) + 나레이션 + 위쪽 시리즈 띠·교수 소개·꼬리표 + 아래 자막 + AI 고지 + (디오라마면) 계기판.
import { loadFont } from "@remotion/fonts";
import { Audio, Video } from "@remotion/media";
import React from "react";
import { AbsoluteFill, interpolate, Sequence, Series, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

const FONT = "KoPub";
loadFont({ family: FONT, url: staticFile("fonts/KoPubBold.otf"), weight: "700" });
loadFont({ family: "HookPretendard", url: staticFile("fonts/Pretendard-Bold.otf"), weight: "700" });   // 훅 제목은 Pretendard Bold(영상 지침)

export type Caption = { lines: string[]; size: number; from: number; to: number };
export type Scene = { id: number; clip: string; voice: string; frames: number; labels: string[]; captions: Caption[]; gauge?: string | null };
export type ShortProps = { tag: string; credit: string | null; disclaimer: string; scenes: Scene[]; hook?: string[]; hook_frames?: number };

const font: React.CSSProperties = { fontFamily: `${FONT}, "Apple Color Emoji", sans-serif`, fontWeight: 700, whiteSpace: "pre" };

const Chrome: React.FC<{ tag: string; credit: string | null; labels: string[] }> = ({ tag, credit, labels }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 48, top: 150, height: 72, display: "flex", alignItems: "center", background: "rgba(14,32,66,0.84)", borderRadius: 14, paddingRight: 28 }}>
        <div style={{ width: 12, height: 72, background: "#ffc83d", borderRadius: "14px 0 0 14px", marginRight: 22 }} />
        <span style={{ ...font, fontSize: 40, color: "#fff" }}>{tag}</span>
      </div>
      {credit ? (
        <div style={{ position: "absolute", left: 48, top: 232, height: 56, display: "flex", alignItems: "center", background: "rgba(0,0,0,0.59)", borderRadius: 12, padding: "0 24px" }}>
          <span style={{ ...font, fontSize: 34, color: "rgba(255,255,255,0.92)" }}>{credit}</span>
        </div>
      ) : null}
      {labels.map((lab, i) => {
        const s = spring({ frame: frame - 4 - i * 6, fps, config: { damping: 18, stiffness: 140 } });
        return (
          <div key={i} style={{ position: "absolute", left: 48, top: (credit ? 310 : 270) + i * 88, height: 70, display: "flex", alignItems: "center", background: "rgba(10,60,120,0.59)", border: "3px solid rgb(120,200,255)", borderRadius: 12, padding: "0 28px", boxSizing: "border-box", opacity: s, transform: `translateX(${(1 - s) * -40}px)` }}>
            <span style={{ ...font, fontSize: 44, color: "rgb(220,240,255)" }}>{lab}</span>
          </div>
        );
      })}
      <div style={{ position: "absolute", top: 1540, width: "100%", textAlign: "center" }}>
        <span style={{ ...font, fontSize: 28, color: "rgba(255,255,255,0.75)" }}>※ 배경은 AI로 생성한 재현 영상입니다</span>
      </div>
    </AbsoluteFill>
  );
};

const Captions: React.FC<{ captions: Caption[] }> = ({ captions }) => {
  const frame = useCurrentFrame();
  const c = captions.find((x) => frame >= x.from && frame < x.to);
  if (!c) return null;
  const k = interpolate(frame - c.from, [0, 5], [0, 1], { extrapolateRight: "clamp" });
  const lh = c.size + 18;
  const top = 1330 - (lh * c.lines.length) / 2;
  return (
    <div style={{ position: "absolute", top, width: "100%", display: "flex", flexDirection: "column", alignItems: "center", opacity: k, transform: `scale(${0.96 + 0.04 * k})` }}>
      {c.lines.map((ln, i) => (
        <div key={i} style={{ height: lh, display: "flex", alignItems: "flex-start" }}>
          <span style={{ ...font, fontSize: c.size, lineHeight: `${c.size + 22}px`, color: "#fff", background: "rgba(0,0,0,0.69)", borderRadius: 18, padding: "0 28px" }}>{ln}</span>
        </div>
      ))}
    </div>
  );
};

// 첫 장면 맨 앞 2~3초에 크게 띄우는 훅(인트로 대신, 2026-10-22). 위쪽 띠·꼬리표·계기판 아래 가운데.
const Hook: React.FC<{ lines: string[]; frames: number }> = ({ lines, frames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const a = spring({ frame, fps, config: { damping: 16, stiffness: 150 } });
  const out = interpolate(frame, [frames - 10, frames], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const longest = Math.max(...lines.map((l) => l.length), 1);
  const size = Math.min(104, Math.floor(880 / longest));
  return (
    <div style={{ position: "absolute", left: 40, right: 40, top: 640, display: "flex", justifyContent: "center", opacity: a * out, transform: `translateY(${(1 - a) * 40}px)` }}>
      <div style={{ background: "rgba(8,18,40,0.82)", borderRadius: 26, padding: "34px 46px", borderLeft: "14px solid #ffc83d", textAlign: "left" }}>
        {lines.map((ln, i) => (
          <div key={i} style={{ fontFamily: "HookPretendard, sans-serif", fontWeight: 700, whiteSpace: "pre", fontSize: size, lineHeight: 1.25, color: i === 0 ? "#ffe3a3" : "#ffffff" }}>{ln}</div>
        ))}
      </div>
    </div>
  );
};

const Gauge: React.FC<{ src: string }> = ({ src }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame: frame - 6, fps, config: { damping: 14, stiffness: 120 } });
  return (
    <div style={{ position: "absolute", right: 33, top: 180, width: 345, height: 345, borderRadius: 22, overflow: "hidden", boxShadow: "0 14px 40px rgba(0,0,0,0.45)", border: "4px solid rgba(255,255,255,0.9)", transform: `scale(${0.6 + 0.4 * s})`, opacity: s, transformOrigin: "top right" }}>
      <Video src={staticFile(src)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
    </div>
  );
};

export const Short: React.FC<ShortProps> = ({ tag, credit, scenes, hook, hook_frames }) => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      <Series>
        {scenes.map((s, idx) => (
          <Series.Sequence key={s.id} durationInFrames={s.frames} premountFor={fps} name={`장면 ${s.id}`}>
            <AbsoluteFill>
              <Video src={staticFile(s.clip)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            </AbsoluteFill>
            {s.gauge ? <Gauge src={s.gauge} /> : null}
            <Chrome tag={tag} credit={credit} labels={s.labels} />
            <Captions captions={s.captions} />
            {idx === 0 && hook && hook.length ? <Sequence durationInFrames={Math.min(hook_frames ?? 78, s.frames)}><Hook lines={hook} frames={Math.min(hook_frames ?? 78, s.frames)} /></Sequence> : null}
            <Sequence durationInFrames={s.frames}>
              <Audio src={staticFile(s.voice)} />
            </Sequence>
          </Series.Sequence>
        ))}
      </Series>
    </AbsoluteFill>
  );
};
