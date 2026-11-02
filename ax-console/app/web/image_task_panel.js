// 로컬 카드·도식 이미지 제작. 명시 요청만 수행하며 자동 생성·재시도·폴링은 없다.
const FIELDS=['task_id','state','reason_code','content_id','input_revision','output_revision','asset_id','review_status'];
const CAPS=['provider_id','service_available','execution_enabled','review_status'];
const STATES={started:'이미지 제작 요청이 시작되었습니다.',unknown:'제작 결과를 알 수 없습니다. 다시 제작하지 말고 작업 기록을 확인하세요.',rendered:'이미지는 만들어졌지만 자산 등록이 남았습니다.',completed:'이미지 제작과 자산 등록이 끝났습니다 · 검토 전',failed:'이미지 제작에 실패했습니다.',content_changed:'원고가 바뀌어 이 작업은 이어갈 수 없습니다.'};
const exact=(v,keys)=>!!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const text=v=>typeof v==='string';
const validCaps=c=>exact(c,CAPS)&&c.provider_id==='local-card'&&typeof c.service_available==='boolean'&&typeof c.execution_enabled==='boolean'&&c.review_status==='not_checked';
const validRow=(r,c)=>exact(r,FIELDS)&&text(r.task_id)&&/^[A-Za-z0-9_-]{1,100}$/.test(r.task_id)&&Object.hasOwn(STATES,r.state)&&(r.reason_code===null||text(r.reason_code))&&r.content_id===c.id&&r.input_revision===c.revision&&(r.output_revision===null||(Number.isInteger(r.output_revision)&&r.output_revision>r.input_revision))&&(r.asset_id===null||(text(r.asset_id)&&r.asset_id.length>0))&&r.review_status==='not_checked'&&(r.state!=='completed'||(r.output_revision!==null&&r.asset_id!==null));
const invalid=()=>Object.assign(new Error('invalid'),{kind:'invalid'});
const UNCERTAIN='제작 결과를 확인하지 못했습니다. 입력은 보존했습니다. 작업 목록을 조회해 확인하기 전 다시 제작하지 마세요. 자동으로 다시 요청하지 않습니다.';

