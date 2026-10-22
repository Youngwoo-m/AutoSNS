import {TransitionSeries} from '@remotion/transitions';
import {useVideoConfig} from 'remotion';
import {Principle} from './Principle';
import {Control} from './Control';
import {Check} from './Check';
import {Closing} from './Closing';
export const CivilShort=()=>{const {fps}=useVideoConfig();return <TransitionSeries>
 <TransitionSeries.Sequence name="다짐 원리" durationInFrames={150} premountFor={fps}><Principle /></TransitionSeries.Sequence>
 <TransitionSeries.Sequence name="시공 관리" durationInFrames={135} premountFor={fps}><Control /></TransitionSeries.Sequence>
 <TransitionSeries.Sequence name="품질 확인" durationInFrames={165} premountFor={fps}><Check /></TransitionSeries.Sequence>
 <TransitionSeries.Sequence name="블로그 답안" durationInFrames={135} premountFor={fps}><Closing /></TransitionSeries.Sequence>
 </TransitionSeries>};
