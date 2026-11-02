// 상위 4개 메뉴(계정 × 영역)와 발행 영역 보조 메뉴를 정하는 순수 함수 모음. DOM·네트워크를 쓰지 않는다.
export const ACCOUNT_IDS=['personal','dept'];
export const ACCOUNT_NAMES={personal:'개인',dept:'학과'};
export const ROUTES=[
  {id:'personal-accounts',account:'personal',area:'accounts',label:'개인 계정 연결'},
  {id:'dept-accounts',account:'dept',area:'accounts',label:'학과 계정 연결'},
  {id:'personal-publishing',account:'personal',area:'publishing',label:'개인 콘텐츠 발행'},
  {id:'dept-publishing',account:'dept',area:'publishing',label:'학과 콘텐츠 발행'}
];
export const DEFAULT_ROUTE={account:'personal',area:'publishing',view:'planning'};
const PUBLISHING_VIEWS=[['planning','콘텐츠 기획'],['today','오늘 운영'],['library','콘텐츠 보관함'],['calendar','예약 캘린더'],['crosspost','교차 발행'],['analytics','성과'],['issues','장애·설정'],['engineer','기술사']];

export const routeById=id=>ROUTES.find(route=>route.id===id)||null;
export const routeFor=(account,area)=>ROUTES.find(route=>route.account===account&&route.area===area)||null;
// 기술사 화면은 개인 계정에서만 보인다.
export const publishingViews=account=>PUBLISHING_VIEWS.filter(([id])=>id!=='engineer'||account==='personal').map(([id,label])=>({id,label}));
export function normalizeRoute({account,area,view}={}) {
  const acc=ACCOUNT_IDS.includes(account)?account:DEFAULT_ROUTE.account;
  if(area==='accounts'||(area===undefined&&view==='accounts'))return {account:acc,area:'accounts',view:'accounts'};
  const allowed=publishingViews(acc).map(item=>item.id);
  return {account:acc,area:'publishing',view:allowed.includes(view)?view:DEFAULT_ROUTE.view};
}
// 기존 setView(id) 링크 호환: 현재 계정을 유지하고 화면 id만으로 영역을 정한다.
export const routeForView=(account,id)=>normalizeRoute({account,view:id});
// aria-current는 선택된 route와 실제로 적용된 계정이 일치할 때만 참이다.
export const isActiveRoute=(route,current)=>Boolean(route&&current&&route.account===current.account&&route.area===current.area);
export const accountName=id=>ACCOUNT_NAMES[id]||'계정 미확인';
export function pageTitle({account,area}) {
  return area==='accounts'?`${accountName(account)} 계정 연결`:`${accountName(account)} 콘텐츠 발행`;
}
// 비동기 전환 중에는 대상 계정과 일치하는 snapshot만 노출한다.
export const visibleSnapshot=(routeAccount,loaderState)=>loaderState?.account===routeAccount?loaderState.snapshot||null:null;
