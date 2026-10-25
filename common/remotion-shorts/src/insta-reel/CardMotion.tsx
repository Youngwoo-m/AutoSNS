import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

// 카드 한 장에 주는 움직임: 아래에서 떠오르며 커지는 등장 → 천천히 확대 → 빛이 한 번 훑고 지나감.
// 릴(InstaReel)과 카드 단독 영상(InstaCardMotion)이 같이 쓴다.
export const CardFace: React.FC<{ image: string; size: number; exit?: boolean }> = ({ image, size, exit = true }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200 }, durationInFrames: Math.round(0.6 * fps) });
  const leave = exit
    ? interpolate(frame, [durationInFrames - 0.3 * fps, durationInFrames], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
    : 0;
  const zoom = interpolate(frame, [0, durationInFrames], [1, 1.035], { extrapolateRight: "clamp" });
  const sweepStart = 0.5 * fps;
  const sweep = interpolate(frame, [sweepStart, sweepStart + 0.9 * fps], [-60, 160], {
    extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.inOut(Easing.quad),
  });
  return (
    <div
      style={{
        width: size, height: size, borderRadius: 28, overflow: "hidden", position: "relative",
        opacity: enter * (1 - leave),
        transform: `translateY(${(1 - enter) * 70 - leave * 30}px) scale(${(0.93 + 0.07 * enter) * zoom})`,
        boxShadow: "0 30px 80px rgba(0,0,0,0.45)",
      }}
    >
      <Img src={staticFile(image)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      <div
        style={{
          position: "absolute", inset: 0, pointerEvents: "none",
          background: `linear-gradient(105deg, transparent ${sweep - 14}%, rgba(255,255,255,0.22) ${sweep}%, transparent ${sweep + 14}%)`,
        }}
      />
    </div>
  );
};

// 카드 PNG 한 장 → 짧은 영상(정사각). 카드뉴스 이미지에 모션을 줄 때 쓴다.
export type CardMotionProps = { image: string; seconds: number };

export const InstaCardMotion: React.FC<CardMotionProps> = ({ image }) => (
  <AbsoluteFill style={{ background: "#0f2038", alignItems: "center", justifyContent: "center" }}>
    <CardFace image={image} size={1080} exit={false} />
  </AbsoluteFill>
);
