import {accountLabel,formatDateTime,statusLabel} from './view_helpers.js';
import {createInstagramReviewPanel} from './instagram_review_panel.js';
export function deliveryPayload(content,draft,selectedConnection=null) {
  if(!draft.connection_id)throw new Error('등록된 대상 연결을 선택해 주세요.');
  if(!/^[a-zA-Z0-9][a-zA-Z0-9_.:-]{0,99}$/.test(draft.schedule_slot||''))throw new Error('일정 슬롯을 입력해 주세요. 영문·숫자·._:-, 최대 100자입니다.');
  const aware=value=>{if(!/T.*(?:Z|[+-]\d\d:\d\d)$/.test(value||'')||!Number.isFinite(Date.parse(value)))throw new Error('UTC 또는 시간대 offset을 포함한 ISO 시각을 입력해 주세요.');return value;};
  const scheduled_at=aware(draft.scheduled_at);
  const schedule_condition=draft.condition_kind==='window'?{kind:'window',from:aware(draft.window_from),to:aware(draft.window_to)}:{kind:'fixed',at:scheduled_at};
  const options={};if(draft.text_only===true)options.text_only=true;for(const key of ['visibility','title_override','description_override'])if(draft[key])options[key]=draft[key];
  const ids=draft.instagram_asset_ids??[],format=draft.instagram_format||'';
  if(!Array.isArray(ids))throw new Error('Instagram 자산 ID 순서를 확인해 주세요.');
  if(format||ids.length||selectedConnection?.platform==='instagram'){
    if(!['image','reels','carousel'].includes(format)||ids.some(id=>typeof id!=='string'||!id)||new Set(ids).size!==ids.length||(format==='carousel'?ids.length<2||ids.length>10:ids.length!==1))throw new Error('Instagram 게시 형식과 자산 개수를 확인해 주세요. 이미지·REELS는 1개, 캐러셀은 2~10개를 명시적으로 선택하세요.');
    for(const id of ids){const matches=(content.assets||[]).filter(a=>a.id===id);if(matches.length!==1||!['image/jpeg','video/mp4'].includes(matches[0].media_type)||(format==='image'&&matches[0].media_type!=='image/jpeg')||(format==='reels'&&matches[0].media_type!=='video/mp4'))throw new Error('선택한 Instagram 자산을 확인해 주세요. 이미지에는 JPEG, REELS에는 MP4가 필요하며 자동 변환하지 않습니다.');}
    options.instagram={format,asset_ids:[...ids]};
  }
  return {content_id:content.id,revision:content.revision,manifest_hash:content.manifest_hash,connection_id:draft.connection_id,publication_purpose:draft.publication_purpose||'initial',schedule_slot:draft.schedule_slot,scheduled_at,timezone:draft.timezone||'Asia/Seoul',schedule_condition,options,...(draft.crosspost_rule_id?{crosspost_rule_id:draft.crosspost_rule_id}:{})};
}
export const canApprove=plan=>Boolean(plan&&['pending','ready'].includes(plan.status)&&plan.target_status==='verified'&&plan.subject_hash&&!(plan.blockers||[]).length);
export const approvalPayload=(plan,decision,notes='')=>({expected_version:plan.version,subject_hash:plan.subject_hash,decision,notes});
export function schedulePayload(plan,draft,preview) {if(!preview?.preview_hash)throw new Error('먼저 일정 영향 미리보기를 확인해 주세요.');return {expected_version:plan.version,scheduled_at:draft.scheduled_at,timezone:draft.timezone,preview_hash:preview.preview_hash};}
export const scheduleImpactLabel=preview=>preview.approval_retained===true?'계획 승인 유지':'계획 재검토 필요';
export function approvalRecordLabel(plan) {
  const record=plan.approval;if(!record)return '계획 승인 기록 없음';
  const decision=({approved:'승인',rejected:'반려',revoked:'철회'}[record.decision]||'결정 미확인');
  const label=plan.status==='cancelled'?'취소 전 기록':record.decision==='approved'&&(record.subject_hash!==plan.subject_hash||plan.status!=='ready')?'이전 계획 승인 기록 · 현재 조건은 재검토 필요':record.decision==='approved'?'현재 계획 승인 기록':'계획 검토 기록';
  return `${label} · ${decision} · 원본 버전 ${record.content_revision} · ${formatDateTime(record.recorded_at)}`;
}
export const targetIdentityLabel=status=>status==='verified'?'대상 ID 확인':'대상 미확인 · 승인 불가';
const crossReasonLabel=reason=>({owner_mismatch:'원본 소유자 불일치',slot_not_allowed:'허용 슬롯 아님',trigger_not_met:'시작 조건 불충족',conditions_not_met:'교차 조건 불충족',ineligible:'교차 대상 제외',disabled:'규칙 중지',unknown:'활성 상태 미확인',observe_legacy:'기존 실행기 관측'}[reason]||'추가 조건 확인 필요');
const localTimeLabel=(value,zone)=>{if(!value)return '시각 미확인';try{return `${zonedScheduleValue(value,zone||'Asia/Seoul')} (${zone||'Asia/Seoul'})`;}catch{return '시각·시간대 확인 필요';}};
const xCostNotice='X API 비용 확인이 필요합니다. 비용 허용 전에는 실제 조회·발행을 실행하지 않습니다.';
const textOnlyNotice=platform=>platform==='x'?`X 텍스트 전용 · 원고의 이미지·영상은 이 배포에 포함하지 않습니다. ${xCostNotice}`:platform==='facebook'?'Facebook 페이지 텍스트 전용 · 개인 타임라인 게시가 아닙니다. 원고의 이미지·영상은 이 배포에 포함하지 않습니다.':platform==='threads'?'Threads 텍스트 전용 · 원고의 이미지·영상은 이 배포에 포함하지 않습니다.':'텍스트 전용 옵션 · 게시 대상 채널과 원본 자산 제외 여부를 다시 확인하세요.';
const instagramNotice=p=>`Instagram 게시 형식: ${({image:'이미지',reels:'REELS',carousel:'캐러셀'})[p.options?.instagram?.format]||'확인 필요'} · 선택 순서: ${(p.options?.instagram?.asset_ids||[]).join(' → ')} · 원본 중 선택한 자산만 배포 · 실제 실행 안 함`;
export function deliveryPreviewSummary(preview,context={}) {
  const p={...context,...preview},lines=[`원본 ${accountLabel(p.owner_account_id)} → 대상 ${accountLabel(p.destination_account_id)} · ${p.platform||'채널 미확인'} · ${p.target_label||'대상 이름 미확인'}`,`${targetIdentityLabel(p.target_status)} · 인증 미확인 (대상 ID 확인과 별개)`,`로컬 예정 시각: ${localTimeLabel(p.scheduled_at,p.timezone)}`,p.approval_retained===true?'계획 승인 유지':p.approval_retained===false?'계획 재검토 필요':'계획 승인 검토 필요','실행 안 함 · 원격 예약 변경 없음'];
  for(const blocker of p.blockers||[])lines.push(`차단: ${blocker.reason||blocker.message||'대상·정책 확인 필요'}`);
  for(const reason of p.reasons||[])lines.push(reason);
  for(const row of p.crossposts||[]) {
    const owner=row.delivery_owner==='legacy'?'기존 실행기 담당':row.delivery_owner==='managed'?'관리 실행기 담당':'실행 주인 미확인';
    const status=({observe_legacy:'기존 경로 관측만',ineligible:'교차 대상 제외',disabled:'규칙 중지',unknown:'활성 상태 미확인',planned:'로컬 교차 계획'}[row.status]||'상태 미확인');
    const delayOwner=({legacy_queue_add:'기존 대기열',queue_add:'대기열',managed:'관리 실행기',source:'원본 경로',none:'지연 없음'}[row.delay_owner]||'지연 주인 미확인');
    lines.push(`교차: ${accountLabel(row.owner_account_id)} → ${accountLabel(row.destination_account_id)} · ${row.platform||'채널 미확인'} · ${owner} · ${status} · ${(row.reasons||[]).map(crossReasonLabel).join(' · ')||'추가 제외 사유 없음'} · 계산 시각 ${localTimeLabel(row.not_before,row.window?.timezone||p.timezone)} · 지연 ${(row.delay_seconds||0)/60}분 (${delayOwner}) · 최소 간격 ${(row.min_gap_seconds||0)/60}분 · 실행 안 함`);
  }
  if(!(p.crossposts||[]).length)lines.push('해당하는 교차 경로 없음');
  if(p.options?.text_only===true)lines.push(textOnlyNotice(p.platform));
  if(p.platform==='instagram'&&p.options?.instagram)lines.push(instagramNotice(p));
  return lines;
}
export function zonedScheduleValue(value,timezone) {
  if(!value)return '';
  const parts=new Intl.DateTimeFormat('sv-SE',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23',timeZoneName:'longOffset'}).formatToParts(new Date(value));
  const get=type=>parts.find(part=>part.type===type)?.value;
  const offset=get('timeZoneName').replace('GMT','')||'+00:00';
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}:${get('second')}${offset}`;
}
export function createDeliverySession() {
  let generation=0;
  return {plan:null,items:[],draft:{},preview:null,phase:'idle',error:'',
    change(key,value){this.draft[key]=value;this.preview=null;},
    async load(id,request){const current=++generation;this.phase='loading';try{const data=await request(id);if(current!==generation)return false;this.items=data.items||[];this.phase='ready';return true;}catch(error){if(current!==generation)return false;this.phase='error';this.error=error.message;return false;}},
    async write(request){this.phase='saving';this.error='';try{const next=await request();this.plan=next;this.preview=null;this.phase='saved';return next;}catch(error){this.phase=error.status===409?'conflict':error.status===401?'unauthorized':'error';this.error=error.message;return null;}}
  };
}
const defaultDraft=()=>({connection_id:'',publication_purpose:'initial',schedule_slot:'main',scheduled_at:'',timezone:'Asia/Seoul',condition_kind:'fixed',window_from:'',window_to:'',visibility:'',title_override:'',description_override:'',text_only:false,instagram_format:'',instagram_asset_ids:[],crosspost_rule_id:''});
export function createDeliveryEditor({api,writable=()=>false,onSaved=()=>{},onStateChange=()=>{}}) {
  const root=document.createElement('section');root.className='editor-section delivery-editor';
  let content=null,connections=[],state=createDeliverySession(),busy=false,generation=0,events=[],dirty=false,loadFailed=false,scheduleDraft={scheduled_at:'',timezone:'Asia/Seoul'},notes='',baselines={create:'',schedule:'',notes:''};
  const snapshot=value=>JSON.stringify(value);
  function resetBaselines(){baselines={create:snapshot(state.draft),schedule:snapshot(scheduleDraft),notes};dirty=false;}
  function updateDirty(){dirty=snapshot(state.draft)!==baselines.create||snapshot(scheduleDraft)!==baselines.schedule||notes!==baselines.notes;}
  const el=(tag,attrs={},...children)=>{const node=document.createElement(tag);for(const [key,value]of Object.entries(attrs))if(key.startsWith('on'))node.addEventListener(key.slice(2),value);else if(key==='disabled')node.disabled=Boolean(value);else node.setAttribute(key,String(value));for(const child of children.flat(Infinity))if(child!=null)node.append(typeof child==='object'?child:document.createTextNode(String(child)));return node;};
  let rendering=false,reviewParentControls=new Map();
  const instagramReview=createInstagramReviewPanel({document,api,onChange:()=>{syncReviewParentControls();syncDraftControls();}});
  const parentBlocked=()=>busy||loadFailed||!writable();
  const reviewBlocks=()=>instagramReview.isDirty()||instagramReview.isBusy();
  const blocked=()=>parentBlocked()||(!rendering&&reviewBlocks());
  const contains=(parent,node)=>parent===node||Array.from(parent.children||[]).some(child=>contains(child,node));
  function syncReviewParentControls(){for(const [node,disabled] of reviewParentControls)node.disabled=disabled||parentBlocked()||reviewBlocks();}

  const button=(label,fn,disabled=false)=>el('button',{type:'button',class:'btn btn-small',disabled:blocked()||disabled,onclick:fn},label);
  function syncDraftControls(){root.querySelectorAll('[data-plan-navigation]').forEach(node=>node.disabled=blocked()||dirty);const discard=root.querySelector('[data-discard-plan]');if(discard){discard.hidden=!dirty&&state.phase!=='conflict';discard.disabled=busy||reviewBlocks();}const notice=root.querySelector('[data-plan-dirty]');if(notice)notice.textContent=reviewBlocks()?'Instagram 최종 구성 검토에 미저장 입력이나 처리 중 요청이 있습니다. 검토 저장 또는 입력 버리기 후 계획·원본을 변경하세요.':dirty?'배포 계획에 미저장 입력이 있습니다. 저장하거나 입력을 버린 뒤 원본을 변경하세요.':'';instagramReview.refreshControls({writable:!parentBlocked()&&!dirty});onStateChange();}
  function navigation(label,fn){const node=button(label,()=>{if(dirty||blocked())return;return fn();},dirty);node.setAttribute('data-plan-navigation','');return node;}
  function field(label,value,change,options=null){const input=el(options?'select':'input',{disabled:blocked(),oninput:e=>{if(blocked())return;change(e.target.value);updateDirty();syncDraftControls();}});if(options)for(const [id,text]of options)input.append(el('option',{value:id},text));input.value=value||'';return el('label',{class:'editor-field'},el('span',{},label),input);}
  const previewOutput=value=>el('div',{class:'delivery-preview-summary'},el('ul',{},deliveryPreviewSummary(value,state.plan||{...state.draft,owner_account_id:content.owner_account_id}).map(line=>el('li',{},line))),el('details',{},el('summary',{},'기술 세부 정보'),el('pre',{class:'delivery-json'},JSON.stringify(value,null,2))));
  async function act(task){if(blocked())return;const token=generation;busy=true;state.error='';render();try{await task();}catch(error){if(token===generation){state.error=error.message;state.phase=error.status===409?'conflict':'error';}}finally{if(token===generation){busy=false;render();}}}
  async function history(){if(state.plan){const response=await api.deliveryEvents(state.plan.id);events=response.items||[];}}
  async function save(request,group){const next=await state.write(request);if(next){if(group==='create'){baselines.create=snapshot(state.draft);scheduleDraft={scheduled_at:zonedScheduleValue(next.scheduled_at,next.timezone),timezone:next.timezone};baselines.schedule=snapshot(scheduleDraft);}if(group==='notes'){notes='';baselines.notes='';}if(group==='schedule'){scheduleDraft={scheduled_at:zonedScheduleValue(next.scheduled_at,next.timezone),timezone:next.timezone};baselines.schedule=snapshot(scheduleDraft);}updateDirty();await history();await reloadList();onSaved(next);}}
  async function reloadList(){const response=await api.listDeliveries('all',content.id);state.items=response.items||[];}
  async function select(plan){if(dirty||blocked())return;await act(async()=>{state.plan=await api.getDelivery(plan.id);state.preview=null;scheduleDraft={scheduled_at:zonedScheduleValue(state.plan.scheduled_at,state.plan.timezone),timezone:state.plan.timezone};notes='';resetBaselines();await history();});}
  function render(){
    const reviewActive=document.activeElement&&contains(instagramReview.element,document.activeElement)?document.activeElement:null;
    const reviewRange=reviewActive&&typeof reviewActive.selectionStart==='number'?[reviewActive.selectionStart,reviewActive.selectionEnd]:null;
    rendering=true;try{
    root.replaceChildren(el('h3',{},'배포 계획·계획 승인'),el('p',{class:'inline-note'},'로컬 계획만 저장합니다. 계획 승인은 실제 발행 승인이 아닙니다. 원격 예약·게시·로그인 검사는 실행하지 않습니다.'),el('p',{role:'status','aria-live':'polite',class:'editor-message'},state.error||(busy?'불러오는 중…':'')));
    if(state.phase==='unauthorized')root.append(el('a',{href:'/login',target:'_blank',rel:'noopener'},'다른 탭에서 로그인'));
    if(loadFailed){onStateChange();root.append(button('계획 다시 불러오기',()=>open(content),false));root.lastChild.disabled=busy;return;}
    if(!content){onStateChange();return;}
    root.append(el('p',{},`고정 원본: ${accountLabel(content.owner_account_id)} · 원본 버전 ${content.revision} · ${content.manifest_hash}`));
    const list=el('div',{class:'delivery-plan-list'});for(const item of state.items)list.append(navigation(`${item.target_label||item.platform} · 원본 버전 ${item.revision} · ${statusLabel(item.status)}`,()=>select(item)));
    root.append(list);if(!state.items.length)root.append(el('p',{class:'sub'},'저장된 로컬 배포 계획이 없습니다.'));
    const discard=el('button',{type:'button',class:'btn btn-small','data-discard-plan':'',onclick:()=>{if(!busy&&!reviewBlocks())return open(content);}},'입력 버리고 계획 다시 불러오기');root.append(el('p',{'data-plan-dirty':'',role:'status'}),discard);
    root.append(navigation('새 계획 작성',()=>{state.plan=null;state.preview=null;state.draft=defaultDraft();events=[];notes='';resetBaselines();render();}));
    if(!state.plan){
      const d=state.draft,selectedConnection=connections.find(item=>item.id===state.draft.connection_id),visibilityOptions=[['','기본값'],...['public','unlisted','private'].filter(value=>(selectedConnection?.capabilities||[]).includes(`visibility:${value}`)).map(value=>[value,({public:'공개',unlisted:'일부 공개',private:'비공개'})[value]])],change=key=>value=>{state.change(key,value);const saveButton=root.querySelector('[data-save-plan]');if(saveButton)saveButton.disabled=true;if(key==='connection_id'){d.visibility='';d.text_only=false;d.instagram_format='';d.instagram_asset_ids=[];render();}};
      root.append(field('실제 등록 연결 (도구 선호와 별개)',d.connection_id,change('connection_id'),[['','연결 선택'],...connections.filter(c=>c.planning_enabled).map(c=>[c.id,`${accountLabel(c.account_id)} · ${c.platform} · ${c.target_label||'대상 미확인'} · ${c.target_status==='verified'?'대상 ID 확인':'대상 미확인 · 승인 불가'} · 인증 ${c.auth_status}`])]),field('발행 목적',d.publication_purpose,change('publication_purpose'),[['initial','최초 계획'],['followup','후속'],['republication','재발행']]),field('일정 슬롯 (계획 생성 후 고정)',d.schedule_slot,change('schedule_slot')),field('예정 시각 (예: 2026-11-01T10:00:00+09:00)',d.scheduled_at,change('scheduled_at')),field('IANA 시간대',d.timezone,change('timezone')),field('허용 일정 조건',d.condition_kind,v=>{change('condition_kind')(v);render();},[['fixed','고정 시각'],['window','허용 범위 (시작 포함·끝 제외)']]));
      if(['threads','facebook','x'].includes(selectedConnection?.platform)&&(selectedConnection.capabilities||[]).includes('text_only')){
        const facebook=selectedConnection.platform==='facebook',x=selectedConnection.platform==='x';
        const box=el('input',{type:'checkbox',...(x?{'data-x-text-only':''}:facebook?{'data-facebook-text-only':''}:{'data-threads-text-only':''}),disabled:blocked(),onchange:event=>{if(blocked())return;state.change('text_only',event.target.checked);updateDirty();syncDraftControls();}});box.checked=d.text_only===true;
        root.append(el('label',{class:'editor-field'},box,x?'X에 텍스트만 발행 · 원고의 이미지·영상은 포함하지 않음':facebook?'Facebook 페이지에 텍스트만 발행 · 개인 타임라인 게시 아님 · 원고의 이미지·영상은 포함하지 않음':'Threads에 텍스트만 발행 · 원고의 이미지·영상은 포함하지 않음'));
        if(x)root.append(el('p',{class:'sub'},xCostNotice));
      }
      if(selectedConnection?.platform==='instagram'&&selectedConnection.planning_enabled){
        root.append(field('Instagram 게시 형식',d.instagram_format,change('instagram_format'),[['','형식 선택'],['image','이미지 1개 (JPEG)'],['reels','REELS 1개 (MP4)'],['carousel','캐러셀 2~10개 (JPEG·MP4)']]));
        const ids=el('textarea',{maxlength:2500,disabled:blocked(),oninput:event=>{if(blocked())return;state.change('instagram_asset_ids',event.target.value===''?[]:event.target.value.split(/\r?\n/).map(id=>id.trim()));state.preview=null;updateDirty();syncDraftControls();}});ids.value=(d.instagram_asset_ids||[]).join('\n');
        root.append(el('label',{class:'editor-field'},el('span',{},'자산 ID 순서 (한 줄에 하나)'),ids),el('p',{class:'sub'},'아래 등록 자산 ID를 원하는 순서로 입력하세요. 자동 선택·변환·파일 공개·게시를 하지 않습니다. 대상 미확인 계획은 저장할 수 있지만 계획 승인·최종 검토는 대상 확인이 필요합니다.'));
        const available=(content.assets||[]).filter(asset=>['image/jpeg','video/mp4'].includes(asset.media_type));root.append(available.length?el('ul',{},available.map(asset=>el('li',{},`${asset.id} · ${asset.media_type} · ${asset.filename||'등록 자산'}`))):el('p',{class:'sub'},'등록된 JPEG·MP4 자산이 없습니다. 먼저 원본 자산을 등록하세요. PNG는 자동 변환하지 않습니다.'));
      }
      if(d.condition_kind==='window')root.append(field('허용 시작 ISO 시각',d.window_from,change('window_from')),field('허용 끝 ISO 시각',d.window_to,change('window_to')));
      root.append(field('공개 옵션 (연결 기능에 따라 서버 검증)',d.visibility,change('visibility'),visibilityOptions),el('div',{},(selectedConnection?.capabilities||[]).includes('title_override')?field('제목 대체 (선택)',d.title_override,change('title_override')):null,(selectedConnection?.capabilities||[]).includes('description_override')?field('설명 대체 (선택)',d.description_override,change('description_override')):null),field('기존 교차 규칙 ID (선택)',d.crosspost_rule_id,change('crosspost_rule_id')),
        button('계획 미리보기',()=>act(async()=>{state.preview=await api.previewDelivery(deliveryPayload(content,d,selectedConnection));})),el('button',{type:'button',class:'btn btn-primary','data-save-plan':'',disabled:blocked()||!state.preview,onclick:()=>act(()=>save(()=>api.createDelivery(deliveryPayload(content,d,selectedConnection)),'create'))},'로컬 계획 저장'));
      if(state.preview)root.append(el('h4',{},'대상·차단·교차 경로 미리보기'),previewOutput(state.preview));
    }else{
      const p=state.plan;root.append(el('h4',{},`${p.target_label||p.platform} · ${statusLabel(p.status)}`),el('p',{},`원본 ${accountLabel(p.owner_account_id)} → 대상 ${accountLabel(p.destination_account_id)} · ${p.platform} · ${targetIdentityLabel(p.target_status)} · 인증 미확인 · 계획 버전 ${p.version}`),el('p',{},`로컬 계획 · 원격 상태 미제공 · 실행 안 함 · 원본 버전 ${p.revision}`),el('p',{class:'delivery-hash'},`승인 subject: ${p.subject_hash||'미확인'}`));
      if(p.options?.text_only===true)root.append(el('p',{},textOnlyNotice(p.platform)));
      if(p.platform==='instagram'&&p.options?.instagram)root.append(el('p',{},instagramNotice(p)));
      if(p.revision!==content.revision)root.append(el('p',{class:'inline-note'},'이 계획은 현재 편집 원본과 다른 저장 버전을 고정합니다.'));
      for(const blocker of p.blockers||[])root.append(el('p',{class:'inline-note'},blocker.reason||blocker.message||blocker.code));
      root.append(el('p',{},approvalRecordLabel(p)),field('계획 승인 메모',notes,v=>notes=v),button('이 버전 계획 승인',()=>act(()=>save(()=>api.approveDelivery(p.id,approvalPayload(p,'approved',notes)),'notes')),!canApprove(p)),button('계획 반려',()=>act(()=>save(()=>api.approveDelivery(p.id,approvalPayload(p,'rejected',notes)),'notes')),p.status==='cancelled'||!p.subject_hash),button('계획 승인 철회',()=>act(()=>save(()=>api.approveDelivery(p.id,approvalPayload(p,'revoked',notes)),'notes')),p.status==='cancelled'||!p.approval));
      if(p.status!=='cancelled'){
        const change=key=>value=>{scheduleDraft[key]=value;state.preview=null;root.querySelector('[data-save-schedule]').disabled=true;};
        root.append(el('h4',{},'일정 변경 영향'),field('변경할 ISO 시각',scheduleDraft.scheduled_at,change('scheduled_at')),field('일정 시간대',scheduleDraft.timezone,change('timezone')),button('일정 영향 미리보기',()=>act(async()=>{state.preview=await api.previewDeliverySchedule(p.id,{expected_version:p.version,...scheduleDraft});})),el('button',{type:'button',class:'btn btn-primary','data-save-schedule':'',disabled:blocked()||!state.preview?.preview_hash,onclick:()=>act(()=>save(()=>api.rescheduleDelivery(p.id,schedulePayload(p,scheduleDraft,state.preview)),'schedule'))},'일정 변경 저장'),button('로컬 계획 취소',()=>act(()=>save(()=>api.cancelDelivery(p.id,{expected_version:p.version})))));
        if(state.preview)root.append(el('p',{},`${scheduleImpactLabel(state.preview)} · 원격 예약 변경 없음`),previewOutput(state.preview));
      }
      root.append(el('h4',{},'계획 이력'),events.length?el('ul',{},events.map(event=>el('li',{},`버전 ${event.version} · ${event.summary} · ${formatDateTime(event.created_at)}`))):el('p',{class:'sub'},'계획 이력이 없습니다.'));
    }
    if(state.plan?.platform==='instagram'){
      instagramReview.open(state.plan,{writable:!parentBlocked()&&!dirty});root.append(instagramReview.element);
    }else instagramReview.open(null);
    }finally{
      rendering=false;reviewParentControls=new Map(['input','select','textarea','button'].flatMap(tag=>Array.from(root.querySelectorAll(tag))).filter(node=>!contains(instagramReview.element,node)).map(node=>[node,node.disabled]));syncReviewParentControls();syncDraftControls();if(reviewActive&&contains(instagramReview.element,reviewActive)&&!reviewActive.disabled&&typeof reviewActive.focus==='function'){reviewActive.focus();if(reviewRange){reviewActive.selectionStart=reviewRange[0];reviewActive.selectionEnd=reviewRange[1];}}
    }
  }
  async function open(next){const token=++generation;instagramReview.open(null);content=next;state=createDeliverySession();state.draft=defaultDraft();connections=[];events=[];dirty=false;loadFailed=false;notes='';scheduleDraft={scheduled_at:'',timezone:'Asia/Seoul'};resetBaselines();busy=true;render();if(!content){busy=false;render();return;}
    try{const [registered,list]=await Promise.all([api.listConnections(),api.listDeliveries('all',content.id)]);if(token!==generation)return;connections=registered.items||[];state.items=list.items||[];}catch(error){if(token===generation){loadFailed=true;state.error=error.message;}}finally{if(token===generation){busy=false;render();}}}
  return {element:root,open,getItems:()=>JSON.parse(JSON.stringify(state.items)),refreshControls:render,hasUnsavedChanges:()=>dirty||instagramReview.isDirty(),isBusy:()=>busy||instagramReview.isBusy()};
}
