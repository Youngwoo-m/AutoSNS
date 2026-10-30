import {safeUrl,formatDateTime} from './view_helpers.js';
const scopes=new Set(['all','personal','dept']);
const key=()=>globalThis.crypto.randomUUID();
const labels={cancelled:'로컬 취소',unknown:'게시 여부 불확실',needs_review:'검토 필요',auth_required:'인증 필요',failed:'실패',retry_wait:'재개 대기',queued:'대기',running:'진행 중',submitting:'제출 중',uploaded:'업로드됨',scheduled:'예약됨 · 공개 확인 전',published:'게시됨 · 검증 전',verified:'공개 검증 완료',completed:'완료',partial:'부분 실패',waiting:'확인 대기'};
const accountName=id=>({personal:'개인',dept:'학과'}[id]||'계정 미확인');
const platformName=id=>({naver_blog:'네이버 블로그',youtube:'유튜브',tiktok:'틱톡',instagram:'인스타그램',threads:'스레드',x:'엑스',facebook:'페이스북',tistory:'티스토리',blogger:'블로거',homepage:'홈페이지',kakao:'카카오'}[id]||'플랫폼 미확인');
const planName=id=>({pending:'대기',ready:'준비 완료',approved:'승인 완료',draft:'초안',planned:'계획됨',scheduled:'예약됨',cancelled:'취소됨',failed:'실패',published:'게시됨',verified:'검증 완료',needs_review:'검토 필요'}[id]||'상태 미확인');
const blockerLabels={execution_disabled:'서버 실행 정책이 비활성 상태입니다.',adapter_unavailable:'이 연결의 읽기 전용 원격 조회 어댑터가 등록되지 않았습니다.',probe_unavailable:'서버 프로세스·잠금 관측이 등록되지 않아 미게시 확인을 확정할 수 없습니다.',insufficient_evidence:'서버 관측 근거가 충분하지 않습니다.',worker_active:'이전 작업자의 실행 시간이 아직 유효합니다.',invalid_resume:'실제 제출 회차로 연결된 실행만 재개할 수 있습니다.',context_changed:'등록된 대상 또는 운영 정책이 바뀌어 재검토가 필요합니다.',connection_not_allowed:'이 연결은 서버 실행 허용 범위에 없습니다.',cutover_required:'서버 실행 전환 근거가 필요합니다.',legacy_owner:'기존 자동 작업 소유 범위라 관리 실행으로 재개할 수 없습니다.',job_disabled:'등록된 작업이 비활성 상태입니다.',connection_disabled:'등록된 연결이 비활성 상태입니다.',managed_paused:'관리 범위가 일시중지 상태입니다.',recovery_state_blocked:'현재 상태에서는 이 복구 조치를 사용할 수 없습니다.'};
const blockerText=code=>blockerLabels[code]||'운영 조건을 추가로 확인해야 합니다.';
export function createOperationsApi({fetcher=globalThis.fetch}={}){
  async function request(path,body){
    const response=await fetcher(`/api/v2${path}`,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json',...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});
    if(!response.ok){let code;try{code=(await response.json()).code;}catch{}throw Object.assign(new Error(response.status===401?'로그인이 필요합니다. 입력은 보존했습니다.':response.status===409?'상태가 바뀌었거나 조치가 허용되지 않습니다. 입력은 보존했습니다.':'요청을 처리하지 못했습니다. 입력은 보존했습니다.'),{status:response.status,code});}
    return response.json();
  }
  const path=id=>`/operations/${encodeURIComponent(id)}`;
  return {list:(account='all')=>{if(!scopes.has(account))return Promise.reject(new Error('계정 범위가 올바르지 않습니다.'));return request(`/operations?account=${account}`);},get:id=>request(path(id)),reconcile:(id,body)=>request(`${path(id)}/reconcile`,body),resolve:(id,body)=>request(`${path(id)}/resolve`,body),retry:(id,body)=>request(`${path(id)}/retry`,body),control:body=>request('/control',body)};
}
export function createOperationsPanel({api,onChange=()=>{},document=globalThis.document}){
  const roots=Object.fromEntries(['issues','today','accounts'].map(mode=>{const node=document.createElement('section');node.className=`operations-panel operations-${mode}`;return [mode,node];}));
  let account='all',snapshot=null,detail=null,draft=null,dirty=false,busy=false,generation=0,selection=0,message='운영 상태를 불러오세요.',conflict=false,filter='all';
  const controls=new Map(), confirmedControls=new Map(), actionRequests=new Map(), actionNeedsRefresh=new Set();
  let renderedMode;
  const actionKey=(id,action)=>`${id}:${action}`;
  function actionBody(action){const id=actionKey(detail.id,action);if(!actionRequests.has(id))actionRequests.set(id,{expected_version:detail.version,request_key:key()});return actionRequests.get(id);}
  function resetActionRequests(id){for(const action of ['retry','reconcile'])actionRequests.delete(actionKey(id,action));}
  const hasDirty=()=>dirty||[...controls.values()].some(value=>value.reason!=='');
  const node=(tag,text,className)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(className)n.className=className;return n;};
  function emit(repaint=true){if(repaint)paint();onChange();}
  function feedback(error){message=error.status===401?'로그인이 필요합니다. 입력은 보존했습니다.':error.status===409?'상태가 바뀌었거나 조치가 허용되지 않습니다. 입력은 보존했습니다. 최신 버전 확인 후 검토하세요.':'요청을 처리하지 못했습니다. 입력은 보존했습니다.';if(error.code)message=blockerText(error.code)+' 입력은 보존했습니다.';conflict=error.status===409;}
  function allowed(action){return !!detail?.available_actions?.includes(action)&&(action!=='retry'||detail.execution_enabled===true&&snapshot?.execution_enabled===true);}
  function button(text,handler,disabled=false){const b=node('button',text,'btn');b.type='button';b.disabled=busy||disabled;b.addEventListener('click',handler);return b;}
  function input(parent,name,label,value,{options,area=false,change}={}){
    const wrap=node('label',label),field=node(options?'select':area?'textarea':'input');field.name=name;
    if(options)for(const [value,text] of options){const o=node('option',text);o.value=value;field.append(o);}
    field.value=value;field.disabled=busy;field.addEventListener('input',()=>change?.(field.value));if(options)field.addEventListener('change',()=>change?.(field.value));wrap.append(field);parent.append(wrap);return field;
  }
  function mergeControlSnapshot(incoming){
    if(!incoming?.control)return incoming;
    const rows=[...(incoming.control.managed||[])];
    for(const [id,confirmed] of confirmedControls){
      const index=rows.findIndex(row=>`${row.scope}-${row.id}`===id);
      if(index>=0&&rows[index].version>=confirmed.version){confirmedControls.delete(id);continue;}
      if(index>=0)rows[index]={...rows[index],...confirmed};else rows.push(confirmed);
    }
    return {...incoming,control:{...incoming.control,managed:rows}};
  }
  const resolutionKinds=()=>Array.isArray(detail?.available_resolution_kinds)?detail.available_resolution_kinds:['link_existing','confirmed_not_posted','cancel_local'];
  function newDraft(){draft={kind:resolutionKinds()[0]||'',evidence:'{}',note:'',expected_version:detail.version,request_key:key()};dirty=false;conflict=false;}
  async function load(scope='all'){
    if(!scopes.has(scope))throw new Error('계정 범위가 올바르지 않습니다.');
    if(scope!==account){account=scope;snapshot=null;detail=null;draft=null;dirty=false;controls.clear();confirmedControls.clear();actionRequests.clear();actionNeedsRefresh.clear();selection++;}
    const current=++generation;message='운영 상태를 불러오는 중입니다.';emit();
    try{const result=await api.list(scope);if(current!==generation)return;snapshot=mergeControlSnapshot(result);message='서버에서 관측한 운영 상태입니다.';}
    catch(error){if(current!==generation)return;if(error.status===401)snapshot=null;feedback(error);emit();return false;}
    emit();return true;
  }
  async function open(id){
    if(busy||hasDirty()){message='입력한 근거를 저장하거나 버린 뒤 다른 실행을 선택하세요.';emit();return;}
    const current=generation,selected=++selection;message='실행 상세를 불러오는 중입니다.';emit();
    try{const result=await api.get(id);if(current!==generation||selected!==selection)return;detail=result;newDraft();message='실행 상태와 근거를 확인하세요.';}
    catch(error){if(current!==generation||selected!==selection)return;feedback(error);}
    emit();
  }
  async function runAction(action){
    if(busy||!allowed(action))return;
    const id=detail.id,requestId=actionKey(id,action),current=generation;
    if(actionNeedsRefresh.has(requestId)){
      busy=true;emit();
      try{const latest=await api.get(id);if(current!==generation)return;detail=latest;actionNeedsRefresh.delete(requestId);}
      catch{if(current===generation)message='이전 조치는 완료됐지만 최신 상세 조회에 실패했습니다. 입력은 보존했고 새 조치는 전송하지 않았습니다.';return;}
      finally{busy=false;emit();}
    }
    return mutate(action,actionBody(action));
  }
  async function mutate(action,body){
    if(busy||!allowed(action))return;
    if(action==='retry'&&dirty){message='작성 중인 복구 입력을 저장하거나 버린 뒤 실행을 재개하세요.';emit();return;}
    const current=generation,id=detail.id,requestId=actionKey(id,action);let postConfirmed=false;busy=true;emit();
    try{
      await api[action](id,body);if(current!==generation)return;postConfirmed=true;
      actionRequests.delete(requestId);
      if(action==='reconcile'){
        actionNeedsRefresh.add(requestId);
        const latest=await api.get(id);if(current!==generation)return;detail=latest;actionNeedsRefresh.delete(requestId);
        const loaded=await load(account);if(loaded===undefined)return;
        message=loaded?'최신 관측을 확인했습니다. 작성 중인 복구 입력과 기준 버전은 보존했습니다.':'조치는 완료됐지만 후속 목록 조회에 실패했습니다. 작성 중인 복구 입력과 기준 버전은 보존했습니다.';
      }else{dirty=false;conflict=false;detail=null;draft=null;message='조치를 기록했습니다. 최신 상태를 확인하세요.';const loaded=await load(account);if(loaded===false)message='조치는 완료됐지만 후속 목록 조회에 실패했습니다.';}
    }
    catch(error){if(current===generation){if(postConfirmed)message='조치는 완료됐지만 후속 상세 조회에 실패했습니다. 입력은 보존했습니다.';else feedback(error);}}
    finally{busy=false;emit();}
  }
  async function rebase(){
    if(busy||!detail)return;busy=true;const current=generation;emit();
    try{const latest=await api.get(detail.id);if(current!==generation)return;detail=latest;draft.expected_version=latest.version;draft.request_key=key();resetActionRequests(detail.id);for(const action of ['retry','reconcile'])actionNeedsRefresh.delete(actionKey(detail.id,action));conflict=false;message='최신 버전을 확인했습니다. 보존한 입력을 검토한 뒤 다시 조치하세요.';}
    catch(error){if(current===generation)feedback(error);}
    finally{busy=false;emit();}
  }
  const localTime=value=>value?`${formatDateTime(value)} · 한국시간`:'시각 미확인';
  function evidence(parent,rows){
    const names={kind:'근거 종류',ordinal:'시도 순서',state:'상태',outcome:'결과',note:'검토 메모',summary:'요약',created_at:'기록 시각',checked_at:'확인 시각',scheduled_at:'예약 시각',started_at:'시작 시각',completed_at:'완료 시각',visibility:'공개 범위',process_status:'이전 프로세스',lock_status:'프로필 잠금',candidate_count:'원격 후보 수',identity_confirmed:'원격 동일성 확인',confirmed_not_posted:'미게시 확인',old_process_terminated:'이전 작업 종료 확인',profile_lock_released:'프로필 잠금 해제 확인',local_only:'로컬 기록에만 적용'};
    const kinds={remote_lookup:'원격 조회',lookup:'원격 조회',recovery:'복구 확인',recovery_observation:'복구 관측',request_started:'제출 요청 시작',late_attempt_result:'뒤늦게 도착한 결과',resolved_link_existing:'기존 게시물 연결',resolved_confirmed_not_posted:'미게시 확인 기록',resolved_cancel_local:'로컬 취소 기록',retry_queued:'동일 실행 재개 대기'};
    const outcomes={matched:'일치 항목 확인',ambiguous:'여러 후보로 확정 불가',not_found:'일치 항목 없음',unsupported:'조회 미지원',error:'조회 오류',pending:'확인 대기',submitted:'제출됨',...labels};
    for(const row of Array.isArray(rows)?rows:[]){const box=node('div',undefined,'operations-evidence');
      for(const [name,label] of Object.entries(names)){
        let value=row[name];if(!['string','number','boolean'].includes(typeof value))continue;
        if(typeof value==='boolean')value=value?'예':'아니요';
        else if(name.endsWith('_at'))value=localTime(value);
        else if(name==='kind')value=kinds[value]||labels[value]||'기타 관측';
        else if(name==='outcome'||name==='state')value=outcomes[value]||'상태 미확인';
        else if(name==='process_status')value={dead:'종료 확인',alive:'실행 중',unknown:'미확인'}[value]||'미확인';
        else if(name==='lock_status')value={free:'해제 확인',held:'사용 중',unknown:'미확인'}[value]||'미확인';
        else if(name==='visibility')value={public:'공개',private:'비공개',unlisted:'일부 공개',scheduled:'예약됨'}[value]||'미확인';
        box.append(node('p',`${label}: ${value}`));
      }
      if(typeof row.remote_id==='string'){const identity=node('details');identity.append(node('summary','원격 게시물 식별자'),node('p',row.remote_id));box.append(identity);}
      const href=safeUrl(row.url);if(href){const link=node('a','원격 근거 열기');link.href=href;link.target='_blank';link.rel='noopener noreferrer';box.append(link);}parent.append(box);
    }
  }
  function renderDetail(root){
    if(!detail)return;const box=node('section',undefined,'operations-detail');box.append(node('h3',detail.title||'실행 상세'),node('p',detail.target_label||platformName(detail.platform)));const identity=node('details');identity.append(node('summary','내부 실행 식별자'),node('p',`실행 상세 · ${detail.id}`));box.append(identity);
    for(const [label,value] of [['계획 상태',planName(detail.plan_status)],['실행 상태',labels[detail.execution_state]||'상태 미확인'],['원본 소유 계정',accountName(detail.owner_account_id)],['대상 계정',accountName(detail.destination_account_id)],['연결',detail.connection_id],['플랫폼',platformName(detail.platform)],['버전',detail.version],['생성 시각',localTime(detail.created_at)],['확인 시각',localTime(detail.checked_at)],['예약 시각',localTime(detail.scheduled_at)]])box.append(node('p',`${label}: ${value??'미확인'}`));
    if(detail.remote_uncertain)box.append(node('p','게시 여부 불확실 · 로컬 상태와 별개로 원격 결과가 확정되지 않았습니다. 새 제출 없이 근거를 확인하세요.','operations-warning'));
    box.append(node('h4','시도 기록'));evidence(box,detail.attempts);box.append(node('h4','확인 근거'));evidence(box,detail.evidence);
    for(const reason of detail.blockers||[])if(typeof reason==='string')box.append(node('p',blockerText(reason),'operations-warning'));
    box.append(button('상태 다시 조회',()=>runAction('reconcile'),!allowed('reconcile')),button('동일 실행 재개',()=>runAction('retry'),!allowed('retry')));
    if(!allowed('reconcile'))box.append(node('p','읽기 전용 조회 어댑터가 허용되지 않아 상태 조회를 실행할 수 없습니다.'));
    if(!allowed('retry'))box.append(node('p','실행 정책 또는 복구 상태 때문에 재개할 수 없습니다.'));
    const form=node('form',undefined,'operations-form');const edit=name=>value=>{draft[name]=value;dirty=true;emit(false);};
    input(form,'kind','조치 종류',draft.kind,{options:[['link_existing','기존 원격 게시물 연결'],['confirmed_not_posted','미게시 확인'],['cancel_local','로컬 실행 취소']].filter(([kind])=>resolutionKinds().includes(kind)),change:edit('kind')});
    input(form,'note','검토 메모',draft.note,{area:true,change:edit('note')});
    const advanced=node('details');advanced.append(node('summary','고급 근거'),node('p','로컬 취소는 검토 메모만 입력하면 됩니다. 기존 게시물 연결·미게시 확인은 조치에 맞는 구조화된 근거와 서버의 독립 확인이 필요합니다.'));
    input(advanced,'evidence','확인 근거 (JSON 객체)',draft.evidence,{area:true,change:edit('evidence')});form.append(advanced);
    form.append(node('p','로컬 실행 취소는 관리 기록에만 적용됩니다. 원격 게시물 삭제·예약 취소를 수행하지 않습니다.'));
    const submit=node('button','근거와 조치 기록','btn');submit.type='submit';submit.disabled=busy||!allowed('resolve')||!resolutionKinds().includes(draft.kind);form.append(submit);
    form.addEventListener('submit',async event=>{event.preventDefault();if(busy||!allowed('resolve'))return;if(!resolutionKinds().includes(draft.kind)){message='서버가 허용한 조치 종류를 선택하세요. 입력은 보존했습니다.';emit();return;}let parsed;try{parsed=JSON.parse(draft.evidence.trim()||'{}');if(!parsed||Array.isArray(parsed)||typeof parsed!=='object')throw new Error();}catch{message='확인 근거에 JSON 객체를 입력하세요. 입력은 보존했습니다.';emit();return;}if(!draft.note.trim()){message='검토 메모를 입력하세요. 입력은 보존했습니다.';emit();return;}if(draft.kind==='cancel_local'&&Object.keys(parsed).length===0)parsed={reason:draft.note};await mutate('resolve',{expected_version:draft.expected_version,request_key:draft.request_key,kind:draft.kind,evidence:parsed,note:draft.note});});
    box.append(form);if(conflict||actionRequests.has(actionKey(detail.id,'retry'))||actionRequests.has(actionKey(detail.id,'reconcile')))box.append(button('내 입력을 유지하고 최신 버전 확인',rebase));box.append(button('미저장 입력 버리기',discard));root.append(box);
  }
  const controlName=item=>item.scope==='managed'?'전체 관리 작업':item.scope==='account'?`${accountName(item.id)} 계정`:item.target_label||`${accountName(item.id.split('.')[0])} ${platformName(item.id.split('.')[1])}`;
  function renderControls(root){
    root.append(node('h3','관리 실행 제어'),node('p','관리 일시중지는 로컬 관리 DB에만 적용됩니다. 기존 자동 작업·launchd에는 적용되지 않습니다. 재개해도 밀린 작업을 새로 등록하지 않습니다.'));
    root.append(node('p',`기존 전역 STOP: ${{clear:'해제 관측',stopped:'중지 관측',unknown:'상태 미확인'}[snapshot?.control?.global?.state]||'상태 미확인'} · 읽기 전용`));
    for(const item of snapshot?.control?.managed||[]){if(!['managed','account','connection'].includes(item.scope))continue;const controlKey=`${item.scope}-${item.id}`;let draft=controls.get(controlKey);if(!draft){draft={reason:'',request_key:key(),version:item.version};controls.set(controlKey,draft);}
      const box=node('section',undefined,'operations-control');box.append(node('h4',`${controlName(item)} · ${item.state==='paused'?'일시중지':item.state==='running'?'정상':'상태 미확인'}`));
      const identity=node('details');identity.append(node('summary','내부 제어 식별자'),node('p',`${item.scope} · ${item.id}`));box.append(identity);
      input(box,`reason-${controlKey}`,'변경 사유',draft.reason,{change:value=>{draft.reason=value;emit(false);}});
      for(const action of ['pause','resume']){const enabled=item.available_actions?.includes(action);box.append(button(`${action==='pause'?'관리 일시중지':'관리 재개'} · ${controlName(item)}`,async()=>{
        if(busy||!enabled)return;if(!draft.reason.trim()){message='변경 사유를 입력하세요. 입력은 보존했습니다.';emit();return;}busy=true;const current=generation;emit();
        try{
          const result=await api.control({scope:item.scope,id:item.id,action,expected_version:draft.version,request_key:draft.request_key,reason:draft.reason});if(current!==generation)return;
          if(result?.scope!==item.scope||result?.id!==item.id||!Number.isInteger(result.version)||result.version<=draft.version||!['paused','running'].includes(result.state))throw new Error('제어 응답 형식 오류');
          const confirmed={...item,...result};confirmedControls.set(controlKey,confirmed);
          snapshot={...snapshot,control:{...snapshot.control,managed:snapshot.control.managed.map(row=>row.scope===item.scope&&row.id===item.id?confirmed:row)}};
          controls.set(controlKey,{reason:'',request_key:key(),version:result.version});
          const loaded=await load(account);if(loaded===false)message='제어 변경은 완료됐지만 후속 조회에 실패했습니다. 저장된 상태와 버전을 보존했습니다.';
        }
        catch(error){if(current===generation){draft.conflict=error.status===409;feedback(error);}}finally{busy=false;emit();}
      },!enabled));}
      if(draft.conflict)box.append(button(`제어 최신 버전 확인 · ${controlName(item)}`,async()=>{
        if(busy)return;busy=true;const current=generation;emit();
        try{const latest=await api.list(account);if(current!==generation)return;const merged=mergeControlSnapshot(latest);const updated=merged.control?.managed?.find(value=>value.scope===item.scope&&value.id===item.id);if(!updated)throw new Error();snapshot=merged;draft.version=updated.version;draft.request_key=key();draft.conflict=false;message='제어 최신 버전을 확인했습니다. 보존한 사유를 검토하세요.';}
        catch(error){if(current===generation)feedback(error);}finally{busy=false;emit();}
      }));root.append(box);
    }
  }
  function paint(){
    for(const [mode,root] of Object.entries(roots)){
      root.replaceChildren();root.append(node('h2',mode==='issues'?'문제·복구':mode==='today'?'관리 실행 현황':'관리 실행 제어'));const status=node('p',message);status.setAttribute('role','status');status.setAttribute('aria-live','polite');root.append(status);
      root.append(node('p',snapshot?.execution_enabled===true?'관리 실행 정책이 활성 상태입니다. 각 대상의 허용 동작을 확인하세요.':'관리 실행은 기본 비활성 상태입니다. 기존 작업의 실행 여부와 별개입니다.','operations-warning'));
      for(const reason of snapshot?.blockers||[])if(typeof reason==='string')root.append(node('p',blockerText(reason)));
      if(mode==='accounts'){renderControls(root);continue;}
      if(mode==='today'){const s=snapshot?.summary||{};root.append(node('p',`관리 실행 · 진행 ${s.active??0} · 완료 ${s.completed??0} · 부분 실패 ${s.partial??0} · 확인 대기 ${s.waiting??0}`),node('p','아래 항목은 관리 실행 기록입니다. 기존 발행 관측·관리 계획은 각 화면의 별도 기록을 확인하세요.'));}
      if(mode==='issues')input(root,'issue-filter','문제 유형',filter,{options:[['all','전체 문제'],['unknown','게시 여부 불확실'],['auth_required','인증 필요'],['needs_review','검토 필요'],['failed','실패'],['retry_wait','재개 대기']],change:value=>{filter=value;emit();}});
      const items=(snapshot?.items||[]).filter(item=>mode==='today'||(item.remote_uncertain&&(filter==='all'||filter==='unknown'))||(filter==='all'?['unknown','auth_required','needs_review','failed','retry_wait'].includes(item.execution_state):item.execution_state===filter));
      if(!items.length)root.append(node('p',snapshot?'해당 실행 기록이 없습니다.':'조회된 실행 기록이 없습니다.'));
      const list=node('div',undefined,'operations-list');for(const item of items){const row=node('article',undefined,'operations-row');row.append(node('h3',item.title||'원본 제목 미수집'),node('p',item.target_label||item.connection_id||'대상 채널 미확인'),node('p',`${platformName(item.platform)} · 원본 소유 ${accountName(item.owner_account_id)} → 게시 대상 ${accountName(item.destination_account_id)}`),node('p',`계획 ${planName(item.plan_status)} · 실행 ${labels[item.execution_state]||'상태 미확인'}`),button(`상세 · ${item.title||item.id}`,()=>open(item.id)));if(item.remote_uncertain)row.append(node('p','게시 여부 불확실 · 로컬 상태와 별개로 원격 결과가 확정되지 않았습니다. 새 제출 없이 근거를 확인하세요.','operations-warning'));list.append(row);}root.append(list);renderDetail(root);
    }
  }
  function discard(){if(busy)return;dirty=false;controls.clear();if(detail)newDraft();message='미저장 입력을 버렸습니다.';emit();}
  paint();return {load,render:(mode='issues')=>{if(!roots[mode])throw new Error('알 수 없는 운영 화면입니다.');if(renderedMode!==mode){renderedMode=mode;paint();}return roots[mode];},isDirty:hasDirty,isBusy:()=>busy,discard,hasUnsavedChanges:hasDirty,discardChanges:discard};
}
