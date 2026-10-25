import React from 'react';
import {loadFont} from '@remotion/fonts';
import {AbsoluteFill, Audio, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
loadFont({family:'CivilPretendard',url:staticFile('civil-day01/Pretendard-Bold.otf'),weight:'700'});
export const CivilFrame:React.FC<{title:string;caption:string;image:string;audio:string;step:string}>=({title,caption,image,audio,step})=>{
 const frame=useCurrentFrame();const {fps}=useVideoConfig();
 return <AbsoluteFill style={{background:'#071e32',fontFamily:'CivilPretendard',fontWeight:700,color:'#fff'}}>
  <Audio src={staticFile(`civil-day01/${audio}`)} />
  <div style={{position:'absolute',left:90,top:118,fontSize:42,color:'#91d9ce'}}>토목시공기술사 · 1일차</div>
  <div style={{position:'absolute',left:90,top:196,fontSize:30,letterSpacing:3,color:'#86a9b6'}}>{step}</div>
  <div style={{position:'absolute',left:88,right:88,top:285,fontSize:90,lineHeight:1.26,whiteSpace:'pre-line',color:'#ffe2a0',opacity:interpolate(frame,[0,0.2*fps],[0.35,1],{extrapolateRight:'clamp'})}}>{title}</div>
  <Img src={staticFile(`civil-day01/${image}`)} style={{position:'absolute',left:45,top:590,width:990,height:870,objectFit:'cover',borderRadius:28,scale:interpolate(frame,[0,6*fps],[1,1.045],{extrapolateRight:'clamp'})}} />
  <div style={{position:'absolute',left:80,right:80,top:1500,minHeight:170,padding:'26px 28px',borderLeft:'6px solid #79ccbb',background:'#102e43',fontSize:48,lineHeight:1.5,whiteSpace:'pre-line'}}>{caption}</div>
  <div style={{position:'absolute',left:90,right:90,top:1780,fontSize:30,color:'#a9bdc7'}}>정답예시·PDF → 재난안전과 GeoAI 블로그</div>
  <div style={{position:'absolute',left:90,right:90,top:1842,fontSize:26,color:'#7898aa'}}>학습용 개념도 · AI 생성 그림·음성</div>
 </AbsoluteFill>;
};
