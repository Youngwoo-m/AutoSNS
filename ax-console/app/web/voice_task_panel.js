// 로컬 음성 제작 패널. 합성·결과 확인은 버튼 클릭 한 번이 요청 한 번이며 자동 재시도·폴링이 없고 요청 대기 시간만 제한한다.
const FIELDS=['task_id','state','reason_code','content_id','input_revision','output_revision','asset_id','seconds','review_status','voice_label','generation_id'];
const CAP_KEYS=['provider_id','service_available','execution_enabled','readiness','external_fallback'];
const STATES={started:'합성 요청이 시작되었지만 결과는 아직 확인되지 않았습니다.',pending:'합성이 진행 중이거나 대기 중입니다.',audio_ready:'음성은 만들어졌지만 자산 등록 확인이 남았습니다.',completed:'합성과 자산 등록이 끝났습니다 · 검토 전',failed:'합성에 실패했습니다.',unknown:'결과를 알 수 없습니다.',content_changed:'원고가 바뀌어 이 작업은 이어갈 수 없습니다.'};
const REASONS={voicebox_disabled:'음성 합성이 꺼져 있습니다.',voicebox_unavailable:'음성 서비스에 연결할 수 없습니다.',voicebox_generation_failed:'음성 생성에 실패했습니다.',voicebox_poll_timeout:'생성 결과 확인 시간이 지났습니다.',voicebox_audio_invalid:'만들어진 음성을 쓸 수 없습니다.',duration_exceeded:'음성이 최대 20초를 넘었습니다.',content_changed:'원고가 바뀌었습니다.',storage_error:'저장 중 문제가 생겼습니다.'};
const TASK_ID=/^[A-Za-z0-9_-]{1,100}$/;
const MAX_SCRIPT=2000,MAX_SECONDS=20,DEFAULT_SEED='14005',MAX_SEED=2147483647;
const UNCERTAIN='결과를 알 수 없습니다. 작업 목록을 조회해 확인하기 전 다시 합성하지 마세요. 자동으로 다시 요청하지 않습니다.';
const exactKeys=(o,keys)=>!!o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).length===keys.length&&keys.every(k=>Object.hasOwn(o,k));
const isStr=v=>typeof v==='string';
const isCount=v=>Number.isInteger(v)&&v>=0;
const nullable=(v,test)=>v===null||test(v);
const validCaps=c=>exactKeys(c,CAP_KEYS)&&c.provider_id==='voicebox-local'&&typeof c.service_available==='boolean'&&typeof c.execution_enabled==='boolean'&&c.readiness==='not_checked'&&c.external_fallback===false;
const validRow=(r,c)=>exactKeys(r,FIELDS)&&isStr(r.task_id)&&TASK_ID.test(r.task_id)&&isStr(r.state)&&Object.hasOwn(STATES,r.state)&&nullable(r.reason_code,isStr)&&r.content_id===c.id&&r.input_revision===c.revision&&nullable(r.output_revision,isCount)&&nullable(r.asset_id,isStr)&&nullable(r.seconds,s=>typeof s==='number'&&Number.isFinite(s)&&s>=0)&&r.review_status==='not_checked'&&nullable(r.voice_label,isStr)&&nullable(r.generation_id,isStr);
const pick=r=>Object.fromEntries(FIELDS.map(k=>[k,r[k]]));
const invalid=()=>Object.assign(new Error('invalid'),{kind:'invalid'});

