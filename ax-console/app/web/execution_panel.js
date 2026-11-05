// Standalone A9 view. No fetch, polling, authentication probe, or publication occurs on import/render/bind.
// The host owns this mutable state for the lifetime of a selected content/delivery, including pending requests.
const views = new WeakMap();
const bound = new WeakMap();
const actions = ['request','refresh','observe','admit','approve'];
const triggerFields = ['job_id','scheduled_at_utc','phase','source','request_kind','mode'];
const frozenFields = ['binding_id','content_id','content_revision','manifest_hash'];
const runFields = ['run_id','state',...frozenFields,'base_job_id','execution_job_id'];
const deliveryFields = ['id','version','run_id','context_hash','observation_id','state','reason'];
const labels = {waiting:'확인 대기',partial:'일부 완료 · 확인 필요',uploaded:'업로드됨 · 공개 확인 전',blocked_quota:'한도 초과',blocked:'실행 차단',prepared:'제작 준비됨',approved:'승인 기록됨',planned:'계획됨',queued:'접수 대기 · 아직 게시되지 않음',running:'실행 중',completed:'실행 완료 · 게시 상태는 배포에서 확인',succeeded:'실행 완료 · 게시 상태는 배포에서 확인',published:'게시됨 · 내용 검증 전',verified:'공개·내용 확인 완료',scheduled:'예약 대기 · 현재 공개 미확인',awaiting_approval:'별도 발행 승인 대기',needs_auth:'로그인 필요',needs_review:'검토 필요',quota_exceeded:'한도 초과',quota_blocked:'한도 초과',unsupported:'미지원',unavailable:'서비스 사용 불가',disabled:'운영 비활성',failed:'실행 실패',unknown:'게시 여부 불확실',cancelled:'로컬 취소',paused:'사용자 중지'};
const reasonNames = {review_execution_uncertain:'검토 실행 여부가 불확실합니다.',review_unclear:'검토 판정을 확인할 수 없습니다.',review_execution_reused:'검토 실행의 독립성을 확인해야 합니다.',review_fix_required:'독립 검토에서 수정이 필요합니다.',fix_cycle_limit:'검토 수정 횟수 한도에 도달했습니다.',calculation_schema_unavailable:'계산 검증 자료가 없습니다.',monthly_limit:'월간 한도 초과',quota_limit:'사용 한도 초과',limit_reached:'사용 한도 초과',timeout:'실행 응답 시간 초과',spawn_failed:'제작 실행기를 시작하지 못했습니다.',missing_required_media:'필수 매체 누락',invalid_output:'제작 산출 형식 확인 필요',missing_result:'제작 결과 미수집',production_output_unlinked:'제작 산출 연결 확인 필요',production_in_progress:'제작 진행 중',content_changed:'원고 변경으로 재검토 필요',conflict:'현재 버전과 충돌',media_render_failed:'매체 제작 실패',media_validation_failed:'매체 검증 실패',independent_review_required:'독립 검토가 필요합니다.',daily_limit:'하루 한도 초과',weekly_limit:'주간 한도 초과',needs_login:'로그인 필요',provider_error:'공급자 오류',provider_unavailable:'공급자 사용 불가',production_execution_failed:'제작 실행 실패',disabled:'운영 실행이 꺼져 있습니다.',execution_disabled:'운영 실행이 꺼져 있습니다.',job_disabled:'등록된 작업이 비활성입니다.',unavailable:'서비스를 사용할 수 없습니다.',unsupported:'이 작업은 미지원입니다.',needs_auth:'로그인 확인이 필요합니다.',auth_required:'로그인 확인이 필요합니다.',quota_exceeded:'사용 한도를 초과했습니다.',media_evidence_required:'매체 게시 근거 확인이 필요합니다.',needs_review:'독립 검토가 필요합니다.'};
const text = value => typeof value==='string'||typeof value==='number' ? String(value) : '미확인';
const id = value => typeof value==='string'&&/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/.test(value)&&!value.includes('..');
const revision = value => Number.isSafeInteger(value)&&value>0;
const pick = (value,keys) => Object.fromEntries(keys.filter(key=>value?.[key]!==undefined).map(key=>[key,value[key]]));
const copy = value => JSON.parse(JSON.stringify(value));
const nonempty = value => typeof value==='string'&&value.length>0&&value.trim()===value;
const invalidResponse = () => Object.assign(new Error('invalid_response'),{status:503});
// A newly received alias replaces the previous spelling. Conflicting aliases are not trusted.
function normalizedState(result,aliases,required=false) {
  const values=aliases.filter(key=>Object.hasOwn(result,key)).map(key=>result[key]);
  if((required&&!values.length)||values.some(value=>!nonempty(value))||values.some(value=>value!==values[0]))throw invalidResponse();
  return values.length?{state:values[0]}:{};
}
const safeProduction = raw => {
  if(raw===null)return null;
  if(!raw||typeof raw!=='object'||Array.isArray(raw))return undefined;
  const result={};
  if(['completed','blocked','unknown'].includes(raw.status))result.status=raw.status;
  if(typeof raw.reason_code==='string'&&Object.hasOwn(reasonNames,raw.reason_code))result.reason_code=raw.reason_code;
  if(id(raw.content_id))result.content_id=raw.content_id;
  if(revision(raw.revision))result.revision=raw.revision;
  if(typeof raw.manifest_hash==='string')result.manifest_hash=raw.manifest_hash;
  if(raw.review&&['completed','required','blocked','unknown'].includes(raw.review.status))result.review={status:raw.review.status,...(Object.hasOwn(reasonNames,raw.review.reason_code)?{reason_code:raw.review.reason_code}:{})};
  return result;
};
const safeRuntimeDelivery = raw => {
  const row=pick(raw,[...deliveryFields,'remote_id']);
  Object.assign(row,normalizedState(raw,['state','execution_state']));
  if(typeof raw.remote_uncertain==='boolean')row.remote_uncertain=raw.remote_uncertain;
  const actions=['thumbnail','playlist','comment','caption','public_switch','tiktok'];
  row.followup_intents=(Array.isArray(raw.followup_intents)?raw.followup_intents:[]).filter(item=>actions.includes(item?.action)&&item.state==='not_started'&&item.required===true&&item.separate_approval_required===true).map(item=>({action:item.action,state:'not_started',required:true,separate_approval_required:true}));
  row.followup_completion=row.followup_intents.length?'pending':'not_required';return row;
};
function safeRun(raw) {
  const run=pick(raw,runFields);
  if(Object.hasOwn(raw,'production'))run.production=safeProduction(raw.production);
  if(Array.isArray(raw.deliveries))run.deliveries=raw.deliveries.map(safeRuntimeDelivery);
  return run;
}
// Read evidence is monotonic within one run. No response contract exists to resolve
// remote uncertainty or contradictory snapshots, so later reads cannot clear it.
export function rememberExecutionRead(state,raw) {
  const run={...safeRun(raw),...normalizedState(raw,['state','status'],true)};
  const evidence=state.read_evidence?.run_id===run.run_id?state.read_evidence:{run_id:run.run_id,deliveries:[],versions:{},unsafe:false,conflict:false};
  if(['unknown','submitting','submitted','running'].includes(run.state))evidence.unsafe=true;
  for(const row of run.deliveries||[]) {
    if(!id(row.id)||!Number.isSafeInteger(row.version)||row.version<0)continue;
    const key=JSON.stringify([row.id,row.version]),seen=evidence.versions[key];
    const fields=['run_id','state','context_hash','remote_id','remote_uncertain'];
    if(seen&&fields.some(field=>Object.hasOwn(seen,field)&&Object.hasOwn(row,field)&&seen[field]!==row[field]))evidence.conflict=true;
    evidence.versions[key]={...row,...seen};
    if(row.remote_id||row.remote_uncertain===true||['unknown','uploaded','published','scheduled','verified','submitting'].includes(row.state))evidence.unsafe=true;
    const index=evidence.deliveries.findIndex(item=>item.id===row.id),previous=evidence.deliveries[index];
    const latest=!previous||row.version>previous.version?{...row}:row.version<previous.version?{...previous}:{...row,...previous};
    if(previous?.remote_id||row.remote_id)latest.remote_id=previous?.remote_id||row.remote_id;
    if(previous?.remote_uncertain===true||row.remote_uncertain===true)latest.remote_uncertain=true;
    if(index<0)evidence.deliveries.push(latest);else evidence.deliveries[index]=latest;
  }
  state.read_evidence=evidence;
  return {...run,deliveries:evidence.deliveries.map(copy)};
}
const stateLabel = value => labels[value]||'상태 미확인';
const reasonLabel = value => reasonNames[value]||text(value);
const runId = state => state.run?.run_id;
const confirmationKey = state => {
  const pending=state.pending?.approve;
  return JSON.stringify([pending?.id||state.delivery?.id,pending?.body?.context_hash||state.delivery?.context_hash,pending?.body?.expected_version??state.delivery?.version,state.run?.binding_id]);
};
const changed = state => !!state.run?.binding_id&&!!state.content&&(state.content.id!==state.run.content_id||state.content.revision!==state.run.content_revision||state.content.manifest_hash!==state.run.manifest_hash);
const hasBinding = state => id(state.run?.binding_id)&&id(state.run?.content_id)&&revision(state.run?.content_revision)&&typeof state.run?.manifest_hash==='string'&&!!state.run.manifest_hash;
function validTrigger(trigger) {
  return triggerFields.every(key=>typeof trigger?.[key]==='string'&&!!trigger[key])&&
    ['prepare','submit','verify'].includes(trigger.phase)&&['console','launchd'].includes(trigger.source)&&
    ['new_publication','resume'].includes(trigger.request_kind)&&['live','dry','shadow'].includes(trigger.mode)&&
    Number.isFinite(Date.parse(trigger.scheduled_at_utc));
}
function blocked(state,action,controller) {
  if(state.reviewing)return '보존 요청의 처리 상태를 읽기 조회 중입니다.';
  if(state.busy)return '다른 요청을 처리 중입니다.';
  if(controller&&typeof controller[action==='refresh'?'getRun':action]!=='function')return '화면 연결이 준비되지 않았습니다.';
  const capability=state.capabilities?.[action];
  if(capability?.available!==true)return reasonLabel(capability?.reason||'unavailable');
  if(action!=='refresh'&&state.enabled!==true)return reasonLabel(state.disabled_reason||'disabled');
  if(action==='refresh')return id(runId(state))?'':'조회할 실행이 없습니다.';
  if((state.read_evidence?.unsafe||state.read_evidence?.conflict||state.plan_read_conflict)&&!state.pending?.[action])return '관측한 불확실 상태나 동일 버전 불일치의 처리 근거를 먼저 확인하세요. 새 요청은 허용하지 않습니다.';
  if(state.recovery_blocked)return '게시 여부가 불확실하거나 최신 원고 선택이 필요합니다. 로컬 정리는 원격 취소나 새 게시 허가가 아닙니다.';
  if(Object.entries(state.pending||{}).some(([name,value])=>value&&name!==action))return '다른 보존 요청의 처리 상태를 먼저 확인하세요.';
  if(action==='request') {
    if(!validTrigger(state.trigger))return '등록된 작업과 실행 시각을 먼저 선택하세요.';
    if(state.content_dirty)return '원고 변경을 저장한 뒤 선택 버전을 재조회하고 별도 제작 요청을 하세요.';
    if(state.trigger.phase==='prepare'&&(!id(state.content?.id)||!revision(state.content?.revision)))return '저장된 원고 상세와 정확한 버전을 선택하세요.';
    if(['observe','admit','approve'].some(name=>state.pending?.[name]))return '결과 미확정 요청을 먼저 확인하세요.';
    const pending=state.pending?.request?.body;
    if(pending&&pending.trigger.phase==='prepare'&&(pending.content_id!==state.content?.id||pending.expected_revision!==state.content?.revision))return '보존한 요청의 원고 버전이 다릅니다. 기존 요청부터 확인하세요.';
    return '';
  }
  if(state.content_dirty||changed(state))return '원고가 바뀌었습니다. 재조회 후 별도 제작 요청이 필요합니다.';
  if(state.mode==='publication'&&state.trigger?.phase!=='submit')return '별도 발행 회차를 먼저 접수하세요.';
  if(state.mode!=='publication'&&!hasBinding(state))return '동결 원고 바인딩을 먼저 확인하세요.';
  if(!id(state.delivery?.id)||!id(runId(state))||!Number.isSafeInteger(state.delivery?.version)||state.delivery.version<0)return '배포와 실행 버전을 먼저 조회하세요.';
  if(state.delivery.run_id&&state.delivery.run_id!==runId(state))return '배포와 실행이 일치하지 않습니다.';
  if(state.pending?.[action]?.id&&state.pending[action].id!==state.delivery.id)return '다른 배포의 보존 요청입니다. 원래 배포를 먼저 확인하세요.';
  if(action==='admit'&&!id(state.delivery.observation_id))return '이 배포의 읽기 점검을 먼저 수행하세요.';
  if(action==='approve') {
    if(typeof state.delivery.context_hash!=='string'||!state.delivery.context_hash)return '발행 의도 확인을 먼저 수행하세요.';
    if(state.draft?.publication_confirmed!==true)return '별도 발행 승인 확인란을 직접 선택하세요.';
    if(state.draft.confirmation_key!==confirmationKey(state))return '대상이나 발행 의도가 바뀌었습니다. 확인란을 다시 직접 선택하세요.';
  }
  return '';
}
function draw(root,state,document,controller) {
  const controls=new Map(),details=[];
  const node=(tag,value)=>{
    const element=document.createElement(tag);
    if(value!==undefined)element.textContent=text(value);
    element.style.minWidth='0';element.style.maxWidth='100%';element.style.boxSizing='border-box';element.style.overflowWrap='anywhere';
    return element;
  };
  const heading=node('h3',state.mode==='publication'?'대상 점검과 별도 발행 승인':'제작 접수와 결과');heading.tabIndex=-1;controls.set('heading',heading);
  const body=[heading,node('p','제작 완료·기획 승인·발행 승인·운영 활성은 별개입니다. 접수만으로 게시되지 않습니다.')];
  const status=node('p',state.message||'선택한 원고 버전과 대상 배포를 확인하세요.');status.setAttribute('role','status');status.setAttribute('aria-live','polite');body.push(status);
  if(state.enabled!==true)body.push(node('p',reasonLabel(state.disabled_reason||'disabled')));
  if(state.error) {
    const explanation=state.error.status===401?'인증이 만료되었습니다. 새 창에서 로그인한 뒤 다시 조회하세요.':state.error.status===409?'원본이나 실행 상태가 변경되었습니다. 재조회하고 보존한 요청을 확인하세요.':state.error.status===503?'서비스를 사용할 수 없습니다. 잠시 뒤 동일 요청으로 재시도하세요.':'요청을 처리하지 못했습니다.';
    body.push(node('p',`${explanation} 입력·진행 중 요청·요청키를 보존했습니다.`));
    if(state.error.message)body.push(node('p',state.error.message));
    if(state.error.status===401) {
      const login=node('a','새 창에서 다시 로그인');login.setAttribute('href','/login');login.setAttribute('target','_blank');login.setAttribute('rel','noopener noreferrer');controls.set('login',login);body.push(login);
    }
  }
  if(state.read_evidence?.conflict)body.push(node('p','동일 버전 조회 결과가 불일치합니다. 원격 처리 근거 확인 전 새 변이를 허용하지 않습니다.'));
  if(state.read_evidence?.unsafe)body.push(node('p','이미 관측한 게시 불확실·원격 진행 근거를 보존하고 있습니다. 이후 대기 응답만으로 해소하지 않습니다.'));
  if(state.content) {
    body.push(node('h4',state.content.title||'제목 없음'),node('p',`선택 원고: ${text(state.content.id)} · 버전: ${text(state.content.revision)}`));
    const original=node('p',state.content.original||'');original.style.whiteSpace='pre-wrap';body.push(original);
    for(const asset of Array.isArray(state.content.assets)?state.content.assets:[]) {
      const name=text(asset.filename||'이름 없는 자산');
      // Never trust supplied URL/path/src. The server content endpoint is the only generated asset link.
      if(id(state.content.id)&&revision(state.content.revision)&&id(asset.id)) {
        const link=node('a',name);link.setAttribute('href',`/api/v2/contents/${encodeURIComponent(state.content.id)}/revisions/${state.content.revision}/assets/${encodeURIComponent(asset.id)}`);link.setAttribute('target','_blank');link.setAttribute('rel','noopener noreferrer');body.push(link);
      } else body.push(node('p',`${name} · 안전한 자산 식별자가 없어 열 수 없습니다.`));
    }
  }
  if(state.run) {
    body.push(node('p',`실행: ${text(runId(state))} · ${stateLabel(state.run.state||state.run.status)}`));
    if(state.run.binding_id) {
      const detail=node('details');const summary=node('summary','동결된 제작 입력');detail.append(summary,node('p',`바인딩: ${text(state.run.binding_id)}`),node('p',`동결 원고: ${text(state.run.content_id)}`),node('p',`동결 원고 버전: ${text(state.run.content_revision)}`),node('p',`동결 매니페스트 해시: ${text(state.run.manifest_hash)}`));details.push(detail);controls.set('binding-summary',summary);body.push(detail);
    }
  }
  if(changed(state)||state.content_dirty)body.push(node('p','선택 원고가 동결 입력과 다르거나 미저장 변경이 있습니다. 기존 바인딩은 바뀌지 않습니다. 원고를 재조회한 뒤 별도 제작 요청을 하세요.'));
  const production=state.run?.production;
  if(production) {
    body.push(node('p',`제작 결과: ${{completed:'완료',blocked:'차단',unknown:'실행 여부 불확실'}[production.status]||'미확인'}`),node('p','제작 사용량: 미확인 · 0으로 간주하지 않습니다.'));
    if(production.reason_code)body.push(node('p',`제작 사유: ${reasonLabel(production.reason_code)}`));
    if(production.revision)body.push(node('p',`산출 원고 버전: ${production.revision} · 동결 입력 버전과 구분됩니다.`),node('p',`산출 매니페스트 해시: ${text(production.manifest_hash)}`));
    if(production.review)body.push(node('p',`독립 검토: ${{completed:'완료',required:'검토 필요',blocked:'차단',unknown:'결과 미확인'}[production.review.status]||'미확인'}${production.review.reason_code?' · '+reasonLabel(production.review.reason_code):''}`));
  }
  const followupNames={thumbnail:'썸네일',playlist:'재생목록',comment:'댓글',caption:'자막',public_switch:'공개 전환',tiktok:'틱톡 교차 게시'};
  for(const delivery of state.run?.deliveries||[]) {
    body.push(node('p',`대상 실행: ${text(delivery.id)} · ${stateLabel(delivery.state)}`));
    if(delivery.remote_uncertain)body.push(node('p','게시 여부 불확실 · 원격 요청 기록을 먼저 확인하세요.'));
    if(delivery.remote_id)body.push(node('p',`원격 게시물 ID: ${text(delivery.remote_id)}`));
    for(const intent of delivery.followup_intents||[])body.push(node('p',`${followupNames[intent.action]||'후처리'} · 필수 · 미시작 · 별도 승인 필요`));
  }
  if(state.delivery)body.push(node('p',`배포: ${text(state.delivery.id)} · 버전: ${text(state.delivery.version)} · ${stateLabel(state.delivery.execution_state||state.delivery.state)}`));
  if(state.mode!=='production') {
  const confirmLabel=node('label','이 대상과 동결 원고의 공개 발행을 별도로 승인합니다.');
  const confirm=node('input');confirm.type='checkbox';confirm.name='publication_confirmed';confirm.checked=state.draft?.publication_confirmed===true;confirm.disabled=!!state.busy||state.enabled!==true||changed(state)||!!state.content_dirty;controls.set('publication_confirmed',confirm);confirmLabel.append(confirm);body.push(confirmLabel);
  }
  const names={request:state.mode==='publication'?'별도 발행 회차 접수':changed(state)?'선택 버전으로 별도 제작 요청':'선택 원고 제작 요청',refresh:'실행 상태 다시 조회',observe:'대상 읽기 점검',admit:'발행 의도 확인',approve:'별도 발행 승인'};
  for(const name of actions.filter(name=>state.mode!=='production'||['request','refresh'].includes(name))) {
    const button=node('button',names[name]);button.type='button';button.className='btn';button.setAttribute('data-execution-action',name);button.style.whiteSpace='normal';
    const reason=blocked(state,name,controller);button.disabled=!!reason;if(reason)button.setAttribute('aria-label',`${names[name]} · ${reason}`);
    controls.set(name,button);body.push(button);if(reason)body.push(node('p',`${names[name]}: ${reason}`));
  }
  if(Object.values(state.pending||{}).some(Boolean))body.push(node('p','결과를 확인하지 못한 요청을 보존하고 있습니다. 재시도는 같은 본문·버전·요청키를 사용합니다.'));
  root.replaceChildren(...body);
  return {state,document,controls,details};
}

