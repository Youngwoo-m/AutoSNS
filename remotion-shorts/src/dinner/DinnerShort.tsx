// '오늘 저녁 뭐 먹지?' 룰렛 앱 업데이트 숏츠(2026-10-15) — 장면 7개 + 배경음악
import { TransitionSeries } from "@remotion/transitions";
import React from "react";
import { Audio, interpolate, useVideoConfig } from "remotion";
import { asset, sceneFrames } from "./common";
import { EmergencyScene, HakScene, IntroScene, NearScene, SafetyScene, SpinScene, VsScene } from "./Scenes";

export const DINNER_TOTAL = [0, 1, 2, 3, 4, 5, 6].reduce((n, i) => n + sceneFrames(i), 0);

export const DinnerShort: React.FC = () => {
  const { fps, durationInFrames } = useVideoConfig();
  return (
    <>
      <Audio
        src={asset("bgm.mp3")}
        volume={(f) => 0.14 * interpolate(f, [0, 15, durationInFrames - 30, durationInFrames], [0, 1, 1, 0], { extrapolateRight: "clamp" })}
      />
      <TransitionSeries>
        <TransitionSeries.Sequence name="인트로" durationInFrames={sceneFrames(0)} premountFor={fps}><IntroScene /></TransitionSeries.Sequence>
        <TransitionSeries.Sequence name="학식" durationInFrames={sceneFrames(1)} premountFor={fps}><HakScene /></TransitionSeries.Sequence>
        <TransitionSeries.Sequence name="내 주변" durationInFrames={sceneFrames(2)} premountFor={fps}><NearScene /></TransitionSeries.Sequence>
        <TransitionSeries.Sequence name="룰렛" durationInFrames={sceneFrames(3)} premountFor={fps}><SpinScene /></TransitionSeries.Sequence>
        <TransitionSeries.Sequence name="학식 vs 룰렛" durationInFrames={sceneFrames(4)} premountFor={fps}><VsScene /></TransitionSeries.Sequence>
        <TransitionSeries.Sequence name="안전시설" durationInFrames={sceneFrames(5)} premountFor={fps}><SafetyScene /></TransitionSeries.Sequence>
        <TransitionSeries.Sequence name="비상식량" durationInFrames={sceneFrames(6)} premountFor={fps}><EmergencyScene /></TransitionSeries.Sequence>
      </TransitionSeries>
    </>
  );
};
