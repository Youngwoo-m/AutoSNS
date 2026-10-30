// Standalone A9 view. No fetch, polling, authentication probe, or publication occurs on import/render/bind.
// The host owns this mutable state for the lifetime of a selected content/delivery, including pending requests.
const views = new WeakMap();
const bound = new WeakMap();
const actions = ['request','refresh','observe','admit','approve'];
const triggerFields = ['job_id','scheduled_at_utc','phase','source','request_kind','mode'];
const frozenFields = ['binding_id','content_id','content_revision','manifest_hash'];
const runFields = ['run_id','state','status',...frozenFields,'base_job_id','execution_job_id'];
const deliveryFields = ['id','version','run_id','context_hash','observation_id','state','execution_state','reason'];
const labels = {queued:'접수 대기 · 아직 게시되지 않음',running:'실행 중',completed:'실행 완료 · 게시 상태는 배포에서 확인',succeeded:'실행 완료 · 게시 상태는 배포에서 확인',published:'공개 게시 확인',verified:'공개·내용 확인 완료',scheduled:'예약 대기 · 현재 공개 미확인',awaiting_approval:'별도 발행 승인 대기',needs_auth:'로그인 필요',needs_review:'검토 필요',quota_exceeded:'한도 초과',quota_blocked:'한도 초과',unsupported:'미지원',unavailable:'서비스 사용 불가',disabled:'운영 비활성',failed:'실행 실패',unknown:'게시 여부 불확실',cancelled:'로컬 취소',paused:'사용자 중지'};
const reasonNames = {disabled:'운영 실행이 꺼져 있습니다.',execution_disabled:'운영 실행이 꺼져 있습니다.',job_disabled:'등록된 작업이 비활성입니다.',unavailable:'서비스를 사용할 수 없습니다.',unsupported:'이 작업은 미지원입니다.',needs_auth:'로그인 확인이 필요합니다.',auth_required:'로그인 확인이 필요합니다.',quota_exceeded:'사용 한도를 초과했습니다.',media_evidence_required:'매체 게시 근거 확인이 필요합니다.',needs_review:'독립 검토가 필요합니다.'};
const text = value => typeof value==='string'||typeof value==='number' ? String(value) : '미확인';
const id = value => typeof value==='string'&&/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/.test(value)&&!value.includes('..');
const revision = value => Number.isSafeInteger(value)&&value>0;
const pick = (value,keys) => Object.fromEntries(keys.filter(key=>value?.[key]!==undefined).map(key=>[key,value[key]]));
const copy = value => JSON.parse(JSON.stringify(value));
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
  if(state.busy)return '다른 요청을 처리 중입니다.';
  if(controller&&typeof controller[action==='refresh'?'getRun':action]!=='function')return '화면 연결이 준비되지 않았습니다.';
  const capability=state.capabilities?.[action];
  if(capability?.available!==true)return reasonLabel(capability?.reason||'unavailable');
  if(action!=='refresh'&&state.enabled!==true)return reasonLabel(state.disabled_reason||'disabled');
  if(action==='refresh')return id(runId(state))?'':'조회할 실행이 없습니다.';
  if(action==='request') {
    if(!validTrigger(state.trigger))return '등록된 작업과 실행 시각을 먼저 선택하세요.';
    if(state.content_dirty)return '원고 변경을 저장한 뒤 선택 버전을 재조회하고 별도 제작 요청을 하세요.';
    if(state.trigger.phase==='prepare'&&(!id(state.content?.id)||!revision(state.content?.revision)))return '저장된 원고 상세와 정확한 버전을 선택하세요.';
    const pending=state.pending?.request?.body;
    if(pending&&pending.trigger.phase==='prepare'&&(pending.content_id!==state.content?.id||pending.expected_revision!==state.content?.revision))return '보존한 요청의 원고 버전이 다릅니다. 기존 요청부터 확인하세요.';
    return '';
  }
  if(state.content_dirty||changed(state))return '원고가 바뀌었습니다. 재조회 후 별도 제작 요청이 필요합니다.';
  if(!hasBinding(state))return '동결 원고 바인딩을 먼저 확인하세요.';
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
  const heading=node('h3','제작 접수와 별도 발행 승인');heading.tabIndex=-1;controls.set('heading',heading);
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
  if(state.delivery)body.push(node('p',`배포: ${text(state.delivery.id)} · 버전: ${text(state.delivery.version)} · ${stateLabel(state.delivery.execution_state||state.delivery.state)}`));
  const confirmLabel=node('label','이 대상과 동결 원고의 공개 발행을 별도로 승인합니다.');
  const confirm=node('input');confirm.type='checkbox';confirm.name='publication_confirmed';confirm.checked=state.draft?.publication_confirmed===true;confirm.disabled=!!state.busy||state.enabled!==true||changed(state)||!!state.content_dirty;controls.set('publication_confirmed',confirm);confirmLabel.append(confirm);body.push(confirmLabel);
  const names={request:changed(state)?'선택 버전으로 별도 제작 요청':'선택 원고 제작 요청',refresh:'실행 상태 다시 조회',observe:'대상 읽기 점검',admit:'발행 의도 확인',approve:'별도 발행 승인'};
  for(const name of actions) {
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
  const {state,document}=initial;state.draft??={publication_confirmed:false};state.pending??={};
  let active=true,removeListeners=[],view=initial,heldFocus=null;
  const listen=(node,type,callback)=>{node.addEventListener(type,callback);removeListeners.push(()=>node.removeEventListener(type,callback));};
  const detach=()=>{for(const remove of removeListeners)remove();removeListeners=[];};
  function paint() {
    if(!active)return;
    const currentFocus=[...view.controls].find(([,node])=>node===document.activeElement)?.[0];
    const focus=currentFocus==='heading'&&heldFocus?heldFocus:currentFocus;
    if(!currentFocus)heldFocus=null;
    detach();view=draw(root,state,document,controller);views.set(root,view);
    for(const name of actions)listen(view.controls.get(name),'click',event=>{event.preventDefault();return execute(name);});
    listen(view.controls.get('publication_confirmed'),'change',event=>{if(state.busy)return;state.draft.publication_confirmed=event.target.checked===true;state.draft.confirmation_key=state.draft.publication_confirmed?confirmationKey(state):null;paint();notify();});
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
    const common={run_id:runId(state),expected_version:state.delivery.version};
    if(name==='observe')return {id:state.delivery.id,body:common};
    if(name==='admit')return {id:state.delivery.id,body:{...common,observation_id:state.delivery.observation_id}};
    return {id:state.delivery.id,body:{expected_version:state.delivery.version,context_hash:state.delivery.context_hash,request_key:globalThis.crypto.randomUUID()}};
  }
  function receive(name,result) {
    if(!result||typeof result!=='object'||Array.isArray(result))throw new Error('invalid_response');
    if(name==='request') {
      if(!id(result.run_id))throw new Error('invalid_response');
      const sent=state.pending.request.body;
      if(sent.trigger.phase==='prepare'&&(!id(result.binding_id)||result.content_id!==sent.content_id||result.content_revision!==sent.expected_revision||typeof result.manifest_hash!=='string'||!result.manifest_hash))throw new Error('invalid_response');
      state.run=pick(result,runFields);state.delivery=null;state.draft.publication_confirmed=false;
    } else if(name==='refresh') {
      if(result.run_id!==runId(state))throw new Error('invalid_response');
      const previous=state.run;state.run={...previous,...pick(result,runFields),...pick(previous,frozenFields)};
    } else if(name==='observe') {
      if(!id(result.observation_id))throw new Error('invalid_response');
      state.delivery={...state.delivery,observation_id:result.observation_id};
    } else {
      if(result.id!==state.delivery.id||!Number.isSafeInteger(result.version))throw new Error('invalid_response');
      state.delivery={...state.delivery,...pick(result,deliveryFields)};
      if(name==='approve')state.draft.publication_confirmed=false;
    }
  }
  async function execute(name) {
    if(!active||blocked(state,name,controller))return;
    if(name!=='refresh')state.pending[name]??=makePending(name);
    state.busy=true;state.error=null;state.message='요청을 처리 중입니다.';paint();notify();
    try {
      const pending=state.pending[name];
      const result=name==='refresh'?await controller.getRun(runId(state)):name==='request'?await controller.request(copy(pending.body)):await controller[name](pending.id,copy(pending.body));
      if(!active)return;receive(name,result);if(name!=='refresh')delete state.pending[name];
      state.message=name==='request'?'실행 요청을 접수했습니다. 접수는 공개 확인이 아닙니다.':name==='approve'?'별도 발행 승인을 기록했습니다. 실제 공개 결과는 실행 상태를 다시 조회하세요.':'조회와 확인 결과를 갱신했습니다.';
    } catch(error) {
      if(active){state.error={status:Number.isInteger(error?.status)?error.status:0};state.message='입력과 요청을 보존했습니다.';}
    } finally {
      if(active){state.busy=false;paint();notify();}
    }
  }
  const cleanup=()=>{if(!active)return;active=false;detach();state.busy=false;if(bound.get(root)===cleanup)bound.delete(root);};
  bound.set(root,cleanup);paint();return cleanup;
}
