import type { SurveyShortProps } from "./SurveyShort";

// 스튜디오 미리보기용 예시. 실제 렌더는 render_survey_short.py 가 props 를 넘긴다.
export const sample: SurveyShortProps = {
  exam: "측량및지형공간정보기술사",
  field: "측지학·좌표계 (학습용 분류) · 11일차",
  source: "2023년 제131회 1교시 1번 기출",
  footer: "자세한 답안·따라쓰기 PDF → 재난안전과 GeoAI 블로그",
  disclosure: "학습용 예시 · AI 생성 그림 · AI 합성 음성(TTS)",
  scenes: [
    { title: "통합기준점,\n한 점에서 무엇을 줄까?", caption: "질문", image: "", kind: "diorama", audio: "", seconds: 3 },
    { title: "위치·표고·중력을 한 점에서", caption: "위성기준점·수준점·중력점을\n기초로 정합니다", image: "", kind: "diagram", audio: "", seconds: 5 },
  ],
};
