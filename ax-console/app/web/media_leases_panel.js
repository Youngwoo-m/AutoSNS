// 전달용 임대의 최소 관리 정보만 표시한다. URL·토큰·발행 영수증은 받지 않는다.
const FIELDS=['lease_id','owner_account_id','destination_account_id','connection_id','content_id','content_revision','asset_id','asset_sha256','asset_size','media_type','expires_at','status'];
const LABELS={active:'전달 가능',expired:'기간 만료',revoked:'전달 중지',purged:'로컬 자료 정리됨'};
const exact=(v,keys)=>!!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const realAccount=v=>v==='personal'||v==='dept';
const text=(v,max=300)=>typeof v==='string'&&v.length>0&&v.length<=max;
const digest=v=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
const positive=v=>Number.isSafeInteger(v)&&v>0;
const validRow=(r,account)=>exact(r,FIELDS)&&digest(r.lease_id)&&realAccount(r.owner_account_id)&&r.destination_account_id===account&&text(r.connection_id)&&text(r.content_id)&&positive(r.content_revision)&&text(r.asset_id)&&digest(r.asset_sha256)&&positive(r.asset_size)&&['image/jpeg','video/mp4'].includes(r.media_type)&&text(r.expires_at,80)&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(r.expires_at)&&Number.isFinite(Date.parse(r.expires_at))&&Object.hasOwn(LABELS,r.status);
const accountLabel=a=>a==='personal'?'개인':'학과';
export function createMediaLeasesPanel({document,fetcher=globalThis.fetch,onChange=()=>{}}={}){
 const root=document.createElement('details');root.className='panel media-leases';
 let account=null,rows=[],loaded=false,busy=false,message='',generation=0;
 const node=(tag,attrs={},value)=>{const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='disabled')n.disabled=v;else n.setAttribute(k,String(v));}if(value!==undefined)n.textContent=value;return n;};
 function paint(){
  const body=node('div',{class:'panel-body'});
  body.append(node('p',{},'전달 중지는 이후 다운로드를 차단합니다. 이미 내려받은 원격 복사본을 삭제하지는 않습니다.'));
  if(loaded){
   if(!rows.length)body.append(node('p',{class:'sub'},'조회된 전달용 미디어가 없습니다.'));
   for(const row of rows){
    const card=node('section',{'data-media-lease-id':row.lease_id});
    card.append(node('h4',{},row.asset_id));
    const dl=node('dl');
    for(const [label,value] of [['원본 계정',accountLabel(row.owner_account_id)],['전달 대상 계정',accountLabel(row.destination_account_id)],['자산',row.asset_id],['크기',`${row.asset_size} 바이트`],['만료',row.expires_at],['상태',LABELS[row.status]]])dl.append(node('dt',{},label),node('dd',{},value));
    card.append(dl);
    if(row.status==='active'){
     const revoke=node('button',{type:'button',class:'btn btn-small','data-media-leases-action':'revoke',disabled:busy},'전달 중지');
     revoke.addEventListener('click',()=>request(row.lease_id));card.append(revoke);
    }
    body.append(card);
   }
  }else if(!busy)body.append(node('p',{class:'sub'},'패널을 펼치면 전달 현황을 조회합니다.'));
  const reload=node('button',{type:'button',class:'btn btn-small','data-media-leases-action':'reload',disabled:busy||!account},'현황 다시 조회');
  reload.addEventListener('click',()=>request());body.append(reload,node('p',{role:'status'},message));
  root.replaceChildren(node('summary',{},'전달용 미디어 현황'),body);
 }
 async function request(leaseId=null){
  if(!account||busy)return;
  if(leaseId!==null&&!rows.some(r=>r.lease_id===leaseId&&r.status==='active'))return;
  const mine=account,token=++generation;busy=true;message=leaseId?'전달 중지 처리 중':'전달 현황 조회 중';paint();onChange();
  try{
   let response;
   try{response=await fetcher(leaseId?`/api/v2/media-leases/${leaseId}/revoke`:`/api/v2/media-leases?account=${mine}`,leaseId?{method:'POST',credentials:'same-origin',headers:{Accept:'application/json','Content-Type':'application/json'},body:JSON.stringify({account_id:mine})}:{method:'GET',credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});}catch{throw new Error('전달 현황 서버에 연결하지 못했습니다.');}
   if(token!==generation)return;
   if(!response.ok)throw new Error(response.status===401?'로그인 후 다시 조회하세요.':'전달 현황 요청을 처리하지 못했습니다.');
   let value;try{value=await response.json();}catch{value=null;}
   if(token!==generation)return;
   if(!exact(value,['account_id','items'])||value.account_id!==mine||!Array.isArray(value.items)||value.items.length>1000||!value.items.every(r=>validRow(r,mine))||new Set(value.items.map(r=>r.lease_id)).size!==value.items.length)throw new Error('전달 현황 응답의 계정과 형식을 확인할 수 없습니다.');
   rows=value.items.map(r=>Object.fromEntries(FIELDS.map(k=>[k,r[k]])));loaded=true;message=leaseId?'전달 중지 요청을 처리했습니다.':'전달 현황을 조회했습니다.';
  }catch(error){if(token===generation){rows=[];loaded=false;message=error.message;}}finally{if(token===generation){busy=false;paint();onChange();}}
 }
 root.addEventListener('toggle',()=>{if(root.open&&account&&!loaded&&!busy)return request();});paint();
 return {element:root,isDirty:()=>false,isBusy:()=>busy,discardChanges(){},refreshControls(){},open(value){const next=realAccount(value)?value:null;if(next===account)return Promise.resolve();generation++;account=next;rows=[];loaded=false;busy=false;message='';root.open=false;paint();onChange();return Promise.resolve();}};
}
