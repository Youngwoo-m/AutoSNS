import { Composition } from "remotion";
import { SewerShort, SewerShortProps, totalFrames, DEFAULT_PROPS } from "./SewerShort";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="SewerShort"
    component={SewerShort}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={totalFrames(DEFAULT_PROPS)}
    defaultProps={DEFAULT_PROPS as SewerShortProps}
    calculateMetadata={({ props }) => ({ durationInFrames: totalFrames(props as SewerShortProps) })}
  />
);
