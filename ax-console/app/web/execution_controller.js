import {renderExecutionPanel,bindExecutionPanel} from './execution_panel.js';

const reasons={execution_disabled:'서버 실행 정책이 비활성입니다.',execution_service_unavailable:'실행 서비스 미연결',job_disabled:'작업 비활성',legacy_owner:'기존 자동 작업 소유',unknown_executor:'실행기 미등록',media_evidence_required:'매체 게시 근거 확인 필요',quota_exceeded:'한도 초과',needs_auth:'로그인 필요',needs_review:'독립 검토 필요'};
const reason=value=>reasons[value]||'현재 실행 조건을 확인할 수 없습니다.';
const dirty=state=>!!state.busy||!!state.draft?.publication_confirmed||Object.values(state.pending||{}).some(Boolean);
const empty=mode=>({mode,enabled:false,capabilities:{},run:null,delivery:null,draft:{publication_confirmed:false},pending:{}});

/** Server discovery + two independent request sessions. Never invent a job, auth proof, or production binding. */
export function createExecutionWorkspace({api,contentApi,document=globalThis.document,onChange=()=>{},onOpenOutput=()=>{},clock=()=>new Date()}={}) {
  let metadata=null,error=null,loading=false,loadVersion=0,statusRoot=null;
  const records=new Map(),listeners=new Set();
  const blockedRecord=r=>dirty(r.production)||dirty(r.publication)||r.loadingPlans;
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);return n;};
  const notify=()=>{if(statusRoot)renderStatus();for(const callback of listeners)callback();onChange();};
  const busy=()=>[...records.values()].some(r=>r.loadingPlans||r.production.busy||r.publication.busy);
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
    const blocked=dirty(r.production)||dirty(r.publication)||r.loadingPlans;
    for(const mode of ['production','publication']) {
      const section=node('section');section.className=`execution-${mode}`;section.append(node('h4',mode==='production'?'선택 원고 제작':'대상별 별도 발행'));
      if(mode==='publication') {
        section.append(button('배포 계획 다시 조회',()=>loadPlans(r),blocked));
        selection(section,'planned_delivery','배포 계획',r.plans.map(plan=>[plan.id,`${plan.connection_id} · 원고 버전 ${plan.revision} · 계획 버전 ${plan.version}`]),r.plan?.id,id=>{
          if(blockedRecord(r))return;r.plan=r.plans.find(plan=>plan.id===id)||null;r.publication=empty('publication');
          if(r.plan)r.publication.delivery={id:r.plan.id,version:r.plan.version,plan_version:r.plan.version,content_revision:r.plan.revision,connection_id:r.plan.connection_id,state:r.plan.status};
          r.publicationJob='';paint(r);notify();
        },blocked);
      }
      selection(section,`${mode}_job`,mode==='production'?'제작 작업':'발행 작업',jobs(r,mode).map(job=>[job.id,`${job.label||job.id}${job.available?'':` · ${reason(job.reason)}`}`]),r[`${mode}Job`],id=>{
        if(blockedRecord(r))return;r[`${mode}Job`]=jobs(r,mode).some(job=>job.id===id)?id:'';
        const s=r[mode];s.trigger=r[`${mode}Job`]?{job_id:id,scheduled_at_utc:clock().toISOString(),phase:mode==='production'?'prepare':'submit',source:'console',request_kind:'new_publication',mode:'live'}:null;paint(r);notify();
      },blocked);
      const s=r[mode];sync(r,s,mode);const panel=renderExecutionPanel(s,{document});
      r.cleanups.push(bindExecutionPanel(panel,{request:body=>api.request(body),getRun:id=>api.getRun(id),observe:(id,body)=>api.observe(id,body),admit:(id,body)=>api.admit(id,body),approve:(id,body)=>api.approve(id,body),onChange:()=>{for(const control of r.controls)control.disabled=blockedRecord(r);updateOutput(r);notify();}}));
      for(const element of section.children)if(element.tagName?.toLowerCase()==='label')for(const child of element.children)if(child.tagName?.toLowerCase()==='select')r.controls.push(child);
      section.append(panel);root.append(section);
    }
    r.output=node('div');root.append(r.output);updateOutput(r);
  }
  function updateOutput(r) {
    if(!r.output)return;r.output.replaceChildren();
    const production=r.production.run?.production;
    if(production?.status==='completed'&&production.content_id&&Number.isSafeInteger(production.revision))r.output.append(button('제작 산출 버전 열기',()=>onOpenOutput(production.content_id,production.revision),blockedRecord(r)));
  }
  async function loadPlans(r) {
    if(r.loadingPlans||dirty(r.production)||dirty(r.publication))return;
    r.loadingPlans=true;notify();
    try {
      const data=await contentApi.listDeliveries('all',r.content.id);
      r.plans=(data.items||[]).filter(plan=>plan.content_id===r.content.id&&plan.revision===r.content.revision&&plan.manifest_hash===r.content.manifest_hash&&plan.status!=='cancelled');r.planError=null;
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
    if(!records.has(key))records.set(key,{key,content,dirty:changed,readOnly,production:empty('production'),publication:empty('publication'),productionJob:'',publicationJob:'',plans:[],plan:null,cleanups:[],root:node('section')});
    const r=records.get(key);r.content=content;r.dirty=changed;r.readOnly=readOnly;r.production.content_dirty=r.publication.content_dirty=changed||readOnly;paint(r);return r.root;
  }
  function renderStatus() {
    const root=statusRoot||(statusRoot=node('section'));root.replaceChildren();root.className='execution-service';root.append(node('h2','실행 서비스와 접수 결과'));
    root.append(node('p',error?error.status===401?'인증이 만료되었습니다. 입력과 요청을 보존했습니다.':'실행 서비스 조회 실패 · 입력과 요청을 보존했습니다.':metadata?.service_available?'서버 실행 서비스 등록됨':'실행 서비스 미연결'));
    root.append(node('p',metadata?.execution_enabled?'실행 정책 활성 · 대상별 별도 승인 필요':'실행 정책 기본 비활성'));
    if(error?.status===401){const link=node('a','새 창에서 다시 로그인');link.setAttribute('href','/login');link.setAttribute('target','_blank');link.setAttribute('rel','noopener noreferrer');root.append(link);}
    root.append(button('실행 서비스 다시 조회',load,loading||busy()));
    for(const code of metadata?.blockers||[])root.append(node('p',reason(code)));
    for(const r of records.values())for(const mode of ['production','publication'])if(r[mode].run||Object.values(r[mode].pending).some(Boolean)){const s=r[mode];const view=renderExecutionPanel({...s,enabled:false,disabled_reason:'원고 상세에서 실행 결과와 승인 입력을 확인하세요.',capabilities:{}},{document});root.append(node('h3',`${r.content.title} · ${mode==='production'?'제작':'발행'} 회차`),view,button('원고 상세에서 확인',()=>onOpenOutput(r.content.id,r.content.revision),busy()));}
    return root;
  }
  return {subscribe:callback=>{listeners.add(callback);return ()=>listeners.delete(callback);},load,forContent,renderStatus,isBusy:busy,isDirty:()=>[...records.values()].some(r=>dirty(r.production)||dirty(r.publication)),openFromOperation:row=>{if(row.content_id&&row.content_revision)onOpenOutput(row.content_id,row.content_revision);},refreshContentControls:(content,options)=>forContent(content,options)};
}
