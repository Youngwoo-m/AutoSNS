// 인스타 릴·카드 모션 전용 진입점 — 공용 Root.tsx 를 건드리지 않고 따로 렌더한다.
//   python3 render_insta_reel.py reel|card props.json out.mp4   (remotion-shorts/ 에서)
import { registerRoot } from "remotion";
import { InstaRoot } from "./Root";

registerRoot(InstaRoot);
