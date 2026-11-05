// 측량 하루 한 문제 숏츠 전용 진입점 — 공용 Root.tsx 를 건드리지 않고 따로 렌더한다.
//   python3 render_survey_short.py props.json out.mp4   (remotion-shorts/ 에서)
import { registerRoot } from "remotion";
import { SurveyRoot } from "./Root";

registerRoot(SurveyRoot);
