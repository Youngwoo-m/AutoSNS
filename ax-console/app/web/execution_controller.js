import {renderExecutionPanel,bindExecutionPanel} from './execution_panel.js';

const reasons={execution_disabled:'서버 실행 정책이 비활성입니다.',execution_service_unavailable:'실행 서비스 미연결',job_disabled:'작업 비활성',legacy_owner:'기존 자동 작업 소유',unknown_executor:'실행기 미등록',media_evidence_required:'매체 게시 근거 확인 필요',quota_exceeded:'한도 초과',needs_auth:'로그인 필요',needs_review:'독립 검토 필요'};
const reason=value=>reasons[value]||'현재 실행 조건을 확인할 수 없습니다.';
const dirty=state=>!!state.busy||!!state.draft?.publication_confirmed||Object.values(state.pending||{}).some(Boolean);
const copy=value=>JSON.parse(JSON.stringify(value));
const labels={request:'제작 요청',observe:'대상 읽기 점검',admit:'발행 의도 확인',approve:'별도 발행 승인'};
const pick=(row,keys)=>Object.fromEntries(keys.filter(key=>row?.[key]!==undefined).map(key=>[key,row[key]]));
const planSnapshot=row=>pick(row,['id','content_id','revision','manifest_hash','connection_id','owner_account_id','destination_account_id','version','status']);
const deliverySnapshot=row=>pick(row,['id','version','run_id','context_hash','state','execution_state','remote_id','remote_uncertain']);
const token=(s,action)=>JSON.stringify([s.pending[action],s.pending_errors?.[action]?.attempt,s.read_generation||0]);
const uncertain=(run,delivery)=>['unknown','submitting','submitted','running'].includes(run?.state)||!!delivery?.remote_id||delivery?.remote_uncertain===true||['unknown','uploaded','published','scheduled','verified','submitting'].includes(delivery?.state||delivery?.execution_state);
const empty=mode=>({mode,enabled:false,capabilities:{},run:null,delivery:null,draft:{publication_confirmed:false},pending:{}});

