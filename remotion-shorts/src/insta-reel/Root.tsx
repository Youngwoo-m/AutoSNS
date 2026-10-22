import { CalculateMetadataFunction, Composition } from "remotion";
import { InstaCardMotion, CardMotionProps } from "./CardMotion";
import { InstaReel, InstaReelProps, defaultReelProps, reelFrames } from "./InstaReel";

const FPS = 30;

const reelMeta: CalculateMetadataFunction<InstaReelProps> = ({ props }) => ({
  durationInFrames: reelFrames({ ...defaultReelProps, ...props }),
});
const cardMeta: CalculateMetadataFunction<CardMotionProps> = ({ props }) => ({
  durationInFrames: Math.round(props.seconds * FPS),
});

export const InstaRoot: React.FC = () => (
  <>
    <Composition
      id="InstaReel" component={InstaReel} durationInFrames={20 * FPS} fps={FPS} width={1080} height={1920}
      defaultProps={defaultReelProps} calculateMetadata={reelMeta}
    />
    <Composition
      id="InstaCardMotion" component={InstaCardMotion} durationInFrames={Math.round(3.5 * FPS)} fps={FPS} width={1080} height={1080}
      defaultProps={{ image: "card1.png", seconds: 3.5 }} calculateMetadata={cardMeta}
    />
  </>
);