export function createImageTaskPanel({document,fetcher=globalThis.fetch,onChange=()=>{},onCompleted=()=>{},requestTimeoutMs=45000}={}){
  const root=document.createElement('details');root.className='panel image-task';
  let ctx=null,writable=true,caps=null,tasks=[],loaded=false,pending=null,message='',generation=0,uncertain=false,seen=new Set(),queue=[];
  let template='card',title='',body='',footer='',baseline=null;
  const snapshot=()=>({template,title,body,footer});
  const dirty=()=>!!ctx&&JSON.stringify(snapshot())!==JSON.stringify(baseline);
  const canRun=()=>!!ctx&&writable&&loaded&&caps?.service_available===true&&caps.execution_enabled===true&&pending===null;
  const canCreate=()=>canRun()&&!uncertain&&!tasks.some(t=>['started','unknown','rendered'].includes(t.state));
  const node=(tag,attrs={},value)=>{const n=document.createElement(tag);for(const [k,v]of Object.entries(attrs)){if(k==='disabled')n.disabled=v;else n.setAttribute(k,String(v));}if(value!==undefined)n.textContent=value;return n;};
  async function send(url,method,payload){
    const controller=new AbortController();let timer;
    const wait=Number.isFinite(requestTimeoutMs)&&requestTimeoutMs>0&&requestTimeoutMs<=120000?requestTimeoutMs:45000;
    try{
      const operation=(async()=>{let response;try{response=await fetcher(url,{method,credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:{Accept:'application/json',...(payload?{'Content-Type':'application/json'}:{})},...(payload?{body:JSON.stringify(payload)}:{})});}catch{throw Object.assign(new Error('network'),{kind:'network'});}if(!response.ok)throw Object.assign(new Error('http'),{kind:'http',status:response.status});try{return await response.json();}catch{throw invalid();}})();
      const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(Object.assign(new Error('timeout'),{kind:'network'}));},wait);});
      return await Promise.race([operation,deadline]);
    }finally{clearTimeout(timer);}
  }
  const note=r=>{if(r.state==='completed'&&!seen.has(r.task_id)){seen.add(r.task_id);queue.push({...r});}};
  const flush=()=>{const q=queue;queue=[];for(const r of q){try{onCompleted(r);}catch{}}};
  function upsert(r){const row=Object.fromEntries(FIELDS.map(k=>[k,r[k]]));const i=tasks.findIndex(t=>t.task_id===row.task_id);tasks=i<0?[row,...tasks]:tasks.map((t,j)=>i===j?row:t);note(row);}
  function input(label,key,value,{area=false,max=120}={}){
    const n=node(area?'textarea':'input',{...(area?{}:{type:'text'}),maxlength:max,'data-image-field':key,'aria-label':label,disabled:!writable||pending!==null});n.value=value;
    n.addEventListener('input',()=>{if(!writable||pending!==null)return;if(key==='title')title=n.value;else if(key==='body')body=n.value;else footer=n.value;onChange();});
    const l=node('label');l.append(document.createTextNode(label+' '),n);return l;
  }
  function paint(){
    const active=document.activeElement,key=active&&root.contains(active)&&active.getAttribute?active.getAttribute('data-image-field'):null;
    const range=key&&typeof active.selectionStart==='number'?[active.selectionStart,active.selectionEnd]:null;
    const summary=node('summary',{},'이미지 제작');const section=node('div',{class:'panel-body'});
    section.append(node('p',{},'로컬 템플릿으로 카드·단계 도식을 만듭니다. 버튼을 눌렀을 때만 제작하며 이미지·글의 검토와 발행은 별도로 진행합니다.'));
    if(ctx){
      section.append(node('p',{},`원고 ${ctx.id} · 버전 ${ctx.revision} · 소유 계정 ${ctx.owner_account_id}`));
      section.append(node('p',{'data-image-info':'capability'},caps===null?'펼치면 이미지 제작 기능과 저장된 작업을 조회합니다.':caps.service_available&&caps.execution_enabled?'로컬 이미지 제작을 사용할 수 있습니다. 결과는 검토 전 상태로 등록합니다.':'이미지 제작이 비활성 상태입니다. 저장된 작업 조회만 가능합니다.'));
      if(!writable)section.append(node('p',{class:'sub'},'읽기 전용 상태라 제작을 요청할 수 없습니다.'));
      const select=node('select',{'data-image-field':'template','aria-label':'이미지 형식',disabled:!writable||pending!==null});for(const [value,label]of [['card','카드'],['steps','단계 도식']])select.append(node('option',{value},label));select.value=template;select.addEventListener('change',()=>{if(!writable||pending!==null)return;template=select.value;onChange();});const label=node('label');label.append(document.createTextNode('이미지 형식 '),select);section.append(label);
      section.append(input('제목 (최대 80자)','title',title,{max:80}),input('본문 (한 줄에 한 항목, 1~6개 · 항목당 최대 120자)','body',body,{area:true,max:725}),input('하단 문구 (최대 120자)','footer',footer));
      const create=node('button',{type:'button',class:'btn btn-small','data-image-action':'create',disabled:!canCreate()},pending==='creating'?'제작 요청 중…':'이미지 제작');create.addEventListener('click',createTask);section.append(create);
      const discard=node('button',{type:'button',class:'btn btn-small','data-image-action':'discard',disabled:pending!==null},'입력 버리기');discard.addEventListener('click',()=>{if(!dirty()||pending!==null)return;if(typeof globalThis.confirm==='function'&&!globalThis.confirm('저장하지 않은 이미지 제작 입력을 버릴까요?'))return;discardChanges();});section.append(discard);
      section.append(node('h4',{},'이미지 작업'));
      if(!tasks.length)section.append(node('p',{class:'sub'},'조회된 이미지 작업이 없습니다.'));
      for(const row of tasks){const card=node('div',{'data-image-task':row.task_id});card.append(node('p',{},`작업 ${row.task_id} · ${STATES[row.state]}`),node('p',{class:'sub'},`입력 버전 ${row.input_revision}${row.output_revision!==null?' · 결과 버전 '+row.output_revision:''} · 검토 전`));if(row.reason_code!==null)card.append(node('p',{class:'sub'},row.reason_code==='content_changed'?'원고가 바뀌었습니다.':'작업 조건을 확인하지 못했습니다. 저장된 원고와 제작 설정을 확인하세요.'));if(row.state==='rendered'){const resume=node('button',{type:'button',class:'btn btn-small','data-image-action':'resume','data-image-resume':row.task_id,disabled:!canRun()},'이미지 결과 등록');resume.addEventListener('click',()=>resumeTask(row.task_id));card.append(resume);}section.append(card);}
    }else section.append(node('p',{},'원고를 열고 이 패널을 펼치면 이미지 작업을 조회합니다.'));
    const reload=node('button',{type:'button',class:'btn btn-small','data-image-action':'reload',disabled:pending!==null||!ctx},'작업 목록 다시 조회');reload.addEventListener('click',()=>load());section.append(reload,node('p',{role:'status'},message));root.replaceChildren(summary,section);
    if(key){const next=root.querySelector(`[data-image-field="${key}"]`);if(next&&!next.disabled){next.focus();if(range){next.selectionStart=range[0];next.selectionEnd=range[1];}}}
  }
  async function load(){
    if(!ctx||pending!==null)return;const mine=ctx,token=++generation;pending='loading';message='이미지 작업 조회 중';paint();onChange();
    const capRun=send('/api/v2/capabilities/image-production','GET').then(v=>({v}),e=>({e}));
    const listRun=send('/api/v2/contents/'+encodeURIComponent(mine.id)+'/image-tasks?revision='+mine.revision,'GET').then(v=>({v}),e=>({e}));
    const [c,l]=await Promise.all([capRun,listRun]);if(token!==generation)return;
    caps=!c.e&&validCaps(c.v)?c.v:null;
    const validList=!l.e&&exact(l.v,['items'])&&Array.isArray(l.v.items)&&l.v.items.every(r=>validRow(r,mine))&&new Set(l.v.items.map(r=>r.task_id)).size===l.v.items.length;
    loaded=!!validList;if(validList){tasks=l.v.items.map(r=>Object.fromEntries(FIELDS.map(k=>[k,r[k]])));tasks.forEach(note);uncertain=false;}
    message=caps&&validList?'저장된 이미지 작업을 조회했습니다. 제작은 버튼을 눌러야 요청됩니다.':'기능 상태 또는 응답의 원고 버전·형식을 확인하지 못해 제작 요청을 막았습니다. 입력은 보존했습니다.';
    pending=null;paint();onChange();flush();
  }
  function problem(){
    if(!['card','steps'].includes(template))return '이미지 형식을 선택하세요.';
    if(!title.trim()||title.length>80)return '제목은 비어 있지 않은 80자 이하 문장이어야 합니다.';
    const lines=body.split(/\r?\n/).map(s=>s.trim());
    if(lines.length<1||lines.length>6||lines.some(s=>!s||s.length>120))return '본문은 비어 있지 않은 1~6개 항목, 항목당 120자 이하로 입력하세요.';
    if(footer.length>120)return '하단 문구는 120자 이하여야 합니다.';
    return '';
  }
  function writeError(e){
    if(e.kind==='http'&&e.status===401)return '로그인 후 다시 시도하세요. 입력은 보존했습니다.';
    if(e.kind==='http'&&e.status===409)return '원고 버전이 바뀌었거나 진행 중인 작업이 있습니다. 입력은 보존했습니다. 작업 목록을 조회해 확인하세요.';
    if(e.kind==='http'&&[400,422].includes(e.status))return '제작 입력을 받아들이지 않았습니다. 제목·본문·하단 문구를 확인하세요. 입력은 보존했습니다.';
    return UNCERTAIN;
  }
  async function createTask(){
    if(!canCreate())return;const error=problem();if(error){message=error;paint();return;}
    const mine=ctx,token=++generation,sent=snapshot();pending='creating';message='이미지 제작 요청 중';paint();onChange();
    try{const row=await send('/api/v2/contents/'+encodeURIComponent(mine.id)+'/image-tasks','POST',{expected_revision:mine.revision,spec:{template:sent.template,title:sent.title,body:sent.body.split(/\r?\n/).map(s=>s.trim()),footer:sent.footer}});if(token!==generation)return;if(!validRow(row,mine))throw invalid();baseline=sent;upsert(row);message='이미지 제작 요청 결과를 저장된 작업에서 확인하세요. 결과는 검토 전입니다.';}
    catch(e){if(token===generation){message=writeError(e);if(e.kind!=='http'||![400,401,409,422].includes(e.status))uncertain=true;}}
    finally{if(token===generation){pending=null;paint();onChange();flush();}}
  }
  async function resumeTask(id){
    if(!canRun()||!tasks.some(t=>t.task_id===id&&t.state==='rendered'))return;const mine=ctx,token=++generation;pending='resuming';message='만들어진 이미지 등록 중';paint();onChange();
    try{const row=await send('/api/v2/image-tasks/'+encodeURIComponent(id)+'/resume','POST',{});if(token!==generation)return;if(!validRow(row,mine)||row.task_id!==id)throw invalid();upsert(row);message='기존 이미지의 결과 등록을 확인했습니다. 새 이미지를 제작하지 않았습니다.';}
    catch(e){if(token===generation)message=writeError(e);}
    finally{if(token===generation){pending=null;paint();onChange();flush();}}
  }
  function discardChanges(){if(pending!==null||!baseline)return;({template,title,body,footer}=baseline);message='입력 변경을 버렸습니다. 저장된 이미지 작업은 보존됩니다.';paint();onChange();}
  root.addEventListener('toggle',()=>{if(root.open&&ctx&&!loaded&&pending===null)return load();});
  paint();
  return {element:root,isDirty:dirty,isBusy:()=>pending!==null,discardChanges,
    refreshControls(options={}){if(options&&options.writable!==undefined&&writable!==(options.writable===true)){writable=options.writable===true;paint();}},
    open(content,{writable:w=true}={}){generation++;pending=null;caps=null;tasks=[];loaded=false;uncertain=false;seen=new Set();queue=[];message='';writable=w===true;ctx=null;template='card';title=body=footer='';baseline=null;
      if(content&&text(content.id)&&content.id&&Number.isInteger(content.revision)&&content.revision>=1&&text(content.manifest_hash)&&text(content.owner_account_id)&&content.owner_account_id){ctx={id:content.id,revision:content.revision,manifest_hash:content.manifest_hash,owner_account_id:content.owner_account_id};title=text(content.title)?content.title:'';baseline=snapshot();}
      paint();onChange();return root.open&&ctx?load():Promise.resolve();}
  };
}
