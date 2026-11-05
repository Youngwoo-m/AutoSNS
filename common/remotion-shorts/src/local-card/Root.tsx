import React from 'react';
import {Still} from 'remotion';
import {LocalCard, type LocalCardProps} from './LocalCard';

const sample: LocalCardProps = {
  owner_account_id: 'personal',
  spec: {template: 'steps', title: '안전을 위한 세 가지 확인', body: ['상황을 확인합니다', '필요한 조치를 준비합니다', '결과를 기록합니다'], footer: '검토 전 · 예시 문구'},
};
export const LocalCardRoot: React.FC = () => (
  <Still id="LocalCard" component={LocalCard} width={1080} height={1350} defaultProps={sample}/>
);