/** Server discovery + two independent request sessions. Never invent a job, auth proof, or production binding. */
export function createExecutionWorkspace({api,contentApi,document=globalThis.document,onChange=()=>{},onOpenOutput=()=>{},clock=()=>new Date()}={}) {
  let metadata=null,error=null,loading=false,loadVersion=0,statusRoot=null;
  const records=new Map(),listeners=new Set();
  const blockedRecord=r=>dirty(r.production)||dirty(r.publication)||r.loadingPlans||r.loadingReview;
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n;};
  const notify=()=>{if(statusRoot)renderStatus();for(const callback of listeners)callback();onChange();};
  const busy=()=>[...records.values()].some(r=>r.loadingReview||r.loadingPlans||r.production.busy||r.publication.busy);
  const jobs=(r,mode)=>{
    const source=mode==='production'?metadata?.production_jobs:metadata?.publication_jobs;
    return (source||[]).filter(job=>job.owner_account_id===r.content.owner_account_id&&(mode==='production'||!r.plan||job.connection_ids?.includes(r.plan.connection_id)));
  };
  function sync(r,s,mode) {
    s.content=r.content;s.content_dirty=r.dirty||r.readOnly;s.enabled=metadata?.execution_enabled===true&&metadata?.service_available===true&&!error;
    const selected=jobs(r,mode).find(job=>job.id===r[`${mode}Job`]);
    const available=s.enabled&&selected?.available===true&&selected?.enabled===true;
    const why=error?error.status===401?'인증을 갱신하고 다시 조회하세요. 입력·요청은 보존했습니다.':'실행 서비스를 사용할 수 없습니다.':!selected?'등록된 작업을 직접 선택하세요.':reason(selected.reason||metadata?.blockers?.[0]);
    s.disabled_reason=why;
    s.capabilities=Object.fromEntries(['request','observe','admit','approve'].map(action=>[action,{available:available&&metadata?.capabilities?.[action]===true&&(mode==='production'?action==='request':!!r.plan),reason:why}]));
    s.capabilities.refresh={available:metadata?.service_available===true&&!error,reason:why};
    if(s.mode==='publication'&&!r.plan)s.capabilities.request={available:false,reason:'저장된 배포 계획을 직접 선택하세요.'};
    s.error=error?{status:error.status}:s.error;
  }
  function selection(root,name,label,rows,value,change,disabled=false) {
    const wrap=node('label',label);const select=node('select');select.name=name;select.disabled=disabled;
    for(const [id,text] of [['','직접 선택'],...rows]){const option=node('option',text);option.value=id;select.append(option);}
    select.value=value||'';select.addEventListener('change',()=>change(select.value));wrap.append(select);root.append(wrap);
  }
  function button(label,callback,disabled=false){const n=node('button',label);n.type='button';n.disabled=disabled;n.addEventListener('click',callback);return n;}
  function paint(r) {
    if(r.production.busy||r.publication.busy)return; // The binder retains active requests and keyboard focus.
    for(const cleanup of r.cleanups)cleanup();r.cleanups=[];
    const root=r.root;r.controls=[];root.replaceChildren(node('h3','제작과 대상별 발행 실행'),node('p','등록된 작업과 저장된 배포 계획을 직접 선택하세요. 기획 승인은 공개 발행 승인이 아닙니다.'));
    const unavailable=metadata?.blockers||['execution_service_unavailable'];for(const code of unavailable)root.append(node('p',reason(code)));
    const blocked=dirty(r.production)||dirty(r.publication)||r.loadingPlans||r.loadingReview;
    for(const mode of ['production','publication']) {
      const section=node('section');section.className=`execution-${mode}`;section.append(node('h4',mode==='production'?'선택 원고 제작':'대상별 별도 발행'));
      if(mode==='publication') {
        section.append(button('배포 계획 다시 조회',()=>loadPlans(r),r.loadingPlans||r.loadingReview||r.production.busy||r.publication.busy));
        if(r.plan)section.append(node('p',`현재 선택 계획 버전: ${r.plan.version}`));
        const readPlan=r.latestPlans?.find(plan=>plan.id===r.plan?.id);
        if(readPlan)section.append(node('p',`조회된 최신 계획 버전: ${readPlan.version} · 현재 선택과 보존 요청은 바꾸지 않았습니다.`));
        selection(section,'planned_delivery','배포 계획',r.plans.map(plan=>[plan.id,`${plan.connection_id} · 원고 버전 ${plan.revision} · 계획 버전 ${plan.version}`]),r.plan?.id,id=>{
          if(blockedRecord(r))return;r.plan=r.plans.find(plan=>plan.id===id)||null;r.publication=empty('publication');
          if(r.plan)r.publication.delivery={id:r.plan.id,version:r.plan.version,plan_version:r.plan.version,content_revision:r.plan.revision,connection_id:r.plan.connection_id,state:r.plan.status};
          r.publication.recovery_blocked=r.blockedPlans.has(r.plan?.id);r.publicationJob='';paint(r);notify();
        },blocked);
      }
      selection(section,`${mode}_job`,mode==='production'?'제작 작업':'발행 작업',jobs(r,mode).map(job=>[job.id,`${job.label||job.id}${job.available?'':` · ${reason(job.reason)}`}`]),r[`${mode}Job`],id=>{
        if(blockedRecord(r))return;r[`${mode}Job`]=jobs(r,mode).some(job=>job.id===id)?id:'';
        const s=r[mode];s.trigger=r[`${mode}Job`]?{job_id:id,scheduled_at_utc:clock().toISOString(),phase:mode==='production'?'prepare':'submit',source:'console',request_kind:'new_publication',mode:'live'}:null;paint(r);notify();
      },blocked);
      const s=r[mode];sync(r,s,mode);const panel=renderExecutionPanel(s,{document});
      r.cleanups.push(bindExecutionPanel(panel,{request:body=>api.request(body),getRun:id=>api.getRun(id),observe:(id,body)=>api.observe(id,body),admit:(id,body)=>api.admit(id,body),approve:(id,body)=>api.approve(id,body),onChange:()=>{for(const control of r.controls)control.disabled=blockedRecord(r);updateOutput(r);renderRecovery(r,mode);notify();}}));
      for(const element of section.children)if(element.tagName?.toLowerCase()==='label')for(const child of element.children)if(child.tagName?.toLowerCase()==='select')r.controls.push(child);
      section.append(panel);
      r.recoverySlots[mode]=node('div');section.append(r.recoverySlots[mode]);renderRecovery(r,mode);root.append(section);
    }
    r.output=node('div');root.append(r.output);updateOutput(r);
  }
  function updateOutput(r) {
    if(!r.output)return;r.output.replaceChildren();
    const production=r.production.run?.production;
    if(production?.status==='completed'&&production.content_id&&Number.isSafeInteger(production.revision))r.output.append(button('제작 산출 버전 열기',()=>onOpenOutput(production.content_id,production.revision),blockedRecord(r)));
  }
  function renderRecovery(r,mode) {
    const slot=r.recoverySlots[mode];if(!slot)return;slot.replaceChildren();const s=r[mode];r.closeChecks??={};
    if(s.recovery_blocked)slot.append(node('p','게시 여부가 불확실하거나 최신 원고 선택이 필요합니다. 로컬 요청 정리는 원격 취소나 새 게시 허가가 아닙니다.'));
    for(const [action,pending] of Object.entries(s.pending))if(pending) {
      const label=labels[action];const box=node('section');box.append(node('h5',`${label} 보존 요청 검토`),node('p','처리 상태를 읽기 조회해 확인하세요. 기존 본문·CAS·요청키는 조회로 바꾸지 않습니다.'));
      box.append(button(`${label} 처리 상태 조회`,()=>inspectPending(r,mode,action),busy()));
      const review=r.reviews[mode][action];const fresh=review?.token===token(s,action);
      if(review?.error){box.append(node('p','처리 상태 조회에 실패했습니다. 원래 요청과 입력을 보존했습니다.'));if(review.status===401){const login=node('a','새 창에서 다시 로그인');login.setAttribute('href','/login');login.setAttribute('target','_blank');login.setAttribute('rel','noopener noreferrer');box.append(login);}}
      if(fresh) {
        if(review.plan)box.append(node('p',`조회된 최신 계획 버전: ${review.plan.version}`));
        if(review.content)box.append(node('p',`조회된 최신 원고 버전: ${review.content.revision}`));
        box.append(node('p',review.delivery?`조회된 대상 실행: ${review.delivery.state||review.delivery.execution_state||'미확인'} · 버전 ${review.delivery.version}`:'현재 조회에서 대상 실행 기록을 찾지 못했습니다. 원격 미처리 확정을 뜻하지 않습니다.'));
      }
      if(s.pending_errors?.[action]?.status===409) {
        const wrap=node('label','충돌 요청을 로컬 종료하고 최신 조건으로 다시 검토합니다. 원격 취소·게시 허가가 아님을 확인했습니다.');
        const check=node('input');check.type='checkbox';check.name=`close_${mode}_${action}`;check.disabled=!fresh||busy();check.checked=fresh&&review.confirmed===true;
        r.closeChecks[check.name]=check;check.addEventListener('change',()=>{if(!fresh||busy())return;const focused=document.activeElement===check;review.confirmed=check.checked===true;renderRecovery(r,mode);if(focused)r.closeChecks[check.name]?.focus({preventScroll:true});});wrap.append(check);box.append(wrap);
        box.append(button(`${label} 충돌 요청 로컬 종료`,()=>closeConflict(r,mode,action),!fresh||review.confirmed!==true||busy()));
      } else box.append(node('p','인증 만료·503 등 결과 불확실 요청은 로컬 종료하지 않습니다. 같은 본문과 키로 처리 결과를 확인하세요.'));
      slot.append(box);
    }
    if(s.closed_requests?.length) {
      const detail=node('details');detail.append(node('summary','로컬 종료 이력 · 원래 요청 보존'));
      for(const entry of s.closed_requests) {
        const body=entry.request.body;detail.append(node('p',`${labels[entry.action]} · 충돌 요청의 로컬 기록만 종료`));
        if(body.expected_version!==undefined)detail.append(node('p',`원래 CAS: ${body.expected_version}`));
        if(body.expected_revision!==undefined)detail.append(node('p',`원래 원고 버전: ${body.expected_revision}`));
        if(body.request_key)detail.append(node('p',`이전 요청키: ${body.request_key}`));
      }slot.append(detail);
    }
    if(s.next_content)slot.append(button('최신 원고 버전 열어 재검토',()=>onOpenOutput(s.next_content.id,s.next_content.revision),busy()));
  }
  async function inspectPending(r,mode,action) {
    const s=r[mode];if(busy()||!s.pending[action])return;
    s.read_generation=(s.read_generation||0)+1;
    const expected=token(s,action);r.loadingReview=true;s.reviewing=true;paint(r);notify();
    try {
      let plan=null,content=null,run=null,delivery=null;
      if(mode==='publication') {
        const [freshPlan,freshRun]=await Promise.all([contentApi.getDelivery?contentApi.getDelivery(r.plan.id):contentApi.listDeliveries('all',r.content.id).then(data=>data.items.find(row=>row.id===r.plan.id)),api.getRun(s.run.run_id)]);
        if(!freshPlan||freshPlan.id!==r.plan.id||freshPlan.content_id!==r.content.id||!Number.isSafeInteger(freshPlan.version)||freshRun?.run_id!==s.run.run_id)throw new Error();
        plan=planSnapshot(freshPlan);run=pick(freshRun,['run_id','state','status']);delivery=deliverySnapshot((freshRun.deliveries||[]).find(row=>row.id===r.plan.id));
        if(!delivery.id)delivery=null;
        if(action==='approve'&&(!delivery||!Number.isSafeInteger(delivery.version)||typeof delivery.context_hash!=='string'||!delivery.context_hash))throw new Error();
      } else {
        const latest=await contentApi.getContent(r.content.id);
        if(latest?.id!==r.content.id||!Number.isSafeInteger(latest.revision)||latest.owner_account_id!==r.content.owner_account_id)throw new Error();
        content=pick(latest,['id','revision','manifest_hash','owner_account_id']);
      }
      if(token(s,action)===expected)r.reviews[mode][action]={token:expected,plan,content,run,delivery,confirmed:false};
    } catch(error) {r.reviews[mode][action]={error:true,status:error?.status};}
    finally{r.loadingReview=false;s.reviewing=false;paint(r);notify();}
  }
  function closeConflict(r,mode,action) {
    const s=r[mode],review=r.reviews[mode][action];
    if(busy()||s.pending_errors?.[action]?.status!==409||!review||review.token!==token(s,action)||review.confirmed!==true)return;
    const matching=s.run?.deliveries?.find(row=>row.id===s.delivery?.id);
    const latestDelivery=[review.delivery,s.latest_delivery,matching].filter(row=>row&&row.id===s.delivery?.id).sort((a,b)=>(b.version??-1)-(a.version??-1))[0];
    const latestPlan=[review.plan,...(r.latestPlans||[]).filter(row=>row.id===r.plan?.id)].filter(Boolean).sort((a,b)=>(b.version??-1)-(a.version??-1))[0];
    const unsafe=uncertain(review.run,review.delivery)||uncertain(s.run,s.latest_delivery)||uncertain(s.run,matching);
    s.closed_requests??=[];s.closed_requests.push({action,request:copy(s.pending[action]),status:409,review:copy(pick(review,['plan','content','run','delivery'])),latest_known:{read_generation:s.read_generation||0,...(latestDelivery?{delivery:copy(deliverySnapshot(latestDelivery))}:{})}});
    delete s.pending[action];delete s.pending_errors[action];delete r.reviews[mode][action];
    s.error=null;s.draft={publication_confirmed:false,confirmation_key:null};s.message='충돌 요청을 로컬 종료했습니다. 원래 요청은 이력에 보존했습니다. 원격 취소나 새 게시 허가가 아닙니다.';
    if(mode==='production') {
      s.recovery_blocked=true;s.next_content=review.content;s.trigger=null;r.productionJob='';
    } else {
      const latest=latestPlan,changed=latest.revision!==r.content.revision||latest.manifest_hash!==r.content.manifest_hash||latest.connection_id!==r.plan.connection_id;
      r.plan=latest;r.plans=r.plans.map(row=>row.id===latest.id?latest:row);
      s.delivery=(action==='approve'||unsafe&&latestDelivery)?{...s.delivery,...latestDelivery,plan_version:latest.version}:{id:latest.id,version:latest.version,plan_version:latest.version,run_id:s.run.run_id,state:latest.status};
      if(changed||latest.status==='cancelled'||unsafe) {
        s.recovery_blocked=true;r.blockedPlans.add(latest.id);
        if(changed)s.next_content={id:latest.content_id,revision:latest.revision};
      }
    }
    paint(r);notify();
  }
  async function loadPlans(r) {
    if(r.loadingPlans||r.loadingReview||r.production.busy||r.publication.busy)return;
    r.publication.read_generation=(r.publication.read_generation||0)+1;
    r.loadingPlans=true;renderRecovery(r,'publication');notify();
    try {
      const data=await contentApi.listDeliveries('all',r.content.id);
      r.latestPlans=(data.items||[]).filter(plan=>plan.content_id===r.content.id&&plan.revision===r.content.revision&&plan.manifest_hash===r.content.manifest_hash&&plan.status!=='cancelled').map(planSnapshot);
      if(!dirty(r.production)&&!dirty(r.publication))r.plans=r.latestPlans;
      r.planError=null;
    }catch(e){r.planError={status:e.status};r.publication.error={status:e.status};}
    finally{r.loadingPlans=false;paint(r);notify();}
  }
  async function load() {
    const version=++loadVersion;loading=true;notify();
    try {const value=await api.status();if(version!==loadVersion)return;if(!value||!Array.isArray(value.production_jobs)||!Array.isArray(value.publication_jobs)||typeof value.capabilities!=='object')throw Object.assign(new Error(),{status:503});metadata=value;error=null;}
    catch(e){if(version===loadVersion)error={status:e.status||503};}
    finally{if(version===loadVersion){loading=false;for(const r of records.values())paint(r);notify();}}
  }
  function forContent(content,{dirty:changed=false,readOnly=false}={}) {
    const key=`${content.id}:${content.revision}:${content.manifest_hash}`;
    if(!records.has(key))records.set(key,{key,content,dirty:changed,readOnly,production:empty('production'),publication:empty('publication'),productionJob:'',publicationJob:'',plans:[],plan:null,cleanups:[],recoverySlots:{},reviews:{production:{},publication:{}},blockedPlans:new Set(),root:node('section')});
    const r=records.get(key);r.content=content;r.dirty=changed;r.readOnly=readOnly;r.production.content_dirty=r.publication.content_dirty=changed||readOnly;paint(r);return r.root;
  }
  function renderStatus() {
    const root=statusRoot||(statusRoot=node('section'));root.replaceChildren();root.className='execution-service';root.append(node('h2','실행 서비스와 접수 결과'));
    root.append(node('p',error?error.status===401?'인증이 만료되었습니다. 입력과 요청을 보존했습니다.':'실행 서비스 조회 실패 · 입력과 요청을 보존했습니다.':metadata?.service_available?'서버 실행 서비스 등록됨':'실행 서비스 미연결'));
    root.append(node('p',metadata?.execution_enabled?'실행 정책 활성 · 대상별 별도 승인 필요':'실행 정책 기본 비활성'));
    if(error?.status===401){const link=node('a','새 창에서 다시 로그인');link.setAttribute('href','/login');link.setAttribute('target','_blank');link.setAttribute('rel','noopener noreferrer');root.append(link);}
    root.append(button('실행 서비스 다시 조회',load,loading||busy()));
    for(const code of metadata?.blockers||[])root.append(node('p',reason(code)));
    for(const r of records.values())for(const mode of ['production','publication'])if(r[mode].run||r[mode].closed_requests?.length||Object.values(r[mode].pending).some(Boolean)){const s=r[mode];const view=renderExecutionPanel({...s,enabled:false,disabled_reason:'원고 상세에서 실행 결과와 승인 입력을 확인하세요.',capabilities:{}},{document});root.append(node('h3',`${r.content.title} · ${mode==='production'?'제작':'발행'} 회차`),view,button('원고 상세에서 확인',()=>onOpenOutput(r.content.id,r.content.revision),busy()));}
    return root;
  }
  return {subscribe:callback=>{listeners.add(callback);return ()=>listeners.delete(callback);},load,forContent,renderStatus,isBusy:busy,isDirty:()=>[...records.values()].some(r=>dirty(r.production)||dirty(r.publication)),openFromOperation:row=>{if(row.content_id&&row.content_revision)onOpenOutput(row.content_id,row.content_revision);},refreshContentControls:(content,options)=>forContent(content,options)};
}