export function createVoiceTaskPanel({document,fetcher=globalThis.fetch,onChange=()=>{},onCompleted=()=>{},requestTimeoutMs=45000}={}) {
  const root=document.createElement('details');root.className='panel voice-task';
  let ctx=null,writable=true,caps=null,tasks=[],script='',seed=DEFAULT_SEED,baseScript='',baseSeed=DEFAULT_SEED,pending=null,message='',generation=0,scriptInput=null,seedInput=null,seen=new Set(),queue=[],recovery=new Map();
  const dirty=()=>!!ctx&&(script!==baseScript||seed!==baseSeed||[...recovery.values()].some(d=>d.generation_id!==''));
  const canRun=()=>!!ctx&&writable&&caps!==null&&caps.service_available===true&&caps.execution_enabled===true&&pending===null;
  const canCreate=()=>canRun()&&!tasks.some(t=>t.state==='started'||t.state==='unknown')&&![...recovery.values()].some(d=>d.generation_id!=='');
  const node=(tag,attrs={},text)=>{const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='disabled')n.disabled=v;else n.setAttribute(k,String(v));}if(text!==undefined)n.textContent=text;return n;};
  async function send(url,method,body){
    const controller=new AbortController();let timer;
    const wait=Number.isFinite(requestTimeoutMs)&&requestTimeoutMs>0&&requestTimeoutMs<=120000?requestTimeoutMs:45000;
    try{
      const operation=(async()=>{
        let response;
        try{response=await fetcher(url,{method,credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});}
        catch{throw Object.assign(new Error('network'),{kind:'network'});}
        if(!response.ok)throw Object.assign(new Error('http'),{kind:'http',status:response.status});
        try{return await response.json();}catch{return null;}
      })();
      const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(Object.assign(new Error('timeout'),{kind:'network'}));},wait);});
      return await Promise.race([operation,deadline]);
    }finally{clearTimeout(timer);}
  }
  const readMessage=e=>e.kind==='invalid'?'응답의 원고 버전·형식을 확인할 수 없어 표시하지 않았습니다.':e.kind==='http'&&e.status===401?'로그인 후 다시 시도하세요. 입력은 유지됩니다.':e.kind==='network'?'서버에 연결하지 못했습니다. 입력은 유지됩니다.':'음성 작업을 조회하지 못했습니다. 입력은 유지됩니다.';
  const writeMessage=e=>{
    if(e.kind==='http'&&e.status===401)return '로그인 후 다시 시도하세요. 요청은 접수되지 않았습니다. 입력은 보존했습니다.';
    if(e.kind==='http'&&e.status===409)return '원고 버전이 바뀌었거나 음성 설정이 다르거나 이미 진행 중인 작업이 있습니다. 입력은 보존했습니다. 작업 목록과 등록 설정을 확인하세요.';
    if(e.kind==='http'&&e.status===503)return '음성 합성 서비스를 지금 사용할 수 없거나 접수 결과를 확인하지 못했습니다. 입력은 보존했습니다. 작업 목록을 조회해 확인하기 전 다시 합성하지 마세요.';
    if(e.kind==='http'&&(e.status===400||e.status===422))return '서버가 입력을 받아들이지 않았습니다. 대본과 시드를 확인하세요. 입력은 보존했습니다.';
    return UNCERTAIN;
  };
  async function fetchCaps(){
    const data=await send('/api/v2/voicebox/capabilities','GET');
    if(!validCaps(data))throw invalid();
    return {provider_id:data.provider_id,service_available:data.service_available,execution_enabled:data.execution_enabled,readiness:data.readiness,external_fallback:data.external_fallback};
  }
  async function fetchTasks(mine){
    const data=await send('/api/v2/contents/'+encodeURIComponent(mine.id)+'/voice-tasks?revision='+mine.revision,'GET');
    if(!exactKeys(data,['items'])||!Array.isArray(data.items))throw invalid();
    if(!data.items.every(r=>validRow(r,mine)))throw invalid();
    const rows=data.items.map(pick);
    if(new Set(rows.map(r=>r.task_id)).size!==rows.length)throw invalid();
    return rows;
  }
  const note=row=>{if(row.state==='completed'&&!seen.has(row.task_id)){seen.add(row.task_id);queue.push(row);}};
  const flush=()=>{const q=queue;queue=[];for(const row of q){try{onCompleted({...row});}catch{}}};
  function upsert(row){const i=tasks.findIndex(t=>t.task_id===row.task_id);if(i<0)tasks=[row,...tasks];else tasks=tasks.map((t,j)=>j===i?row:t);note(row);}
  function capText(){
    if(caps===null)return '합성 기능 상태를 확인하지 못해 합성 요청을 막았습니다. 원고를 다시 열어 확인하세요.';
    if(caps.execution_enabled!==true)return '로컬 음성 합성이 꺼져 있어 합성 요청을 할 수 없습니다. 저장된 작업 조회만 가능합니다.';
    return '로컬 음성 합성을 사용할 수 있습니다. 준비 상태는 확인되지 않았으며 외부 서비스로 대체하지 않습니다.';
  }
  function taskCard(row){
    const card=node('div',{class:'voice-task-row','data-voice-task':row.task_id});
    card.append(node('p',{},`작업 ${row.task_id} · ${STATES[row.state]}`));
    if(row.reason_code!==null)card.append(node('p',{class:'sub'},Object.hasOwn(REASONS,row.reason_code)?REASONS[row.reason_code]:'자세한 사유는 표시하지 않습니다.'));
    const facts=[`입력 원고 버전 ${row.input_revision}`];
    if(row.output_revision!==null)facts.push(`결과 원고 버전 ${row.output_revision}`);
    if(row.asset_id!==null)facts.push(`자산 ${row.asset_id}`);
    if(row.seconds!==null)facts.push(`${row.seconds}초`);
    if(row.voice_label!==null)facts.push(`음성 ${row.voice_label}`);
    facts.push('검토 전');
    card.append(node('p',{class:'sub'},facts.join(' · ')));
    if(row.state==='started'||row.state==='unknown'){
      card.append(node('p',{class:'sub'},'생성 결과를 확인하기 전 다시 합성하지 마세요. 기존 생성 ID를 알고 있다면 아래에서 대본·음성 설정을 대조한 뒤 연결할 수 있습니다.'));
      if(!recovery.has(row.task_id))recovery.set(row.task_id,{generation_id:'',preview:null});
      const draft=recovery.get(row.task_id);
      const candidate=node('input',{type:'text',maxlength:128,'aria-label':'기존 생성 ID','data-voice-recovery-input':row.task_id,disabled:!canRun()});candidate.value=draft.generation_id;
      const label=node('label');label.append(document.createTextNode('기존 생성 ID '),candidate);card.append(label);
      const inspect=node('button',{type:'button',class:'btn btn-small','data-voice-action':'inspect-recovery','data-voice-recovery-task':row.task_id,disabled:!canRun()},'기존 음성 대조');
      inspect.addEventListener('click',()=>inspectRecovery(row.task_id));card.append(inspect);
      const confirm=node('button',{type:'button',class:'btn btn-small','data-voice-action':'confirm-recovery','data-voice-recovery-task':row.task_id,disabled:!canRun()||!draft.preview},'대조한 음성 연결');
      confirm.addEventListener('click',()=>confirmRecovery(row.task_id));card.append(confirm);
      candidate.addEventListener('input',()=>{if(!canRun())return;draft.generation_id=candidate.value;draft.preview=null;confirm.disabled=true;onChange();});
      if(draft.preview)card.append(node('p',{class:'sub'},'대본과 등록 음성 설정이 일치합니다. 연결을 확정하면 새 합성 없이 기존 결과 확인을 이어갑니다. 검토 완료를 뜻하지 않습니다.'));
    }
    if(row.state==='pending'||row.state==='audio_ready'){
      const resume=node('button',{type:'button',class:'btn btn-small','data-voice-action':'resume','data-voice-resume':row.task_id,disabled:!canRun()},'결과 확인');
      resume.addEventListener('click',()=>resumeTask(row.task_id));card.append(resume);
    }
    return card;
  }
  function paint(){
    const active=document.activeElement;
    const focusKey=active&&root.contains(active)&&active.getAttribute?active.getAttribute('data-voice-field'):null;
    const range=focusKey&&typeof active.selectionStart==='number'?[active.selectionStart,active.selectionEnd]:null;
    scriptInput=seedInput=null;
    const summary=node('summary',{},'음성 제작');const body=node('div',{class:'panel-body'});
    body.append(node('p',{},'AI 합성 음성 · 본인 목소리 복제 · 검토 전 · 최대 20초. 합성은 아래 버튼을 눌렀을 때만 한 번 요청하며 자동 재시도나 반복 조회는 없습니다.'));
    if(ctx){
      body.append(node('p',{'data-voice-info':'content'},`원고 ${ctx.id} · 버전 ${ctx.revision} · 소유 계정 ${ctx.owner_account_id}`));
      body.append(node('p',{class:'sub'},`원고 해시 ${ctx.manifest_hash.slice(0,12)}`));
      body.append(node('p',{'data-voice-info':'capability'},capText()));
      if(!writable)body.append(node('p',{class:'sub'},'읽기 전용 상태라 합성을 요청할 수 없습니다.'));
      const locked=!writable||pending!==null;
      scriptInput=node('textarea',{maxlength:MAX_SCRIPT,'data-voice-field':'script','aria-label':'합성할 대본',disabled:locked});scriptInput.value=script;
      scriptInput.addEventListener('input',()=>{if(!writable||pending!==null)return;script=scriptInput.value;onChange();});
      const sl=node('label');sl.append(document.createTextNode(`대본 (최대 ${MAX_SCRIPT}자 · 원고 본문은 자동으로 복사되지 않습니다) `),scriptInput);body.append(sl);
      seedInput=node('input',{type:'number',min:0,step:1,inputmode:'numeric','data-voice-field':'seed','aria-label':'시드',disabled:locked});seedInput.value=seed;
      seedInput.addEventListener('input',()=>{if(!writable||pending!==null)return;seed=seedInput.value;onChange();});
      const dl=node('label');dl.append(document.createTextNode('시드 '),seedInput);body.append(dl);
      if(dirty())body.append(node('p',{class:'sub'},'아직 합성 요청에 쓰이지 않은 입력이 있습니다.'));
      const create=node('button',{type:'button',class:'btn btn-small','data-voice-action':'create',disabled:!canCreate()},pending==='creating'?'요청 중…':'합성 요청');
      create.addEventListener('click',createTask);body.append(create);
      const discard=node('button',{type:'button',class:'btn btn-small','data-voice-action':'discard',disabled:pending!==null},'입력 버리기');
      discard.addEventListener('click',()=>{
        if(!ctx||pending!==null||!dirty())return;
        if(typeof globalThis.confirm==='function'&&!globalThis.confirm('대본·시드 변경과 확정하지 않은 복구 입력을 버릴까요?'))return;
        script=baseScript;seed=baseSeed;recovery=new Map();message='입력 변경을 버렸습니다. 저장된 음성 작업은 보존됩니다.';paint();onChange();
      });body.append(discard);
      body.append(node('h4',{},'음성 작업'));
      if(!tasks.length)body.append(node('p',{class:'sub'},'조회된 음성 작업이 없습니다.'));
      tasks.forEach(t=>body.append(taskCard(t)));
    }else body.append(node('p',{},'원고를 열면 저장된 음성 작업을 조회합니다.'));
    const reload=node('button',{type:'button',class:'btn btn-small','data-voice-action':'reload',disabled:pending!==null||!ctx},'작업 목록 다시 조회');
    reload.addEventListener('click',reloadTasks);
    body.append(reload,node('p',{role:'status'},message));
    root.replaceChildren(summary,body);
    const target=focusKey==='script'?scriptInput:focusKey==='seed'?seedInput:null;
    if(target){target.focus();if(range&&typeof target.setSelectionRange==='function')target.setSelectionRange(range[0],range[1]);}
  }
  async function reloadTasks(){
    if(!ctx||pending!==null)return;
    const token=++generation,mine=ctx;pending='loading';message='작업 목록 조회 중';paint();onChange();
    try{const rows=await fetchTasks(mine);if(token!==generation)return;tasks=rows;rows.forEach(note);message='저장된 작업 목록을 조회했습니다. 입력은 그대로 두었습니다.';}
    catch(e){if(token===generation)message=readMessage(e);}
    finally{if(token===generation){pending=null;paint();onChange();flush();}}
  }
  function localProblem(){
    if(script.trim()==='')return '합성할 대본을 입력하세요.';
    if(script.length>MAX_SCRIPT)return `대본은 ${MAX_SCRIPT}자 이하여야 합니다.`;
    if(!/^[0-9]{1,10}$/.test(seed)||Number(seed)>MAX_SEED)return '시드는 0부터 2147483647까지의 정수여야 합니다.';
    return '';
  }
  async function createTask(){
    if(!canCreate())return;
    const problem=localProblem();if(problem){message=problem;paint();return;}
    const token=++generation,mine=ctx,sent={script,seed};
    pending='creating';message='합성 요청 전송 중 · 결과가 나올 때까지 다시 누르지 마세요';paint();onChange();
    try{
      const data=await send('/api/v2/contents/'+encodeURIComponent(mine.id)+'/voice-tasks','POST',{expected_revision:mine.revision,script:sent.script,seed:Number(sent.seed)});
      if(token!==generation)return;
      if(!validRow(data,mine))throw invalid();
      baseScript=sent.script;baseSeed=sent.seed;
      upsert(pick(data));message='합성 요청을 보냈습니다. 상태는 아래 작업에서 확인하세요. 검토 전 음성입니다.';
    }catch(e){if(token===generation)message=writeMessage(e);}
    finally{if(token===generation){pending=null;paint();onChange();flush();}}
  }
  async function resumeTask(id){
    if(!canRun())return;
    const target=tasks.find(t=>t.task_id===id);
    if(!target||(target.state!=='pending'&&target.state!=='audio_ready'))return;
    const token=++generation,mine=ctx;
    pending='resuming';message='결과 확인 요청 전송 중';paint();onChange();
    try{
      const data=await send('/api/v2/voice-tasks/'+encodeURIComponent(id)+'/resume','POST',{});
      if(token!==generation)return;
      if(!validRow(data,mine)||data.task_id!==id)throw invalid();
      upsert(pick(data));message='작업 결과를 확인했습니다.';
    }catch(e){if(token===generation)message=writeMessage(e);}
    finally{if(token===generation){pending=null;paint();onChange();flush();}}
  }
  const recoveryError=e=>e.kind==='http'&&e.status===401?'로그인 후 다시 대조하세요. 입력은 유지됩니다.':e.kind==='http'&&e.status===409?'작업이 처리 중이거나 대조 내용이 달라 연결하지 않았습니다. 저장된 작업을 조회한 뒤 다시 대조하세요.':'기존 음성과 이 작업의 일치 여부를 확인하지 못했습니다. 입력을 보존했고 새 합성은 하지 않았습니다.';
  async function inspectRecovery(id){
    if(!canRun())return;
    const row=tasks.find(t=>t.task_id===id),draft=recovery.get(id);
    if(!row||!['started','unknown'].includes(row.state)||!draft)return;
    if(!/^[A-Za-z0-9_-]{1,128}$/.test(draft.generation_id)){message='기존 생성 ID의 형식을 확인하세요.';paint();return;}
    const token=++generation,candidate=draft.generation_id;draft.preview=null;pending='inspecting';message='기존 음성 대조 중';paint();onChange();
    try{
      const result=await send('/api/v2/voice-tasks/'+encodeURIComponent(id)+'/recovery-preview','POST',{generation_id:candidate});
      if(token!==generation)return;
      if(!exactKeys(result,['task_id','generation_id','recovery_fingerprint','task_state','can_confirm','review_status'])||result.task_id!==id||result.generation_id!==candidate||!['started','unknown'].includes(result.task_state)||result.can_confirm!==true||result.review_status!=='not_checked'||typeof result.recovery_fingerprint!=='string'||!/^[a-f0-9]{64}$/.test(result.recovery_fingerprint))throw invalid();
      draft.preview={...result};message='기존 음성을 대조했습니다. 연결 버튼으로 확정하세요. 아직 작업 상태를 바꾸지 않았습니다.';
    }catch(e){if(token===generation)message=recoveryError(e);}
    finally{if(token===generation){pending=null;paint();onChange();}}
  }
  async function confirmRecovery(id){
    if(!canRun())return;
    const row=tasks.find(t=>t.task_id===id),draft=recovery.get(id);
    if(!row||!['started','unknown'].includes(row.state)||!draft?.preview||draft.preview.generation_id!==draft.generation_id)return;
    const token=++generation,mine=ctx,preview={...draft.preview};pending='recovering';message='대조한 기존 음성 연결 중';paint();onChange();
    try{
      const result=await send('/api/v2/voice-tasks/'+encodeURIComponent(id)+'/recover','POST',{generation_id:preview.generation_id,recovery_fingerprint:preview.recovery_fingerprint});
      if(token!==generation)return;
      if(!validRow(result,mine)||result.task_id!==id||!['pending','audio_ready','completed'].includes(result.state)||result.generation_id!==preview.generation_id)throw invalid();
      recovery.delete(id);upsert(pick(result));message='기존 음성을 연결했습니다. 새 합성 없이 결과 확인을 이어갈 수 있습니다. 검토 전입니다.';
    }catch(e){if(token===generation)message=recoveryError(e);}
    finally{if(token===generation){pending=null;paint();onChange();flush();}}
  }
  paint();
  return {
    element:root,isDirty:dirty,isBusy:()=>pending!==null,
    discardChanges(){script=baseScript;seed=baseSeed;recovery=new Map();paint();onChange();},
    refreshControls(options={}){
      if(!options||options.writable===undefined)return;
      const next=options.writable===true;
      if(next===writable)return;
      writable=next;paint();
    },
    open(content,{writable:w=true}={}){
      generation++;pending=null;caps=null;tasks=[];script=baseScript='';seed=baseSeed=DEFAULT_SEED;seen=new Set();queue=[];recovery=new Map();message='';writable=w===true;
      const ok=content&&typeof content.id==='string'&&content.id&&Number.isInteger(content.revision)&&content.revision>=1&&typeof content.manifest_hash==='string'&&typeof content.owner_account_id==='string'&&content.owner_account_id;
      if(!ok){ctx=null;if(content)message='원고 정보를 확인할 수 없어 음성 작업을 조회하지 않았습니다.';paint();onChange();return Promise.resolve();}
      ctx={id:content.id,revision:content.revision,manifest_hash:content.manifest_hash,owner_account_id:content.owner_account_id};
      const mine=ctx,token=generation;pending='loading';message='조회 중';paint();onChange();
      const capsRun=fetchCaps().then(v=>({v}),e=>({e}));
      const listRun=fetchTasks(mine).then(v=>({v}),e=>({e}));
      return (async()=>{
        const [c,l]=await Promise.all([capsRun,listRun]);
        if(token!==generation)return;
        caps=c.e?null:c.v;
        if(!l.e){tasks=l.v;l.v.forEach(note);}
        const problems=[];
        if(c.e)problems.push('합성 기능 상태를 확인하지 못해 합성 요청을 막았습니다.');
        if(l.e)problems.push(readMessage(l.e));
        message=problems.length?problems.join(' '):'저장된 음성 작업을 조회했습니다. 합성 요청은 버튼을 눌러야만 보냅니다.';
        pending=null;paint();onChange();flush();
      })();
    }
  };
}
