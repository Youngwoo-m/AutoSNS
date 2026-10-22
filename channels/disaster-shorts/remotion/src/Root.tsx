import { CalculateMetadataFunction, Composition } from "remotion";
import { Short, ShortProps } from "./Short";

// 길이는 장면 프레임 합 — assemble.py 가 --props 로 넘긴다
const calculateMetadata: CalculateMetadataFunction<ShortProps> = ({ props }) => ({
  durationInFrames: Math.max(1, props.scenes.reduce((a, s) => a + s.frames, 0)),
});

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="DisasterShort"
      component={Short}
      durationInFrames={300}
      fps={30}
      width={1080}
      height={1920}
      defaultProps={{ tag: "재난 대응 · 예시", credit: "세명대학교 재난안전학과 나영우 교수", disclaimer: "", scenes: [] } as ShortProps}
      calculateMetadata={calculateMetadata}
    />
  );
};
