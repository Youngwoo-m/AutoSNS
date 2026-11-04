// 채널의 구현·연결·실행 상태를 분리해 보여 주는 읽기 전용 패널.
const FIELDS=['account_id','platform','connection_id','label','planning_enabled','target_status','authentication_status','publisher_status','verification_status','metrics_status','live_enabled','next_actions'];
const STATUS={implemented:'개발됨',code_implemented:'개발됨',text_only_implemented:'텍스트 기반 개발',local_preparation_only:'로컬 영상 준비',browser_implemented:'브라우저 경로 개발',not_implemented:'미구현',stored_only:'저장 자료 조회',public_probe_required:'공개 확인 연결 필요',receipt_implemented:'업로드 영수증 검증 개발',hash_implemented:'본문·자산 검증 개발',metrics_implemented:'통계 수집기 개발',configured:'설정됨',confirmed:'확인됨',required:'확인 필요',target_required:'대상 확인 필요',unconfigured:'설정 전',not_configured:'설정 전',connected:'연결 기록 있음',not_connected:'연결 전',disconnected:'연결 전',unknown:'확인 전',unchecked:'확인 전',not_checked:'확인 전',expired:'인증 갱신 필요',pending:'확인 대기',unsupported:'지원 경로 없음',verified:'대상 ID 확인 기록',unverified:'대상 ID 미확인',no_connection:'연결 등록 전',reauth_required:'재인증 필요',needs_reauth:'재인증 필요'};
const exact=(v,keys)=>!!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const text=(v,max=2000)=>typeof v==='string'&&v.length>0&&v.length<=max;
const realAccount=a=>a==='personal'||a==='dept';
const validAccount=a=>realAccount(a)||a==='all';
const validRow=(r,a)=>exact(r,FIELDS)&&realAccount(r.account_id)&&(a==='all'||r.account_id===a)&&text(r.platform,100)&&(r.connection_id===null||text(r.connection_id,200))&&text(r.label,300)&&typeof r.planning_enabled==='boolean'&&['target_status','authentication_status','publisher_status','verification_status','metrics_status'].every(k=>text(r[k],100))&&r.live_enabled===false&&Array.isArray(r.next_actions)&&r.next_actions.length<=20&&r.next_actions.every(v=>text(v,1000));
export function createChannelReadinessPanel({document,fetcher=globalThis.fetch,onChange=()=>{}}={}){
 const root=document.createElement('details');root.className='panel channel-readiness';
 let account=null,rows=[],loaded=false,busy=false,message='',generation=0;
 const node=(tag,attrs={},value)=>{const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='disabled')n.disabled=v;else n.setAttribute(k,String(v));}if(value!==undefined)n.textContent=value;return n;};
 const status=(value,field)=>field==='authentication_status'&&value==='connected'?'연결 기록 있음 · 현재 로그인 미검증':field==='metrics_status'&&['implemented','metricsimplemented'].includes(value)?'통계 수집기 개발':STATUS[value]||'확인 필요';
 function paint(){
  const body=node('div',{class:'panel-body'});body.append(node('p',{},`${account==='personal'?'개인':account==='dept'?'학과':account==='all'?'전체':'계정 선택 전'} 계정의 채널별 준비 상태입니다. 개발 상태와 계정 인증·실제 발행 상태는 서로 다릅니다. 관리 웹 실행 상태이며 기존 자동 작업의 동작 여부와 별개입니다.`));
  if(loaded){
   if(!rows.length)body.append(node('p',{class:'sub'},'조회된 채널이 없습니다.'));
   for(const row of rows){
    const card=node('section',{'data-channel-readiness-platform':row.platform,'data-channel-readiness-account':row.account_id});card.append(node('h4',{},`${row.account_id==='personal'?'개인':'학과'} · ${row.label}`));
    const dl=node('dl');
    const fields=[['기획',row.planning_enabled?'기획 가능':'기획 비활성'],['대상',status(row.target_status,'target_status')],['인증',status(row.authentication_status,'authentication_status')],['발행 모듈',status(row.publisher_status,'publisher_status')],['공개 검증',status(row.verification_status,'verification_status')],['성과',status(row.metrics_status,'metrics_status')],['실행','관리 웹 실제 발행 꺼짐']];
    for(const [label,value] of fields)dl.append(node('dt',{},label),node('dd',{},value));card.append(dl);
    if(row.next_actions.length){const list=node('ul');for(const action of row.next_actions)list.append(node('li',{},action));card.append(list);}body.append(card);
   }
  }else if(!busy)body.append(node('p',{class:'sub'},'패널을 펼치면 저장된 준비 상태만 조회합니다. 로그인·권한 부여·자격 조회·발행을 실행하지 않습니다.'));
  const reload=node('button',{type:'button',class:'btn btn-small','data-channel-readiness-action':'reload',disabled:busy||!account},'상태 다시 조회');reload.addEventListener('click',load);body.append(reload,node('p',{role:'status'},message));root.replaceChildren(node('summary',{},'채널별 연결 준비 상태'),body);
 }
 async function load(){
  if(!account||busy)return;const mine=account,token=++generation;busy=true;message='채널 준비 상태 조회 중';paint();onChange();
  try{
   let response;try{response=await fetcher('/api/v2/channels/readiness?account='+mine,{method:'GET',credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});}catch{throw new Error('채널 준비 상태 서버에 연결하지 못했습니다.');}
   if(!response.ok)throw new Error(response.status===401?'로그인 후 다시 조회하세요.':'채널 준비 상태를 조회하지 못했습니다.');
   let value;try{value=await response.json();}catch{value=null;}
   if(token!==generation)return;
   if(!exact(value,['account_id','channels'])||value.account_id!==mine||!Array.isArray(value.channels)||value.channels.length>40||!value.channels.every(r=>validRow(r,mine)))throw new Error('채널 준비 상태 응답의 계정과 형식을 확인할 수 없습니다.');
   rows=value.channels.map(r=>Object.fromEntries(FIELDS.map(k=>[k,k==='next_actions'?[...r[k]]:r[k]])));loaded=true;message='저장된 채널 준비 상태를 조회했습니다. 관리 웹의 실제 발행은 꺼져 있습니다.';
  }catch(e){if(token===generation){rows=[];loaded=false;message=e.message;}}finally{if(token===generation){busy=false;paint();onChange();}}
 }
 root.addEventListener('toggle',()=>{if(root.open&&account&&!loaded&&!busy)return load();});paint();
 return {element:root,isDirty:()=>false,isBusy:()=>busy,discardChanges(){},refreshControls(){},open(value){const next=validAccount(value)?value:null;if(next===account)return Promise.resolve();generation++;account=next;rows=[];loaded=false;busy=false;message='';root.open=false;paint();onChange();return Promise.resolve();}};
}
