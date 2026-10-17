// 룰렛 앱 업데이트 숏츠의 장면들 — 장면마다 나레이션 한 줄(음성은 장면 안에서 재생)
import React from "react";
import { AbsoluteFill, Audio, OffthreadVideo, Sequence, interpolate, useCurrentFrame } from "remotion";
import { Backdrop, Captions, Diorama, Footer, Header, Phone, Shot, asset, sceneFrames } from "./common";

const Voice: React.FC<{ index: number }> = ({ index }) => (
  <Audio src={asset(`0${index + 1}.mp3`)} />
);

// 디오라마로 시작했다가 휴대폰 화면으로 넘어가는 장면(넘어가는 시점: 장면 길이의 split 비율)
const DioramaThenPhone: React.FC<{ index: number; diorama: string; shot: string; split: number }> = ({
  index, diorama, shot, split,
}) => {
  const frame = useCurrentFrame();
  const cut = Math.round(sceneFrames(index) * split);
  const fade = interpolate(frame, [cut - 8, cut + 4], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <>
      <AbsoluteFill style={{ opacity: fade }}>
        <Diorama src={diorama} size={860} top={560} />
      </AbsoluteFill>
      <Sequence from={cut} layout="none">
        <Phone delay={0}><Shot src={shot} /></Phone>
      </Sequence>
    </>
  );
};

export const IntroScene: React.FC = () => (
  <Backdrop>
    <Voice index={0} />
    <Header title="오늘 저녁 뭐 먹지?" sub="학식 · 내 주변 · 안전 기능 업데이트" />
    <Diorama src="campus_cafeteria.png" size={900} top={560} />
    <Captions index={0} />
    <Footer />
  </Backdrop>
);

export const HakScene: React.FC = () => (
  <Backdrop>
    <Voice index={1} />
    <Header step="STEP 1" title="🍚 학식 한눈에" sub="오늘 아침 · 점심 · 저녁 메뉴" />
    <Phone><Shot src="02_hak.png" /></Phone>
    <Captions index={1} />
    <Footer />
  </Backdrop>
);

export const NearScene: React.FC = () => (
  <Backdrop>
    <Voice index={2} />
    <Header step="STEP 2" title="📍 내 주변 룰렛" sub="반경 1km 음식점으로 칸을 채워요" />
    <DioramaThenPhone index={2} diorama="food_street.png" shot="03_near.png" split={0.4} />
    <Captions index={2} />
    <Footer />
  </Backdrop>
);

export const SpinScene: React.FC = () => (
  <Backdrop>
    <Voice index={3} />
    <Header step="STEP 3" title="🎡 룰렛 돌리기" sub="버튼 한 번이면 메뉴 결정" />
    <Phone delay={0}>
      <OffthreadVideo src={asset("spin.mp4")} muted style={{ width: "100%", height: "100%", objectFit: "cover", objectPosition: "top" }} />
    </Phone>
    <Captions index={3} />
    <Footer />
  </Backdrop>
);

export const VsScene: React.FC = () => (
  <Backdrop>
    <Voice index={4} />
    <Header step="STEP 4" title="🍚 학식 vs 🎡 룰렛" sub="거리 · 운영 시간으로 비교" />
    <Phone><Shot src="04_result.png" /></Phone>
    <Captions index={4} />
    <Footer />
  </Backdrop>
);

export const SafetyScene: React.FC = () => (
  <Backdrop>
    <Voice index={5} />
    <Header step="STEP 5" title="🛟 내 주변 안전시설" sub="기상특보 · AED · 민방위 대피소" />
    <Phone><Shot src="05_safety.png" /></Phone>
    <Captions index={5} />
    <Footer />
  </Backdrop>
);

export const EmergencyScene: React.FC = () => (
  <Backdrop>
    <Voice index={6} />
    <Header title="🔦 비상식량 모드" sub="3일 비상용품 체크리스트" />
    <DioramaThenPhone index={6} diorama="emergency_pantry.png" shot="06_emergency.png" split={0.45} />
    <Captions index={6} />
    <Footer />
  </Backdrop>
);