/** Pure DOM view: state contains content/trigger/run/delivery/capabilities; bind adds callbacks. */
export function renderExecutionPanel(state={}, {document=globalThis.document}={}) {
  const root=document.createElement('section');root.className='execution-panel';
  root.style.minWidth='0';root.style.maxWidth='100%';root.style.overflowWrap='anywhere';root.style.boxSizing='border-box';
  views.set(root,draw(root,state,document));return root;
}

/**
 * controller.request(body), getRun(runId), observe(deliveryId,body), admit(deliveryId,body),
 * approve(deliveryId,body) return safe JSON snapshots (see task-9-panel-report.md).
 * onChange(state) is a notification; this binder owns repainting this root.
 * cleanup detaches listeners and ignores late responses; it never discards pending state.
 */
export function bindExecutionPanel(root,controller={}) {
  const initial=views.get(root);if(!initial)throw new TypeError('renderExecutionPanel이 만든 루트가 필요합니다.');
  bound.get(root)?.();
  const {state,document}=initial;state.draft??={publication_confirmed:false};state.pending??={};state.pending_errors??={};state.attempt_serial??=0;state.read_generation??=0;
  let active=true,removeListeners=[],view=initial,heldFocus=null;
  const listen=(node,type,callback)=>{node.addEventListener(type,callback);removeListeners.push(()=>node.removeEventListener(type,callback));};
  const detach=()=>{for(const remove of removeListeners)remove();removeListeners=[];};
  function paint() {
    if(!active)return;
    const currentFocus=[...view.controls].find(([,node])=>node===document.activeElement)?.[0];
    const focus=currentFocus==='heading'&&heldFocus?heldFocus:currentFocus;
    if(!currentFocus)heldFocus=null;
    detach();view=draw(root,state,document,controller);views.set(root,view);
    for(const name of actions)if(view.controls.has(name))listen(view.controls.get(name),'click',event=>{event.preventDefault();return execute(name);});
    if(view.controls.has('publication_confirmed'))listen(view.controls.get('publication_confirmed'),'change',event=>{if(state.busy)return;state.draft.publication_confirmed=event.target.checked===true;state.draft.confirmation_key=state.draft.publication_confirmed?confirmationKey(state):null;paint();notify();});
    for(const detail of view.details)listen(detail,'keydown',event=>{if(event.key==='Escape'){event.preventDefault();detail.open=false;detail.children[0].focus();}});
    // The async completion must not steal focus after the person moved elsewhere.
    if(focus){const candidate=view.controls.get(focus);const available=candidate&&!candidate.disabled;heldFocus=available?null:focus;(available?candidate:view.controls.get('heading')).focus({preventScroll:true});}
  }
  const notify=()=>{if(active&&typeof controller.onChange==='function')controller.onChange(state);};
  function makePending(name) {
    if(name==='request') {
      const trigger=pick(state.trigger,triggerFields);
      return {body:{trigger,content_id:trigger.phase==='prepare'?state.content.id:null,expected_revision:trigger.phase==='prepare'?state.content.revision:null}};
    }
    const common={run_id:runId(state),expected_version:state.delivery.plan_version??state.delivery.version};
    if(name==='observe')return {id:state.delivery.id,body:common};
    if(name==='admit')return {id:state.delivery.id,body:{...common,observation_id:state.delivery.observation_id}};
    return {id:state.delivery.id,body:{expected_version:state.delivery.version,context_hash:state.delivery.context_hash,request_key:globalThis.crypto.randomUUID()}};
  }
  function receive(name,result) {
    if(!result||typeof result!=='object'||Array.isArray(result))throw invalidResponse();
    if(name==='request') {
      if(!id(result.run_id))throw invalidResponse();
      const sent=state.pending.request.body;
      if(sent.trigger.phase==='prepare'&&(!id(result.binding_id)||result.content_id!==sent.content_id||result.content_revision!==sent.expected_revision||typeof result.manifest_hash!=='string'||!result.manifest_hash))throw invalidResponse();
      const status=normalizedState(result,['state','status']);
      state.run={...safeRun(result),...status};
      state.delivery=state.mode==='publication'&&state.delivery?{id:state.delivery.id,version:state.delivery.plan_version??state.delivery.version,plan_version:state.delivery.plan_version??state.delivery.version,run_id:result.run_id,state:'planned'}:null;state.draft.publication_confirmed=false;
    } else if(name==='refresh') {
      if(result.run_id!==runId(state))throw invalidResponse();
      const status=normalizedState(result,['state','status'],true);
      const previous=state.run;const next={...previous,...rememberExecutionRead(state,{...result,...status}),...pick(previous,frozenFields)};
      delete next.status;
      const delivery=next.deliveries?.find(row=>row.id===state.delivery?.id);
      state.run=next;
      if(delivery&&Number.isSafeInteger(delivery.version)&&delivery.version>=0){
        if(Object.values(state.pending).some(Boolean))state.latest_delivery=delivery;
        else state.delivery={...state.delivery,...delivery};
      }
    } else if(name==='observe') {
      if(!id(result.observation_id))throw invalidResponse();
      state.delivery={...state.delivery,observation_id:result.observation_id};
    } else {
      if(result.id!==state.delivery.id||!Number.isSafeInteger(result.version)||result.version<0)throw invalidResponse();
      if(name==='admit'&&!nonempty(result.context_hash))throw invalidResponse();
      const status=normalizedState(result,['state','execution_state'],name==='approve');
      const next={...state.delivery,...pick(result,deliveryFields),...status};
      if(!Object.hasOwn(status,'state')&&next.execution_state)next.state=next.execution_state;
      delete next.execution_state;state.delivery=next;
      if(name==='approve')state.draft.publication_confirmed=false;
    }
  }
  async function execute(name) {
    if(!active||blocked(state,name,controller))return;
    if(name!=='refresh'){state.pending[name]??=makePending(name);state.pending_errors[name]={status:null,attempt:++state.attempt_serial};}
    if(name==='refresh')state.read_generation++;
    state.busy=true;state.error=null;state.message='요청을 처리 중입니다.';paint();notify();
    try {
      const pending=state.pending[name];
      const result=name==='refresh'?await controller.getRun(runId(state)):name==='request'?await controller.request(copy(pending.body)):await controller[name](pending.id,copy(pending.body));
      if(!active)return;receive(name,result);if(name!=='refresh'){delete state.pending[name];delete state.pending_errors[name];}
      state.message=name==='request'?'실행 요청을 접수했습니다. 접수는 공개 확인이 아닙니다.':name==='approve'?'별도 발행 승인을 기록했습니다. 실제 공개 결과는 실행 상태를 다시 조회하세요.':'조회와 확인 결과를 갱신했습니다.';
    } catch(error) {
      if(active){state.error={status:Number.isInteger(error?.status)?error.status:0};if(name!=='refresh')state.pending_errors[name]={status:state.error.status,attempt:state.pending_errors[name].attempt};state.message='입력과 요청을 보존했습니다.';}
    } finally {
      if(active){state.busy=false;paint();notify();}
    }
  }
  const cleanup=()=>{if(!active)return;active=false;detach();state.busy=false;if(bound.get(root)===cleanup)bound.delete(root);};
  bound.set(root,cleanup);paint();return cleanup;
}
