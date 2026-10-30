import {formatDateTime} from './view_helpers.js';

const scopes=new Set(['all','personal','dept']);
const accountName=id=>({personal:'개인',dept:'학과'}[id]||'미확인');
const platforms={naver_blog:'네이버 블로그',youtube:'유튜브',tiktok:'틱톡',instagram:'인스타그램',threads:'스레드',x:'엑스',tistory:'티스토리',facebook:'페이스북',blogger:'블로거',homepage:'홈페이지',kakao:'카카오'};
const metricNames={views:'조회수',likes:'좋아요',comments:'댓글',shares:'공유',reach:'도달',impressions:'노출',clicks:'클릭',subscribers:'구독자',watch_time:'시청 시간'};
const unique=rows=>[...new Map((rows||[]).filter(row=>row&&typeof row.id==='string').map(row=>[row.id,row])).values()];
const requestKey=()=>globalThis.crypto.randomUUID();

export function createMetricsApi({fetcher=globalThis.fetch}={}){
  async function request(path,body){
    const response=await fetcher(`/api/v2/metrics${path}`,{method:body===undefined?'GET':'POST',credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json',...(body===undefined?{}:{'Content-Type':'application/json'})},...(body===undefined?{}:{body:JSON.stringify(body)})});
    if(!response.ok){let code;try{code=(await response.json()).code;}catch{}throw Object.assign(new Error('성과 요청을 처리하지 못했습니다.'),{status:response.status,code});}
    return response.json();
  }
  return {
    list:(account='all')=>scopes.has(account)?request(`?account=${account}`):Promise.reject(new Error('계정 범위가 올바르지 않습니다.')),
    importPreview:()=>request('/import-preview'),
    importObservations:body=>request('/import',body),
    createProposal:body=>request('/proposals',body)
  };
}

// Each account keeps its draft and in-flight request separately. Rendering never collects or writes.
export function createMetricsPanel({api,onChange=()=>{},document=globalThis.document}={}){
  const root=document.createElement('section');root.className='metrics-panel';
  let account='all',writable=false,destroyed=false;
  let paintedAccount;
  const focusKeys=new WeakMap(),focusTargets=new Map();
  function focusTarget(element,key){focusKeys.set(element,key);focusTargets.set(key,element);return element;}
  function rememberFocus(){
    const active=document.activeElement;
    // Changes in this panel must never steal focus from the account selector or another screen.
    if(!active||!root.contains(active))return null;
    const saved={key:paintedAccount===account?focusKeys.get(active):'heading'};
    if(typeof active.selectionStart==='number'&&typeof active.selectionEnd==='number')saved.selection=[active.selectionStart,active.selectionEnd,active.selectionDirection];
    return saved;
  }
  function restoreFocus(saved){
    if(!saved)return;
    const candidate=focusTargets.get(saved.key);
    // Removed/disabled controls and account changes land on the panel heading, never another account's field.
    const target=candidate&&!candidate.disabled?candidate:focusTargets.get('heading');
    target?.focus({preventScroll:true});
    if(target===candidate&&saved.selection&&typeof target.setSelectionRange==='function'){
      try{target.setSelectionRange(...saved.selection);}catch{/* Non-text controls cannot hold a text selection. */}
    }
  }
  const states=new Map();
  const freshDraft=scope=>({account_id:scope==='all'?'':scope,title:'',note:'',selected:new Set()});
  function state(scope=account){if(!states.has(scope))states.set(scope,{scope,snapshot:null,started:false,loading:false,busy:false,readVersion:0,message:'성과 기록을 불러오세요.',owner:'all',destination:'all',draft:freshDraft(scope),proposalRequest:null,preview:null,importRequest:null});return states.get(scope);}
  const node=(tag,text,className)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text);if(className)n.className=className;return n;};
  const time=value=>value?`${formatDateTime(value)} · 한국시간`:'미확인';
  const canWrite=s=>writable&&s.snapshot?.writable===true;
  function emit(s){if(destroyed)return;if(s.scope===account)paint();onChange();}
  function feedback(error){return error?.status===401?'인증이 만료되었습니다. 다시 로그인하세요. 입력과 요청키는 보존했습니다.':error?.status===409?'원본이나 저장 상태가 바뀌었습니다. 입력·미리보기·요청키를 보존했습니다. 요청을 버리기 전에는 같은 요청으로 재시도합니다.':'요청을 처리하지 못했습니다. 입력·미리보기·요청키를 보존했습니다.';}
  function button(text,action,disabled=false){const n=focusTarget(node('button',text,'btn'),`button:${text}`);n.type='button';n.disabled=disabled;n.addEventListener('click',action);return n;}
  function field(parent,name,label,value,{options,area=false,disabled=false,change}={}){
    const wrap=node('label',label);const input=focusTarget(node(options?'select':area?'textarea':'input'),`field:${name}`);input.name=name;
    if(options)for(const [value,text] of options){const option=node('option',text);option.value=value;input.append(option);}
    input.value=value;input.disabled=disabled;input.addEventListener(options?'change':'input',()=>change(input.value));wrap.append(input);parent.append(wrap);return input;
  }
  async function load(scope=account){
    if(!scopes.has(scope))throw new Error('계정 범위가 올바르지 않습니다.');
    const s=state(scope);const version=++s.readVersion;s.started=true;s.loading=true;
    if(!api?.list){s.loading=false;s.message='성과 조회 API를 사용할 수 없습니다.';emit(s);return false;}
    emit(s);
    try{
      const data=await api.list(scope);
      if(destroyed||s.readVersion!==version)return false;
      if(!data||!Array.isArray(data.observations)||!Array.isArray(data.support)||!Array.isArray(data.proposals))throw new Error('응답 형식 오류');
      s.snapshot=data;s.message='성과 기록을 조회했습니다. 자동 수집은 실행하지 않았습니다.';return true;
    }catch(error){if(!destroyed&&s.readVersion===version)s.message=feedback(error);return false;}
    finally{if(!destroyed&&s.readVersion===version){s.loading=false;emit(s);}}
  }
  async function showPreview(s){
    if(s.busy||!canWrite(s)||!api?.importPreview)return;
    if(s.importRequest){s.message='이전 가져오기 요청과 미리보기를 보존했습니다. 같은 요청을 재시도하거나 명시적으로 버리세요.';emit(s);return;}
    s.busy=true;emit(s);
    try{const result=await api.importPreview();if(destroyed)return;if(typeof result?.preview_digest!=='string')throw new Error();s.preview=result;s.message='전체 계정 과거자료의 저장 전 미리보기입니다. 명시 저장 버튼을 눌러야 저장됩니다.';}
    catch(error){if(!destroyed)s.message=feedback(error);}finally{s.busy=false;emit(s);}
  }
  async function saveImport(s){
    if(s.busy||!canWrite(s)||s.preview?.writable!==true||!api?.importObservations)return;
    s.importRequest??={preview_digest:s.preview.preview_digest,request_key:requestKey()};s.busy=true;emit(s);
    try{
      await api.importObservations({...s.importRequest});if(destroyed)return;
      // Clear the successful mutation before the following read, which can independently fail.
      s.importRequest=null;s.preview=null;
      const refreshed=await load(s.scope);if(destroyed)return;
      s.message=refreshed?'가져오기 자료를 저장했습니다. 검증 배포와 과거 보고 자료는 분리됩니다.':'가져오기 자료를 저장했습니다. 후속 조회에 실패했습니다. 재조회로 저장 상태를 확인하세요.';
    }catch(error){if(!destroyed)s.message=feedback(error);}finally{s.busy=false;emit(s);}
  }
  async function saveProposal(s){
    if(s.busy||!canWrite(s)||!api?.createProposal)return;
    const d=s.draft;
    if(!s.proposalRequest){
      if(!scopes.has(d.account_id)||d.account_id==='all'||!d.title.trim()||!d.selected.size){s.message='제안 계정·제목·근거를 선택하세요. 입력은 보존했습니다.';emit(s);return;}
      s.proposalRequest={account_id:d.account_id,observation_ids:[...d.selected],title:d.title.trim(),note:d.note,request_key:requestKey()};
    }
    s.busy=true;emit(s);
    try{
      await api.createProposal({...s.proposalRequest,observation_ids:[...s.proposalRequest.observation_ids]});if(destroyed)return;
      s.proposalRequest=null;s.draft=freshDraft(s.scope);
      const refreshed=await load(s.scope);if(destroyed)return;
      s.message=refreshed?'기획제안 초안을 저장했습니다.':'기획제안 초안을 저장했습니다. 후속 조회에 실패했습니다. 재조회로 저장 상태를 확인하세요.';
    }catch(error){if(!destroyed)s.message=feedback(error);}finally{s.busy=false;emit(s);}
  }
  function renderObservation(parent,row,s){
    const legacy=row.source_kind==='legacy_reported';const article=node('article',undefined,'metrics-observation');
    article.append(node('h4',row.title||'제목 미수집'),node('p',`원본 소유: ${accountName(row.owner_account_id)} · 대상 계정: ${accountName(row.destination_account_id)} · 채널: ${platforms[row.platform]||'미확인'}`));
    const status=({ok:'관측 완료',unsupported:'미지원',error:'조회 오류',legacy_reported:'과거 보고 자료'}[row.status]||'미수집');article.append(node('p',`상태: ${status}`));
    if(legacy)article.append(node('p','과거 파일의 보고값입니다. 검증 배포 성과나 기간 발생량으로 합산하지 않습니다.'));
    if(row.status==='ok'||legacy&&row.status==='legacy_reported'){
      for(const [key,label] of Object.entries(metricNames)){
        const value=row.values?.[key];if(key!=='views'&&value==null)continue;
        article.append(node('p',`${legacy?'보고 ':''}${label}: ${typeof value==='number'&&Number.isFinite(value)?value.toLocaleString('ko-KR'):'미수집'}`));
      }
    }else article.append(node('p',row.status==='error'?'조회 실패로 수치를 확인할 수 없습니다.':row.status==='unsupported'?'이 항목은 조회를 지원하지 않습니다.':'관측값을 수집하지 않았습니다.'));
    article.append(node('p',`비용: ${typeof row.values?.cost==='number'&&Number.isFinite(row.values.cost)?`${row.values.cost.toLocaleString('ko-KR')} · 통화 단위 미확인`:'미확인'}`));
    const detail=node('details');detail.append(focusTarget(node('summary','관측·출처 상세'),`summary:${row.id}`));
    for(const [key,label] of [['content_id','원본 식별자'],['delivery_id','배포 식별자'],['connection_id','연결 식별자'],['target_id','대상 식별자'],['remote_id','원격 게시물 식별자']])detail.append(node('p',`${label}: ${row[key]??'미확인'}`));
    detail.append(node('p',`관측 시각: ${time(row.observed_at)}`),node('p',`자료 수집 시각: ${time(row.collected_at)}`),node('p',`파일 수정 시각: ${time(row.file_mtime)} · 관측 시각과 다릅니다.`),node('p',`정의: ${row.definition_id||'미확인'}`));
    detail.append(node('p',row.basis==='lifetime'?'기준: 누적값 · 기간 발생량이 아닙니다.':row.basis==='interval'?'기준: 명시된 기간의 관측값입니다.':'기준: 누적·기간 여부 미확인'));
    const period=row.period;detail.append(node('p',`기간: ${typeof period==='string'?period:period&&typeof period==='object'?`${time(period.start||period.start_at)} ~ ${time(period.end||period.end_at)}`:'미확인'}`));
    const source=row.source;if(source&&typeof source==='object')for(const [key,label] of [['path','자료 경로'],['kind','출처 종류'],['label','출처'],['note','출처 설명']])if(typeof source[key]==='string')detail.append(node('p',`${label}: ${source[key]}`));
    if(!source||!['path','kind','label','note'].some(key=>typeof source[key]==='string'))detail.append(node('p','출처: 미확인'));
    for(const text of Array.isArray(row.uncertainties)?row.uncertainties:[])if(typeof text==='string')detail.append(node('p',`불확실성: ${text}`));
    detail.addEventListener('keydown',event=>{if(event.key==='Escape'){detail.open=false;detail.children[0]?.focus?.();}});article.append(detail);
    const label=node('label','기획제안 근거로 선택');const check=focusTarget(node('input'),`observation:${row.id}`);check.type='checkbox';check.name=`observation-${row.id}`;check.checked=s.draft.selected.has(row.id);check.disabled=s.busy||!!s.proposalRequest||!canWrite(s);check.addEventListener('change',()=>{if(check.checked)s.draft.selected.add(row.id);else s.draft.selected.delete(row.id);});label.append(check);article.append(label);parent.append(article);
  }
  function renderSupport(s){
    const section=node('section',undefined,'metrics-support');section.append(node('h3','채널 지원 상태'),node('p','구현·권한·수집 상태는 별개입니다. 연결 도구 설치만으로 웹 인증을 확인하지 않습니다.'));
    const supplied=new Map((s.snapshot?.support||[]).map(row=>[row.platform,row]));
    const implementation={unregistered:'미등록',implemented:'구현됨',available:'구현됨',supported:'구현됨',unsupported:'추후 지원',planned:'추후 지원',future:'추후 지원',not_implemented:'미구현',unavailable:'미구현',unknown:'미확인'};
    const auth={authenticated:'확인됨',verified:'확인됨',authorized:'확인됨',connected:'확인됨',required:'인증 필요',auth_required:'인증 필요',unauthorized:'인증 필요',expired:'인증 만료',unknown:'미확인',unverified:'미확인'};
    const collection={collected:'수집됨',ok:'수집됨',not_collected:'미수집',uncollected:'미수집',disabled:'미수집',unsupported:'미지원',error:'조회 오류',unknown:'미확인'};
    for(const platform of new Set([...Object.keys(platforms),...supplied.keys()])){const row=supplied.get(platform)||{};section.append(node('p',`${platforms[platform]||row.label||'기타 채널'} · 구현: ${implementation[row.implementation_status]||'미확인'} · 권한: ${auth[row.auth_status]||'미확인'} · 수집: ${collection[row.collection_status]||'미수집'}`));}
    root.append(section);
  }
  function renderPreview(s){
    if(!s.preview)return;const box=node('section',undefined,'metrics-preview');const p=s.preview;
    box.append(node('h3','가져오기 미리보기'),node('p',`파일 행수: ${p.counts?.rows??'미확인'} · 계정 미지정: ${p.counts?.unassigned??'미확인'} · 오류: ${p.counts?.errors??'미확인'}`),node('p','전체 계정의 과거자료를 가져옵니다. 현재 계정 필터는 가져오기 범위를 바꾸지 않습니다. 저장 전 미리보기이며 파일 행수와 게시 목록은 조회수가 아닙니다.'));
    for(const file of p.files||[])if(typeof file.path==='string')box.append(node('p',`자료 파일: ${file.path}`));
    for(const warning of p.warnings||[])if(typeof warning==='string')box.append(node('p',warning));
    for(const row of unique(p.observations)){box.append(node('p',`${row.title||'제목 미수집'} · ${row.source_kind==='legacy_reported'?'과거 보고 자료':'검증 배포 관측'} · 원본 소유 ${accountName(row.owner_account_id)} · 대상 ${accountName(row.destination_account_id)}`));}
    box.append(button('미리보기 명시 저장',()=>saveImport(s),s.busy||!canWrite(s)||p.writable!==true||!api?.importObservations),button('가져오기 요청 버리기',()=>{if(s.busy)return;s.preview=null;s.importRequest=null;s.message='가져오기 미리보기와 요청을 버렸습니다.';emit(s);},s.busy));root.append(box);
  }
  function paint(){
    if(destroyed)return;const savedFocus=rememberFocus();focusTargets.clear();const s=state();root.replaceChildren();
    const heading=focusTarget(node('h2','성과'),'heading');heading.tabIndex=-1;root.append(heading,node('p','검증 배포 관측과 과거 보고 자료를 분리합니다. 서로 다른 정의·기간·채널의 수치는 합산하지 않습니다.'));
    const status=node('p',s.message);status.setAttribute('role','status');status.setAttribute('aria-live','polite');root.append(status);
    if(s.loading)root.append(node('p','성과 기록 조회 중…'));
    root.append(node('p','자동 수집은 실행하지 않습니다. 관측값이 없으면 0으로 간주하지 않습니다. 가져오기는 현재 필터와 관계없이 전체 계정의 과거자료를 저장합니다.'),button('성과 다시 조회',()=>load(account),s.loading||s.busy||!api?.list),button('가져오기 미리보기',()=>showPreview(s),s.busy||!canWrite(s)||!api?.importPreview));
    if(!canWrite(s))root.append(node('p','읽기 전용 상태입니다. 성과 저장을 사용할 수 없습니다.'));
    const filters=node('div',undefined,'metrics-filters');const options=[['all','전체'],['personal','개인'],['dept','학과'],['unknown','미확인']];
    for(const [key,label] of [['owner','원본 소유 계정'],['destination','실제 대상 계정']])field(filters,`${key}-filter`,label,s[key],{options,change:value=>{s[key]=value;emit(s);}});root.append(filters);
    const matches=(value,filter)=>filter==='all'||(filter==='unknown'?!['personal','dept'].includes(value):value===filter);
    const rows=unique(s.snapshot?.observations).filter(row=>(account==='all'||row.owner_account_id===account||row.destination_account_id===account)&&matches(row.owner_account_id,s.owner)&&matches(row.destination_account_id,s.destination));
    for(const [kind,title] of [['verified_delivery','검증 배포 관측'],['legacy_reported','과거 보고 자료']]){const box=node('section',undefined,'metrics-group');box.append(node('h3',title));const selected=rows.filter(row=>row.source_kind===kind);if(!selected.length)box.append(node('p','해당 관측 자료가 없습니다.'));for(const row of selected)renderObservation(box,row,s);root.append(box);}
    renderPreview(s);
    const form=node('form',undefined,'metrics-proposal');form.append(node('h3','근거로 기획제안 저장'),node('p','선택한 관측을 근거로 별도 기획제안 초안을 저장합니다. 원본을 자동 생성하거나 승인하지 않습니다.'));
    const locked=s.busy||!!s.proposalRequest||!canWrite(s);const d=s.draft;
    field(form,'proposal-account','제안 계정',d.account_id,{options:[['','계정 선택'],['personal','개인'],['dept','학과']],disabled:locked,change:value=>{d.account_id=value;}});
    field(form,'proposal-title','제안 제목',d.title,{disabled:locked,change:value=>{d.title=value;}});field(form,'proposal-note','검토 메모',d.note,{area:true,disabled:locked,change:value=>{d.note=value;}});
    if(s.proposalRequest)form.append(node('p','전송한 입력과 요청키를 보존했습니다. 재시도하거나 요청을 버린 뒤 수정하세요.'));
    const submit=focusTarget(node('button','기획제안 초안 저장','btn'),'proposal-submit');submit.type='submit';submit.disabled=s.busy||!canWrite(s)||!api?.createProposal;form.append(submit);form.addEventListener('submit',event=>{event.preventDefault();return saveProposal(s);});
    form.append(button('기획제안 입력·요청 버리기',()=>{if(s.busy)return;s.draft=freshDraft(account);s.proposalRequest=null;s.message='기획제안 입력과 요청을 버렸습니다.';emit(s);},s.busy));root.append(form);
    const saved=node('section');saved.append(node('h3','저장된 기획제안 초안'));for(const proposal of s.snapshot?.proposals||[]){const box=node('div');box.append(node('h4',proposal.title||'제목 없음'),node('p',proposal.note||''),node('p',`${accountName(proposal.account_id)} · 초안 · ${time(proposal.created_at)}`));saved.append(box);}if(!s.snapshot?.proposals?.length)saved.append(node('p','저장된 기획제안이 없습니다.'));root.append(saved);renderSupport(s);
    paintedAccount=account;restoreFocus(savedFocus);
  }
  return {
    render({account:scope='all',writable:allowed=false}={}){if(!scopes.has(scope))throw new Error('계정 범위가 올바르지 않습니다.');account=scope;writable=allowed;const s=state();if(!s.started){s.message='성과 기록을 불러오세요.';void load(scope);}else paint();return root;},
    load,
    destroy(){destroyed=true;for(const s of states.values())s.readVersion++;root.replaceChildren();}
  };
}
