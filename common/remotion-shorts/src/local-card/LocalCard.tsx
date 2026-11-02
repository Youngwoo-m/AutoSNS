import React, {useLayoutEffect, useRef, useState} from 'react';
import {AbsoluteFill, staticFile, delayRender, continueRender, cancelRender} from 'remotion';
import {loadFont} from '@remotion/fonts';

loadFont({family: 'LocalCardPretendard', url: staticFile('Pretendard-Bold.otf'), weight: '700'});
export type LocalCardProps = {
  owner_account_id: 'personal' | 'dept';
  spec: {template: 'card' | 'steps'; title: string; body: string[]; footer: string};
};

// Font readiness and actual layout are checked before the still is released.
const FittedText: React.FC<{text: string; size: number; style?: React.CSSProperties}> = ({text, size, style}) => {
  const ref = useRef<HTMLDivElement>(null);
  const [handle] = useState(() => delayRender('LocalCard text fitting'));
  useLayoutEffect(() => {
    let alive = true;
    document.fonts.ready.then(() => {
      if (!alive || !ref.current) return;
      const node = ref.current;
      let pixels = size;
      node.style.fontSize = `${pixels}px`;
      while ((node.scrollHeight > node.clientHeight + 1 || node.scrollWidth > node.clientWidth + 1) && pixels > 14) {
        pixels -= 1;
        node.style.fontSize = `${pixels}px`;
      }
      if (node.scrollHeight > node.clientHeight + 1 || node.scrollWidth > node.clientWidth + 1) {
        cancelRender(new Error('LocalCard text does not fit'));
      } else continueRender(handle);
    }).catch(() => cancelRender(new Error('LocalCard font unavailable')));
    return () => {alive = false;};
  }, [handle, size, text]);
  return <div ref={ref} style={{fontSize: size, lineHeight: 1.3, whiteSpace: 'normal', wordBreak: 'break-all', overflow: 'hidden', ...style}}>{text}</div>;
};

export const LocalCard: React.FC<LocalCardProps> = ({owner_account_id, spec}) => {
  const dept = owner_account_id === 'dept';
  const accent = dept ? '#226bba' : '#17745c';
  const count = spec.body.length;
  const bodySize = count > 4 ? 27 : count > 2 ? 31 : 38;
  return <AbsoluteFill style={{background: '#f2f5f7', color: '#142635', fontFamily: 'LocalCardPretendard', fontWeight: 700, padding: '64px 64px 54px'}}>
    <div style={{display: 'flex', alignItems: 'center', gap: 14, marginBottom: 30}}>
      <div style={{width: 12, height: 40, background: accent, borderRadius: 6}}/>
      <div style={{fontSize: 26, color: accent}}>{dept ? '세명대학교 재난안전학과' : '개인 콘텐츠'}</div>
    </div>
    <FittedText text={spec.title} size={spec.title.length > 45 ? 46 : 58} style={{height: 220, flexShrink: 0, marginBottom: 30}}/>
    <div style={{display: 'flex', flexDirection: 'column', flex: 1, gap: count > 4 ? 12 : 20, minHeight: 0}}>
      {spec.body.map((text, index) => <div key={index} style={{display: 'flex', flex: 1, alignItems: 'center', gap: 20, background: '#ffffff', borderRadius: 18, padding: count > 4 ? '14px 22px' : '22px 26px', borderLeft: `7px solid ${accent}`, minHeight: 0}}>
        {spec.template === 'steps' ? <div style={{flexShrink: 0, width: 48, height: 48, borderRadius: 24, background: accent, color: '#ffffff', fontSize: 26, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>{index + 1}</div> : null}
        <FittedText text={text} size={bodySize} style={{flex: 1, height: '100%'}}/>
      </div>)}
    </div>
    <FittedText text={spec.footer} size={22} style={{marginTop: 28, height: 86, flexShrink: 0, color: '#4d6475'}}/>
    <div style={{fontSize: 17, color: '#647b8c', marginTop: 12}}>로컬 제작 · 검토 전</div>
  </AbsoluteFill>;
};
