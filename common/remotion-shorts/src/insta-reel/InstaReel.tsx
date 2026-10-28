import React from "react";
import { loadFont } from "@remotion/fonts";
import {
  AbsoluteFill, Audio, Easing, Img, OffthreadVideo, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig,
} from "remotion";
import { CardFace } from "./CardMotion";

// 글꼴은 Pretendard Bold 하나(CLAUDE.md 영상 지침). 카드 글자는 이미 PNG 안에 있다.
loadFont({ family: "ReelPretendard", url: staticFile("Pretendard-Bold.otf"), weight: "700" });

export type InstaReelProps = {
  title: string;          // 첫 화면 제목(\n 줄바꿈)
  cards: string[];        // 카드 PNG(public 기준 파일 이름), 순서대로
  dioramas: string[];     // 디오라마 그림 0~3장. 첫 장=첫 화면, 마지막 장=끝 화면, 가운데=카드 사이
  bg: string;             // 배경 영상 mp4(없으면 ""). 단색 그라데이션 대신 깐다
  audio: string;          // 배경음악(없으면 "")
  endText: string;        // 끝 화면 문구(\n 줄바꿈)
  account: string;        // 끝 화면 계정 표기
  disclosure: string;     // 디오라마가 보일 때 아래 작은 글씨(AI 생성 그림 고지)
  stats?: { value: number; suffix: string; label: string }[]; // 모션그래픽: 숫자 올라가는 수치 띠(카드 사이 장면)
  scenes?: { head: string; lines: string[] }[]; // 있으면 카드 PNG 대신 모션그래픽 글자 장면(디오라마 위)
  secondsPerCard: number;
  hookSeconds: number;
  gapSeconds: number;     // 카드 사이 디오라마·배경이 보이는 시간
  endSeconds: number;
};

export const defaultReelProps: InstaReelProps = {
  title: "이번 주 재난안전 뉴스",
  cards: [],
  dioramas: [],
  bg: "",
  audio: "",
  endText: "재난안전 소식\n팔로우하고 받아보세요",
  account: "@smu_ds_official",
  disclosure: "AI 생성 그림",
  secondsPerCard: 3.5,
  hookSeconds: 2.4,
  gapSeconds: 1.2,
  endSeconds: 2.6,
};

const FPS = 30;
const C = { bg1: "#0b1d2e", bg2: "#12314a", accent: "#8fd3ff", title: "#ffe3a3", text: "#ffffff", sub: "#9fb6c6" };

type Seg =
  | { kind: "hook"; frames: number }
  | { kind: "card"; frames: number; idx: number }
  | { kind: "gap"; frames: number; dio: string }
  | { kind: "end"; frames: number };

// 디오라마 배치: 첫 장은 첫 화면, 마지막 장은 끝 화면(한 장뿐이면 둘 다), 가운데 장은 카드 사이에 고르게.
// 디오라마가 없는데 배경 영상이 있으면 예전처럼 카드마다 배경이 비치는 틈을 둔다.
export const buildSegments = (p: InstaReelProps): Seg[] => {
  const n = p.scenes?.length || p.cards.length;
  const f = (s: number) => Math.max(1, Math.round(s * FPS));
  const d = p.dioramas;
  const middle = d.length > 2 ? d.slice(1, -1) : [];
  const gapAfter = new Map<number, string>();
  middle.forEach((dio, k) => gapAfter.set(Math.floor(((k + 1) * n) / (middle.length + 1)) - 1, dio));
  if (!middle.length && p.bg) for (let i = 0; i < n - 1; i++) gapAfter.set(i, "");
  const segs: Seg[] = [{ kind: "hook", frames: f(p.hookSeconds) }];
  for (let i = 0; i < n; i++) {
    segs.push({ kind: "card", frames: f(p.secondsPerCard), idx: i });
    const g = gapAfter.get(i);
    if (g !== undefined && i < n - 1) segs.push({ kind: "gap", frames: f(p.gapSeconds), dio: g });
  }
  segs.push({ kind: "end", frames: f(p.endSeconds) });
  return segs;
};

export const reelFrames = (p: InstaReelProps) => buildSegments(p).reduce((s, g) => s + g.frames, 0);

