import { Composition, Folder } from "remotion";
import { DINNER_TOTAL, DinnerShort } from "./dinner/DinnerShort";
import { sceneFrames } from "./dinner/common";
import { EmergencyScene, HakScene, IntroScene, NearScene, SafetyScene, SpinScene, VsScene } from "./dinner/Scenes";

const SHORT = { width: 1080, height: 1920, fps: 30 } as const;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="DinnerShort" component={DinnerShort} durationInFrames={DINNER_TOTAL} {...SHORT} />
      <Folder name="DinnerScenes">
        <Composition id="Dinner-Intro" component={IntroScene} durationInFrames={sceneFrames(0)} {...SHORT} />
        <Composition id="Dinner-Hak" component={HakScene} durationInFrames={sceneFrames(1)} {...SHORT} />
        <Composition id="Dinner-Near" component={NearScene} durationInFrames={sceneFrames(2)} {...SHORT} />
        <Composition id="Dinner-Spin" component={SpinScene} durationInFrames={sceneFrames(3)} {...SHORT} />
        <Composition id="Dinner-Vs" component={VsScene} durationInFrames={sceneFrames(4)} {...SHORT} />
        <Composition id="Dinner-Safety" component={SafetyScene} durationInFrames={sceneFrames(5)} {...SHORT} />
        <Composition id="Dinner-Emergency" component={EmergencyScene} durationInFrames={sceneFrames(6)} {...SHORT} />
      </Folder>
    </>
  );
};
