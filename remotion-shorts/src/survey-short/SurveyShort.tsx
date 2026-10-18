import React from "react";
import { loadFont } from "@remotion/fonts";
import {
  AbsoluteFill, Audio, Easing, Img, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig,
} from "remotion";

// 글꼴은 Pretendard Bold 하나 — 굵기 대신 크기와 색으로 위계를 준다(CLAUDE.md, 2026-10-14).
loadFont({ family: "SurveyPretendard", url: staticFile("Pretendard-Bold.otf"), weight: "700" });

export type SurveyScene = {
  title: string;      // 장면 위 큰 글자(\n 줄바꿈)
  caption: string;    // 아래 자막 상자 — 이 장면 음성과 같은 내용
  image: string;      // public 기준 파일 이름. 비우면 그림 없이
  kind: "diorama" | "diagram"; // 디오라마는 꽉 채워 천천히 확대, 도식은 흰 바탕에 온전히
  audio: string;      // 이 장면 음성 파일(public 기준). 비우면 무음
  seconds: number;    // 장면 길이(음성 길이 + 여유)
};

export type SurveyShortProps = {
  exam: string;
  field: string;
  source: string;
  footer: string;
  disclosure: string;
  voice?: string;     // 영상 전체에 까는 음성 한 개(장면별 audio 대신)
  scenes: SurveyScene[];
};

const C = { bg: "#0b1d2e", accent: "#8fd3ff", title: "#ffe3a3", text: "#ffffff", sub: "#9fb6c6", box: "#12314a" };

const Scene: React.FC<{ scene: SurveyScene; props: SurveyShortProps }> = ({ scene, props }) => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: C.bg, fontFamily: "SurveyPretendard", fontWeight: 700, color: C.text }}>
      {scene.audio ? <Audio src={staticFile(scene.audio)} /> : null}
      <div style={{ position: "absolute", left: 80, right: 80, top: 96, fontSize: 44, color: C.accent }}>{props.exam}</div>
      <div style={{ position: "absolute", left: 80, right: 80, top: 160, fontSize: 32, color: C.sub }}>{props.field}</div>
      {props.source ? (
        <div style={{ position: "absolute", left: 80, right: 80, top: 206, fontSize: 32, color: C.sub }}>{props.source}</div>
      ) : null}
      <div
        style={{
          position: "absolute", left: 76, right: 76, top: 290, fontSize: 80, lineHeight: 1.25, whiteSpace: "pre-line",
          color: C.title,
          opacity: interpolate(frame, [0, 0.25 * fps], [0, 1], { extrapolateRight: "clamp" }),
          translate: interpolate(frame, [0, 0.4 * fps], ["0px 24px", "0px 0px"], {
            extrapolateRight: "clamp", easing: Easing.bezier(0.16, 1, 0.3, 1),
          }),
        }}
      >
        {scene.title}
      </div>
      {scene.image ? (
        <div
          style={{
            position: "absolute", left: 50, right: 50, top: 560, height: 900, borderRadius: 28, overflow: "hidden",
            background: scene.kind === "diagram" ? "#ffffff" : "#000000",
            opacity: interpolate(frame, [0, 0.3 * fps], [0, 1], { extrapolateRight: "clamp" }),
          }}
        >
          <Img
            src={staticFile(scene.image)}
            style={{
              width: "100%", height: "100%",
              objectFit: scene.kind === "diagram" ? "contain" : "cover",
              scale: scene.kind === "diagram" ? 1 : interpolate(frame, [0, durationInFrames], [1, 1.08], {
                extrapolateRight: "clamp", output: "perceptual-scale",
              }),
            }}
          />
        </div>
      ) : null}
      <div
        style={{
          position: "absolute", left: 70, right: 70, top: 1500, minHeight: 190, padding: "24px 30px",
          borderLeft: `8px solid ${C.accent}`, background: C.box, fontSize: 50, lineHeight: 1.42, whiteSpace: "pre-line",
        }}
      >
        {scene.caption}
      </div>
      <div style={{ position: "absolute", left: 80, right: 80, top: 1760, fontSize: 32, color: C.accent }}>{props.footer}</div>
      <div style={{ position: "absolute", left: 80, right: 80, top: 1818, fontSize: 26, color: C.sub }}>{props.disclosure}</div>
    </AbsoluteFill>
  );
};

export const SurveyShort: React.FC<SurveyShortProps> = (props) => {
  const { fps } = useVideoConfig();
  let from = 0;
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      {props.voice ? <Audio src={staticFile(props.voice)} /> : null}
      {props.scenes.map((scene, i) => {
        const len = Math.round(scene.seconds * fps);
        const at = from;
        from += len;
        return (
          <Sequence key={i} name={`장면 ${i + 1}`} from={at} durationInFrames={len} premountFor={fps}>
            <Scene scene={scene} props={props} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
