// 공개 검증된 등록 게시물만 명시 수집한다. 자동 수집·재시도·폴링은 없다.
const TARGET_KEYS=['delivery_id','content_id','content_revision','owner_account_id','destination_account_id','platform','connection_id','target_id','remote_id','verified_at','title'];
const exact=(v,keys)=>!!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const accountId=a=>['all','personal','dept'].includes(a);
const realAccount=a=>['personal','dept'].includes(a);
const text=v=>typeof v==='string'&&v.length>0&&v.length<=2000;
const time=v=>text(v)&&Number.isFinite(Date.parse(v));
const validTarget=(r,a)=>exact(r,TARGET_KEYS)&&['delivery_id','content_id','platform','connection_id','target_id','remote_id'].every(k=>text(r[k]))&&typeof r.title==='string'&&r.title.length<=2000&&Number.isInteger(r.content_revision)&&r.content_revision>0&&realAccount(r.owner_account_id)&&realAccount(r.destination_account_id)&&time(r.verified_at)&&(a==='all'||r.destination_account_id===a);
const validObservation=(o,r)=>!!o&&typeof o==='object'&&!Array.isArray(o)&&text(o.id)&&o.source_kind==='verified_delivery'&&['owner_account_id','destination_account_id','platform','connection_id','target_id','remote_id','delivery_id','content_id'].every(k=>o[k]===r[k])&&['ok','error','unsupported'].includes(o.status)&&(o.status!=='ok'||time(o.observed_at))&&!!o.values&&typeof o.values==='object'&&!Array.isArray(o.values)&&Object.values(o.values).every(v=>typeof v==='number'&&Number.isFinite(v))&&(!Object.hasOwn(o.values,'views')||(Number.isFinite(o.values.views)&&o.values.views>=0));
const invalid=()=>Object.assign(new Error('invalid'),{kind:'invalid'});
export function createMetricsCollectionPanel({document,fetcher=globalThis.fetch,onChange=()=>{},onCollected=()=>{},requestTimeoutMs=45000}={}){
 const root=document.createElement('details');root.className='panel metrics-collection';
 let account=null,writable=false,loaded=false,enabled=false,items=[],selected='',pending=null,message='',generation=0,uncertain=false;
 const dirty=()=>selected!=='';
 const target=()=>items.find(r=>r.delivery_id===selected);
 const canCollect=()=>!!account&&writable&&loaded&&enabled&&pending===null&&!uncertain&&!!target();
 const node=(tag,attrs={},value)=>{const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='disabled')n.disabled=v;else n.setAttribute(k,String(v));}if(value!==undefined)n.textContent=value;return n;};
 function controls(){const s=root.querySelector('[data-metrics-collection-field="delivery"]');if(s)s.disabled=!writable||pending!==null;for(const n of root.querySelectorAll('[data-metrics-collection-action]')){const action=n.getAttribute('data-metrics-collection-action');n.disabled=action==='collect'?!canCollect():action==='discard'?pending!==null:!account||pending!==null;}}
 function paint(){
  const body=node('div',{class:'panel-body'});body.append(node('p',{},`${account==='personal'?'개인':account==='dept'?'학과':'전체'} 계정 · 공개 검증된 게시물을 선택한 뒤 수집 버튼을 누르세요. 조회만으로 외부 성과를 수집하지 않습니다.`));
  if(loaded){
   const s=node('select',{'aria-label':'성과 수집 게시물','data-metrics-collection-field':'delivery'});s.append(node('option',{value:''},'게시물 선택'));
   for(const r of items)s.append(node('option',{value:r.delivery_id},`${r.title||'제목 없음'} · ${r.destination_account_id==='personal'?'개인':'학과'} / ${r.platform}`));s.value=selected;
   s.addEventListener('change',()=>{if(!writable||pending!==null)return;selected=items.some(r=>r.delivery_id===s.value)?s.value:'';controls();onChange();});body.append(s);
   if(!items.length)body.append(node('p',{class:'sub'},'수집 가능한 공개 검증 게시물이 없습니다.'));
   if(!enabled)body.append(node('p',{class:'sub'},'성과 수집 실행이 비활성 상태입니다.'));
   const collect=node('button',{type:'button',class:'btn btn-small','data-metrics-collection-action':'collect'},pending==='collecting'?'수집 중…':'선택 게시물 성과 수집');collect.addEventListener('click',collectSelected);body.append(collect);
   const discard=node('button',{type:'button',class:'btn btn-small','data-metrics-collection-action':'discard'},'선택 해제');discard.addEventListener('click',discardChanges);body.append(discard);
  }
  const reload=node('button',{type:'button',class:'btn btn-small','data-metrics-collection-action':'reload'},'대상 다시 조회');reload.addEventListener('click',load);body.append(reload,node('p',{role:'status'},message));root.replaceChildren(node('summary',{},'공개 게시물 성과 수집'),body);controls();
 }
 async function send(url,method,body){
  const controller=new AbortController();let timer;const wait=Number.isFinite(requestTimeoutMs)&&requestTimeoutMs>0&&requestTimeoutMs<=120000?requestTimeoutMs:45000;
  try{const operation=(async()=>{let response;try{response=await fetcher(url,{method,credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});}catch{throw Object.assign(new Error('network'),{kind:'network'});}if(!response.ok)throw Object.assign(new Error('http'),{kind:'http',status:response.status});try{return await response.json();}catch{throw invalid();}})();const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(Object.assign(new Error('timeout'),{kind:'timeout'}));},wait);});return await Promise.race([operation,deadline]);}finally{clearTimeout(timer);}
 }
 function failure(e){return e.kind==='invalid'?'성과 응답의 형식을 확인할 수 없습니다. 선택은 보존했습니다.':e.kind==='http'&&e.status===401?'로그인 후 다시 시도하세요. 선택은 보존했습니다.':e.kind==='http'&&e.status===409?'게시물 상태가 바뀌었습니다. 선택을 보존했습니다. 대상을 다시 조회하세요.':e.kind==='http'&&e.status===503?'성과 수집 서비스를 사용할 수 없습니다. 선택은 보존했습니다.':'수집 응답을 확인하지 못했습니다. 선택은 보존했습니다. 대상을 다시 조회해 확인한 뒤 명시적으로 요청하세요.';}
 async function load(){
  if(!account||pending!==null)return;const mine=account,token=++generation;pending='loading';message='수집 대상 조회 중';paint();onChange();
  try{const row=await send('/api/v2/metrics/collection-targets?account='+mine,'GET');if(token!==generation)return;if(!exact(row,['account_id','execution_enabled','items'])||row.account_id!==mine||typeof row.execution_enabled!=='boolean'||!Array.isArray(row.items)||!row.items.every(r=>validTarget(r,mine))||new Set(row.items.map(r=>r.delivery_id)).size!==row.items.length)throw invalid();items=row.items.map(r=>Object.fromEntries(TARGET_KEYS.map(k=>[k,r[k]])));enabled=row.execution_enabled;loaded=true;uncertain=false;if(!target())selected='';message='수집 대상을 조회했습니다. 아직 외부 성과를 수집하지 않았습니다.';}catch(e){if(token===generation){enabled=false;message=e.kind==='invalid'?'수집 대상 응답의 계정과 형식을 확인할 수 없습니다. 선택은 보존했습니다.':failure(e);}}finally{if(token===generation){pending=null;paint();onChange();}}
 }
 async function collectSelected(){
  if(!canCollect())return;const mine=account,row={...target()},token=++generation;pending='collecting';message='선택 게시물 성과 수집 중';paint();onChange();let collected=null;
  try{const result=await send('/api/v2/metrics/collect','POST',{delivery_id:row.delivery_id});if(token!==generation)return;if(!exact(result,['observation'])||!validObservation(result.observation,row))throw invalid();const observation=result.observation;collected={id:observation.id,source_kind:'verified_delivery',...Object.fromEntries(['owner_account_id','destination_account_id','platform','connection_id','target_id','remote_id','delivery_id','content_id'].map(k=>[k,observation[k]])),status:observation.status,observed_at:observation.observed_at,values:Object.hasOwn(observation.values,'views')?{views:observation.values.views}:{}};selected='';message=observation.status==='ok'?`성과를 저장했습니다.${Object.hasOwn(observation.values,'views')?' 조회수 '+String(observation.values.views):''}`:'수집 결과를 저장했습니다. 해당 채널의 지표 지원 상태를 성과 목록에서 확인하세요.';}catch(e){if(token===generation){uncertain=['network','timeout','invalid'].includes(e.kind);message=e.kind==='invalid'?'성과 응답의 게시물·계정·형식을 확인할 수 없습니다. 선택은 보존했습니다. 대상을 다시 조회하세요.':failure(e);}}finally{if(token===generation){pending=null;paint();onChange();if(collected&&mine===account){try{onCollected(collected);}catch{}}}}
 }
 function discardChanges(){if(pending!==null)return;selected='';paint();onChange();}
 root.addEventListener('toggle',()=>{if(root.open&&account&&!loaded&&pending===null)return load();});paint();
 return {element:root,isBusy:()=>pending!==null,isDirty:dirty,discardChanges,refreshControls(options={}){if(options.writable!==undefined)writable=options.writable===true;controls();},open(value,{writable:w=true}={}){writable=w===true;const next=accountId(value)?value:null;if(next===account){controls();return Promise.resolve();}generation++;account=next;loaded=enabled=false;items=[];selected='';pending=null;message='';uncertain=false;root.open=false;paint();onChange();return Promise.resolve();}};
}
