import {safeUrl} from './view_helpers.js';
const scopes=new Set(['all','personal','dept']);
const key=()=>globalThis.crypto.randomUUID();
const labels={unknown:'게시 여부 불확실',needs_review:'검토 필요',auth_required:'인증 필요',failed:'실패',retry_wait:'재개 대기',queued:'대기',running:'진행 중',submitting:'제출 중',uploaded:'업로드됨',scheduled:'예약됨 · 공개 확인 전',published:'게시됨 · 검증 전',verified:'공개 검증 완료',completed:'완료',partial:'부분 실패',waiting:'확인 대기'};
export function createOperationsApi({fetcher=globalThis.fetch}={}){
  async function request(path,body){
    const response=await fetcher(`/api/v2${path}`,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json',...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});
    if(!response.ok)throw Object.assign(new Error(response.status===401?'로그인이 필요합니다. 입력은 보존했습니다.':response.status===409?'상태가 바뀌었거나 조치가 허용되지 않습니다. 입력은 보존했습니다.':'요청을 처리하지 못했습니다. 입력은 보존했습니다.'),{status:response.status});
    return response.json();
  }
  const path=id=>`/operations/${encodeURIComponent(id)}`;
  return {list:(account='all')=>{if(!scopes.has(account))return Promise.reject(new Error('계정 범위가 올바르지 않습니다.'));return request(`/operations?account=${account}`);},get:id=>request(path(id)),reconcile:(id,body)=>request(`${path(id)}/reconcile`,body),resolve:(id,body)=>request(`${path(id)}/resolve`,body),retry:(id,body)=>request(`${path(id)}/retry`,body),control:body=>request('/control',body)};
}
export function createOperationsPanel({api,onChange=()=>{},document=globalThis.document}){
  const roots=Object.fromEntries(['issues','today','accounts'].map(mode=>{const node=document.createElement('section');node.className=`operations-panel operations-${mode}`;return [mode,node];}));
  let account='all',snapshot=null,detail=null,draft=null,dirty=false,busy=false,generation=0,selection=0,message='운영 상태를 불러오세요.',conflict=false,filter='all';
  const controls=new Map();
  const hasDirty=()=>dirty||[...controls.values()].some(value=>value.reason!=='');
  const node=(tag,text,className)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(className)n.className=className;return n;};
  function emit(repaint=true){if(repaint)paint();onChange();}
  function feedback(error){message=error.status===401?'로그인이 필요합니다. 입력은 보존했습니다.':error.status===409?'상태가 바뀌었거나 조치가 허용되지 않습니다. 입력은 보존했습니다. 최신 버전 확인 후 검토하세요.':'요청을 처리하지 못했습니다. 입력은 보존했습니다.';conflict=error.status===409;}
  function allowed(action){return !!detail?.available_actions?.includes(action)&&(action!=='retry'||detail.execution_enabled===true&&snapshot?.execution_enabled===true);}
  function button(text,handler,disabled=false){const b=node('button',text,'btn');b.type='button';b.disabled=busy||disabled;b.addEventListener('click',handler);return b;}
  function input(parent,name,label,value,{options,area=false,change}={}){
    const wrap=node('label',label),field=node(options?'select':area?'textarea':'input');field.name=name;
    if(options)for(const [value,text] of options){const o=node('option',text);o.value=value;field.append(o);}
    field.value=value;field.disabled=busy;field.addEventListener('input',()=>change?.(field.value));if(options)field.addEventListener('change',()=>change?.(field.value));wrap.append(field);parent.append(wrap);return field;
  }
  function newDraft(){draft={kind:'link_existing',evidence:'{}',note:'',expected_version:detail.version,request_key:key()};dirty=false;conflict=false;}
  async function load(scope='all'){
    if(!scopes.has(scope))throw new Error('계정 범위가 올바르지 않습니다.');
    if(scope!==account){account=scope;snapshot=null;detail=null;draft=null;dirty=false;controls.clear();selection++;}
    const current=++generation;message='운영 상태를 불러오는 중입니다.';emit();
    try{const result=await api.list(scope);if(current!==generation)return;snapshot=result;message='서버에서 관측한 운영 상태입니다.';}
    catch(error){if(current!==generation)return;if(error.status===401)snapshot=null;feedback(error);}
    emit();
  }
  async function open(id){
    if(busy||hasDirty()){message='입력한 근거를 저장하거나 버린 뒤 다른 실행을 선택하세요.';emit();return;}
    const current=generation,selected=++selection;message='실행 상세를 불러오는 중입니다.';emit();
    try{const result=await api.get(id);if(current!==generation||selected!==selection)return;detail=result;newDraft();message='실행 상태와 근거를 확인하세요.';}
    catch(error){if(current!==generation||selected!==selection)return;feedback(error);}
    emit();
  }
  async function mutate(action,body){
    if(busy||!allowed(action))return;
    const current=generation,id=detail.id;busy=true;emit();
    try{await api[action](id,body);if(current!==generation)return;dirty=false;conflict=false;detail=null;draft=null;message='조치를 기록했습니다. 최신 상태를 확인하세요.';await load(account);}
    catch(error){if(current===generation)feedback(error);}
    finally{busy=false;emit();}
  }
  async function rebase(){
    if(busy||!detail)return;busy=true;const current=generation;emit();
    try{const latest=await api.get(detail.id);if(current!==generation)return;detail=latest;draft.expected_version=latest.version;draft.request_key=key();conflict=false;message='최신 버전을 확인했습니다. 보존한 입력을 검토한 뒤 다시 조치하세요.';}
    catch(error){if(current===generation)feedback(error);}
    finally{busy=false;emit();}
  }
  function evidence(parent,rows){
    for(const row of Array.isArray(rows)?rows:[]){const box=node('div',undefined,'operations-evidence');
      // Only the server's documented display fields are rendered; arbitrary metadata is never dumped.
      for(const name of ['kind','ordinal','state','outcome','note','summary','checked_at','started_at','completed_at','remote_id'])if(typeof row[name]==='string'||typeof row[name]==='number')box.append(node('p',`${name}: ${row[name]}`));
      const href=safeUrl(row.url);if(href){const link=node('a','원격 근거 열기');link.href=href;link.target='_blank';link.rel='noopener noreferrer';box.append(link);}parent.append(box);
    }
  }
  function renderDetail(root){
    if(!detail)return;const box=node('section',undefined,'operations-detail');box.append(node('h3',`실행 상세 · ${detail.id}`));
    for(const [label,value] of [['계획 상태',detail.plan_status],['실행 상태',labels[detail.execution_state]||'상태 미확인'],['소유 계정',detail.owner_account_id],['대상 계정',detail.destination_account_id],['연결',detail.connection_id],['플랫폼',detail.platform],['버전',detail.version]])box.append(node('p',`${label}: ${value??'미확인'}`));
    box.append(node('h4','시도 기록'));evidence(box,detail.attempts);box.append(node('h4','확인 근거'));evidence(box,detail.evidence);
    for(const reason of detail.blockers||[])if(typeof reason==='string')box.append(node('p',reason,'operations-warning'));
    box.append(button('상태 다시 조회',()=>mutate('reconcile',{expected_version:detail.version,request_key:key()}),!allowed('reconcile')),button('동일 실행 재개',()=>mutate('retry',{expected_version:detail.version,request_key:key()}),!allowed('retry')));
    if(!allowed('reconcile'))box.append(node('p','읽기 전용 조회 어댑터가 허용되지 않아 상태 조회를 실행할 수 없습니다.'));
    if(!allowed('retry'))box.append(node('p','실행 정책 또는 복구 상태 때문에 재개할 수 없습니다.'));
    const form=node('form',undefined,'operations-form');const edit=name=>value=>{draft[name]=value;dirty=true;emit(false);};
    input(form,'kind','조치 종류',draft.kind,{options:[['link_existing','기존 원격 게시물 연결'],['confirmed_not_posted','미게시 확인'],['cancel_local','로컬 실행 취소']],change:edit('kind')});
    input(form,'evidence','확인 근거 (JSON 객체)',draft.evidence,{area:true,change:edit('evidence')});input(form,'note','검토 메모',draft.note,{area:true,change:edit('note')});
    form.append(node('p','로컬 실행 취소는 관리 기록에만 적용됩니다. 원격 게시물 삭제·예약 취소를 수행하지 않습니다.'));
    const submit=node('button','근거와 조치 기록','btn');submit.type='submit';submit.disabled=busy||!allowed('resolve');form.append(submit);
    form.addEventListener('submit',async event=>{event.preventDefault();if(busy||!allowed('resolve'))return;let parsed;try{parsed=JSON.parse(draft.evidence);if(!parsed||Array.isArray(parsed)||typeof parsed!=='object')throw new Error();}catch{message='확인 근거에 JSON 객체를 입력하세요. 입력은 보존했습니다.';emit();return;}if(!draft.note.trim()){message='검토 메모를 입력하세요. 입력은 보존했습니다.';emit();return;}await mutate('resolve',{expected_version:draft.expected_version,request_key:draft.request_key,kind:draft.kind,evidence:parsed,note:draft.note});});
    box.append(form);if(conflict)box.append(button('내 입력을 유지하고 최신 버전 확인',rebase));box.append(button('미저장 입력 버리기',discard));root.append(box);
  }
  function renderControls(root){
    root.append(node('h3','관리 실행 제어'),node('p','관리 일시중지는 로컬 관리 DB에만 적용됩니다. 기존 자동 작업·launchd에는 적용되지 않습니다. 재개해도 밀린 작업을 새로 등록하지 않습니다.'));
    root.append(node('p',`기존 전역 STOP: ${{clear:'해제 관측',stopped:'중지 관측',unknown:'상태 미확인'}[snapshot?.control?.global?.state]||'상태 미확인'} · 읽기 전용`));
    for(const item of snapshot?.control?.managed||[]){if(!['managed','account','connection'].includes(item.scope))continue;const controlKey=`${item.scope}-${item.id}`;let draft=controls.get(controlKey);if(!draft){draft={reason:'',request_key:key(),version:item.version};controls.set(controlKey,draft);}
      const box=node('section',undefined,'operations-control');box.append(node('h4',`${item.scope} · ${item.id} · ${item.state==='paused'?'일시중지':'상태 '+item.state}`));
      input(box,`reason-${controlKey}`,'변경 사유',draft.reason,{change:value=>{draft.reason=value;emit(false);}});
      for(const action of ['pause','resume']){const enabled=item.available_actions?.includes(action);box.append(button(`${action==='pause'?'관리 일시중지':'관리 재개'} · ${item.id}`,async()=>{
        if(busy||!enabled)return;if(!draft.reason.trim()){message='변경 사유를 입력하세요. 입력은 보존했습니다.';emit();return;}busy=true;const current=generation;emit();
        try{await api.control({scope:item.scope,id:item.id,action,expected_version:draft.version,request_key:draft.request_key,reason:draft.reason});if(current!==generation)return;controls.delete(controlKey);await load(account);}
        catch(error){if(current===generation){draft.conflict=error.status===409;feedback(error);}}finally{busy=false;emit();}
      },!enabled));}
      if(draft.conflict)box.append(button(`제어 최신 버전 확인 · ${item.id}`,async()=>{
        if(busy)return;busy=true;const current=generation;emit();
        try{const latest=await api.list(account);if(current!==generation)return;const updated=latest.control?.managed?.find(value=>value.scope===item.scope&&value.id===item.id);if(!updated)throw new Error();snapshot=latest;draft.version=updated.version;draft.request_key=key();draft.conflict=false;message='제어 최신 버전을 확인했습니다. 보존한 사유를 검토하세요.';}
        catch(error){if(current===generation)feedback(error);}finally{busy=false;emit();}
      }));root.append(box);
    }
  }
  function paint(){
    for(const [mode,root] of Object.entries(roots)){
      root.replaceChildren();root.append(node('h2',mode==='issues'?'문제·복구':mode==='today'?'관리 실행 현황':'관리 실행 제어'));const status=node('p',message);status.setAttribute('role','status');status.setAttribute('aria-live','polite');root.append(status);
      root.append(node('p',snapshot?.execution_enabled===true?'관리 실행 정책이 활성 상태입니다. 각 대상의 허용 동작을 확인하세요.':'관리 실행은 기본 비활성 상태입니다. 기존 작업의 실행 여부와 별개입니다.','operations-warning'));
      for(const reason of snapshot?.blockers||[])if(typeof reason==='string')root.append(node('p',reason));
      if(mode==='accounts'){renderControls(root);continue;}
      if(mode==='today'){const s=snapshot?.summary||{};root.append(node('p',`관리 실행 · 진행 ${s.active??0} · 완료 ${s.completed??0} · 부분 실패 ${s.partial??0} · 확인 대기 ${s.waiting??0}`),node('p','아래 항목은 관리 실행 기록입니다. 기존 발행 관측·관리 계획은 각 화면의 별도 기록을 확인하세요.'));}
      if(mode==='issues')input(root,'issue-filter','문제 유형',filter,{options:[['all','전체 문제'],['unknown','게시 여부 불확실'],['auth_required','인증 필요'],['needs_review','검토 필요'],['failed','실패'],['retry_wait','재개 대기']],change:value=>{filter=value;emit();}});
      const items=(snapshot?.items||[]).filter(item=>mode==='today'||(filter==='all'?['unknown','auth_required','needs_review','failed','retry_wait'].includes(item.execution_state):item.execution_state===filter));
      if(!items.length)root.append(node('p',snapshot?'해당 실행 기록이 없습니다.':'조회된 실행 기록이 없습니다.'));
      const list=node('div',undefined,'operations-list');for(const item of items){const row=node('article',undefined,'operations-row');row.append(node('p',`${item.platform} · 소유 ${item.owner_account_id} → 대상 ${item.destination_account_id}`),node('p',`계획 ${item.plan_status} · 실행 ${labels[item.execution_state]||'상태 미확인'}`),button(`상세 · ${item.id}`,()=>open(item.id)));list.append(row);}root.append(list);if(mode==='issues')renderDetail(root);
    }
  }
  function discard(){if(busy)return;dirty=false;controls.clear();if(detail)newDraft();message='미저장 입력을 버렸습니다.';emit();}
  paint();return {load,render:(mode='issues')=>{if(!roots[mode])throw new Error('알 수 없는 운영 화면입니다.');return roots[mode];},isDirty:hasDirty,isBusy:()=>busy,discard,hasUnsavedChanges:hasDirty,discardChanges:discard};
}