const DioramaFull: React.FC<{ image: string; dark?: number; note?: string }> = ({ image, dark = 0.25, note }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const fade = Math.min(10, durationInFrames / 3);
  const op = interpolate(frame, [0, fade, durationInFrames - fade, durationInFrames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp",
  });
  const scale = interpolate(frame, [0, durationInFrames], [1.04, 1.16], { extrapolateRight: "clamp", output: "perceptual-scale" });
  return (
    <AbsoluteFill style={{ opacity: op }}>
      <Img src={staticFile(image)} style={{ width: "100%", height: "100%", objectFit: "cover", scale }} />
      <AbsoluteFill style={{ background: `linear-gradient(180deg, rgba(0,0,0,${dark}) 0%, rgba(0,0,0,${dark * 0.4}) 45%, rgba(0,0,0,${dark + 0.2}) 100%)` }} />
      {note ? (
        <div style={{ position: "absolute", left: 60, right: 60, bottom: 60, fontSize: 26, color: "rgba(255,255,255,0.78)", textAlign: "center" }}>
          {note}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

const RiseText: React.FC<{ children: React.ReactNode; top: number; size: number; color: string; delay?: number }> = ({
  children, top, size, color, delay = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = spring({ frame: frame - delay, fps, config: { damping: 200 }, durationInFrames: Math.round(0.7 * fps) });
  return (
    <div
      style={{
        position: "absolute", left: 70, right: 70, top, fontSize: size, lineHeight: 1.28, color, textAlign: "center",
        whiteSpace: "pre-line", opacity: t, transform: `translateY(${(1 - t) * 40}px)`, textShadow: "0 4px 24px rgba(0,0,0,0.6)",
      }}
    >
      {children}
    </div>
  );
};

// 모션그래픽: 숫자가 올라가는 수치 띠 + 아래에서 그어지는 선
const StatRow: React.FC<{ stats: { value: number; suffix: string; label: string }[]; top: number }> = ({ stats, top }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div style={{ position: "absolute", left: 60, right: 60, top, display: "flex", justifyContent: "center", gap: 60 }}>
      {stats.map((st, i) => {
        const t = spring({ frame: frame - 6 - i * 8, fps, config: { damping: 200 }, durationInFrames: Math.round(1.1 * fps) });
        return (
          <div key={i} style={{ textAlign: "center", opacity: Math.min(1, t * 2), transform: `translateY(${(1 - t) * 50}px)` }}>
            <div style={{ fontSize: 150, lineHeight: 1, color: C.title, textShadow: "0 4px 24px rgba(0,0,0,0.6)" }}>
              {Math.round(st.value * t)}<span style={{ fontSize: 64, color: C.accent }}>{st.suffix}</span>
            </div>
            <div style={{ marginTop: 14, height: 6, width: `${t * 100}%`, background: C.accent, borderRadius: 3, marginInline: "auto" }} />
            <div style={{ marginTop: 14, fontSize: 40, color: C.text, textShadow: "0 3px 16px rgba(0,0,0,0.6)" }}>{st.label}</div>
          </div>
        );
      })}
    </div>
  );
};

const Hook: React.FC<{ p: InstaReelProps }> = ({ p }) => (
  <AbsoluteFill>
    {p.dioramas[0] ? <DioramaFull image={p.dioramas[0]} dark={0.35} note={p.disclosure} /> : null}
    <RiseText top={700} size={92} color={C.title}>{p.title}</RiseText>
  </AbsoluteFill>
);

const End: React.FC<{ p: InstaReelProps }> = ({ p }) => {
  const dio = p.dioramas.length ? p.dioramas[p.dioramas.length - 1] : "";
  return (
    <AbsoluteFill>
      {dio ? <DioramaFull image={dio} dark={0.45} note={p.disclosure} /> : null}
      <RiseText top={640} size={84} color={C.text}>{p.endText}</RiseText>
      <RiseText top={1010} size={54} color={C.accent} delay={8}>{p.account}</RiseText>
    </AbsoluteFill>
  );
};

// 모션그래픽 글자 장면: 디오라마를 어둡게 깔고 제목이 밀려 들어오고, 줄이 차례로 올라온다
const MotionScene: React.FC<{ p: InstaReelProps; idx: number }> = ({ p, idx }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const sc = p.scenes![idx];
  const n = p.scenes!.length;
  const dio = p.dioramas.length ? p.dioramas[idx % p.dioramas.length] : "";
  const head = spring({ frame, fps, config: { damping: 200 }, durationInFrames: Math.round(0.8 * fps) });
  const out = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill>
      {dio ? <DioramaFull image={dio} dark={0.62} note={p.disclosure} /> : null}
      <AbsoluteFill style={{ opacity: out }}>
        <div style={{ position: "absolute", top: 250, display: "flex", gap: 12, left: 90 }}>
          {Array.from({ length: n }).map((_, i) => (
            <div key={i} style={{ width: i === idx ? 54 : 14, height: 14, borderRadius: 7, background: i === idx ? C.accent : "rgba(255,255,255,0.35)" }} />
          ))}
        </div>
        <div style={{ position: "absolute", left: 90, right: 90, top: 330, opacity: head, transform: `translateX(${(1 - head) * -120}px)` }}>
          <div style={{ fontSize: 92, lineHeight: 1.2, color: C.title, whiteSpace: "pre-line", textShadow: "0 4px 24px rgba(0,0,0,0.7)" }}>{sc.head}</div>
          <div style={{ marginTop: 26, height: 8, width: `${head * 40}%`, background: C.accent, borderRadius: 4 }} />
        </div>
        <div style={{ position: "absolute", left: 90, right: 90, top: 700 }}>
          {sc.lines.map((ln, i) => {
            const t = spring({ frame: frame - 14 - i * 10, fps, config: { damping: 200 }, durationInFrames: Math.round(0.7 * fps) });
            return (
              <div key={i} style={{ display: "flex", gap: 24, marginBottom: 36, opacity: t, transform: `translateY(${(1 - t) * 50}px)` }}>
                <div style={{ width: 10, borderRadius: 5, background: C.accent, flexShrink: 0 }} />
                <div style={{ fontSize: 60, lineHeight: 1.3, color: C.text, textShadow: "0 3px 20px rgba(0,0,0,0.75)", wordBreak: "keep-all" }}>{ln}</div>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const CardSeg: React.FC<{ p: InstaReelProps; idx: number }> = ({ p, idx }) => {
  const size = 940;
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
      <CardFace image={p.cards[idx]} size={size} exit={idx < p.cards.length - 1} />
      {/* 진행 표시: 카드 수만큼 점, 지금 카드는 길게 */}
      <div style={{ position: "absolute", top: (1920 - size) / 2 - 70, display: "flex", gap: 12 }}>
        {p.cards.map((_, i) => (
          <div key={i} style={{ width: i === idx ? 54 : 14, height: 14, borderRadius: 7, background: i === idx ? C.accent : "rgba(255,255,255,0.35)" }} />
        ))}
      </div>
    </AbsoluteFill>
  );
};

export const InstaReel: React.FC<InstaReelProps> = (props) => {
  const p = { ...defaultReelProps, ...props };
  const { durationInFrames, fps } = useVideoConfig();
  const segs = buildSegments(p);
  let from = 0;
  return (
    <AbsoluteFill style={{ background: `linear-gradient(180deg, ${C.bg1}, ${C.bg2})`, fontFamily: "ReelPretendard", fontWeight: 700 }}>
      {p.bg ? <OffthreadVideo src={staticFile(p.bg)} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : null}
      {p.audio ? (
        <Audio
          src={staticFile(p.audio)} loop
          volume={(f) => interpolate(f, [0, 0.6 * fps, durationInFrames - 1.5 * fps, durationInFrames], [0, 1, 1, 0], {
            extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.linear,
          })}
        />
      ) : null}
      {segs.map((s, i) => {
        const at = from;
        from += s.frames;
        return (
          <Sequence key={i} from={at} durationInFrames={s.frames} premountFor={FPS}>
            {s.kind === "hook" ? <Hook p={p} /> : null}
            {s.kind === "card" ? (p.scenes?.length ? <MotionScene p={p} idx={s.idx} /> : <CardSeg p={p} idx={s.idx} />) : null}
            {s.kind === "gap" && s.dio ? (
              <AbsoluteFill>
                <DioramaFull image={s.dio} note={p.disclosure} />
                {p.stats?.length ? <StatRow stats={p.stats} top={760} /> : null}
              </AbsoluteFill>
            ) : null}
            {s.kind === "end" ? <End p={p} /> : null}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
