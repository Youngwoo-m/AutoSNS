import { CalculateMetadataFunction, Composition } from "remotion";
import { SurveyShort, SurveyShortProps } from "./SurveyShort";
import { sample } from "./sample";

const FPS = 30;

// 장면 길이(초)의 합으로 영상 길이를 정한다. 20.0초 상한은 렌더 스크립트가 다시 확인한다.
const calculateMetadata: CalculateMetadataFunction<SurveyShortProps> = ({ props }) => ({
  durationInFrames: props.scenes.reduce((s, sc) => s + Math.round(sc.seconds * FPS), 0),
});

export const SurveyRoot: React.FC = () => (
  <Composition
    id="SurveyShort"
    component={SurveyShort}
    durationInFrames={18 * FPS}
    fps={FPS}
    width={1080}
    height={1920}
    defaultProps={sample}
    calculateMetadata={calculateMetadata}
  />
);
