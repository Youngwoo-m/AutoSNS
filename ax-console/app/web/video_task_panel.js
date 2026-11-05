// 로컬 영상 제작 패널. 제작 요청·결과 등록 재개·사람 검토 기록은 버튼 클릭 한 번이 요청 한 번이며 자동 재시도·폴링이 없고 요청 대기 시간만 제한한다.
const FIELDS=['task_id','state','reason_code','content_id','input_revision','plan_revision','output_revision','asset_id','review_status'];
const CAP_KEYS=['provider_id','service_available','execution_enabled','review_status'];
const PLAN_KEYS=['content_id','content_revision','manifest_hash','owner_account_id','plan_revision','plan','inputs_ready','blockers','execution_enabled','review_status'];
const PLAN_BODY_KEYS=['exam','field','source','footer','disclosure','voice_asset_id','scenes'];
const SCENE_KEYS=['asset_id','kind','seconds','title','caption'];
const REVIEW_KEYS=['task_id','state','content_id','input_revision','plan_revision','context_fingerprint','scene_count','media','manifest','review_status'];
const MEDIA_KEYS=['filename','media_type','size','sha256','seconds','width','height','has_audio'];
const MANIFEST_KEYS=['exam','field','source','footer','disclosure','scenes','scene_count'];
const REVIEW_SCENE_KEYS=['index','kind','seconds','title','caption'];
const CHECKS=[['audio_checked','음성 내용이 끝까지 명료하게 들립니다'],['font_checked','한글 글자가 모두 읽히고 깨지지 않습니다'],['disclosure_checked','AI 합성 고지가 보입니다'],['scenes_checked','모든 장면과 자막을 확인했습니다']];
const CHECK_KEYS=CHECKS.map(([k])=>k);
const DECISIONS=[['pass','검토 확인 후 등록'],['changes_requested','수정 요청']];
const MAX_NOTES=2000;
const STATES={queued:'제작 대기열에 등록되었습니다. 아직 렌더링이 시작되지 않았을 수 있습니다.',preparing:'제작 입력을 준비하는 중입니다.',rendering:'영상을 렌더링하는 중입니다.',awaiting_review:'영상은 만들어졌지만 사람 검토 기록이 남아 아직 등록되지 않았습니다.',rendered:'영상은 만들어졌지만 결과 등록 확인이 남았습니다.',completed:'영상 생성과 자산 등록이 끝났습니다 · 검토 전',blocked:'제작 조건이 맞지 않아 진행하지 못했습니다.',failed:'영상 제작에 실패했습니다.',unknown:'결과를 알 수 없습니다.',content_changed:'원고가 바뀌어 이 작업은 이어갈 수 없습니다.'};
const REASONS={content_changed:'원고가 바뀌었습니다.',plan_changed:'제작 계획이 바뀌었습니다.',content_store_unavailable:'원고 저장소를 사용할 수 없습니다.',media_inputs_required:'제작에 필요한 입력이 부족합니다.',media_prepare_failed:'제작 입력을 준비하지 못했습니다.',media_render_blocked:'렌더링이 막혔습니다.',render_outcome_unknown:'렌더링 결과를 확인하지 못했습니다.',render_result_invalid:'렌더링 결과를 쓸 수 없습니다.',render_artifact_invalid:'만들어진 영상 파일을 쓸 수 없습니다.',invalid_production_result:'제작 결과가 올바르지 않습니다.',video_ingest_rejected:'영상 자산 등록이 거절되었습니다.',renderer_unavailable:'영상 렌더러를 사용할 수 없습니다.',reuse_not_authorized:'기존 결과를 다시 쓸 수 없습니다.',scene_asset_unregistered:'등록되지 않은 장면 이미지가 있습니다.',scene_asset_mismatch:'장면 이미지가 계획과 다릅니다.',scene_asset_changed:'장면 이미지가 바뀌었습니다.',asset_changed:'자산이 바뀌었습니다.',missing_required_media:'필요한 이미지나 음성이 없습니다.',media_too_large:'미디어 용량이 너무 큽니다.',unsafe_artifact_path:'결과 파일 위치를 쓸 수 없습니다.',unsupported_media:'지원하지 않는 미디어 형식입니다.',invalid_media_manifest:'미디어 목록이 올바르지 않습니다.',synthetic_disclosure_required:'AI 합성 고지가 필요합니다.',duration_exceeded:'영상이 최대 20초를 넘었습니다.',audio_required:'WAV 음성이 필요합니다.',invalid_scene_registration:'장면 이미지 등록이 올바르지 않습니다.',generation_not_authorized:'이 제작은 허용되지 않았습니다.',media_probe_failed:'미디어를 검사하지 못했습니다.',video_dimensions_or_audio:'영상 크기 또는 음성이 규격에 맞지 않습니다.',font_unchecked:'글꼴 확인이 끝나지 않았습니다.',video_unchecked:'영상 확인이 끝나지 않았습니다.',video_scenes_unchecked:'장면 확인이 끝나지 않았습니다.',video_review_required:'사람이 영상을 확인하고 기록해야 등록됩니다.',video_review_changes_requested:'사람 검토에서 수정 요청이 기록되어 영상을 등록하지 않았습니다.',invalid_media_result:'미디어 결과가 올바르지 않습니다.',template_changed:'영상 틀이 바뀌었습니다.',artifact_already_exists:'같은 결과 파일이 이미 있습니다.',remotion_render_failed:'영상 렌더링에 실패했습니다.',media_render_failed:'미디어 렌더링에 실패했습니다.',media_validation_failed:'미디어 검증에 실패했습니다.',invalid_remotion_registration:'렌더 결과 등록이 올바르지 않습니다.',video_task_error:'영상 작업 처리 중 문제가 생겼습니다.'};
const BLOCKERS={voice_required:'WAV 음성이 필요합니다.',diorama_required:'디오라마 장면이 2~3장이어야 합니다.',distinct_diorama_required:'디오라마에 서로 다른 이미지가 2장 이상 필요합니다.',scenes_required:'장면이 하나 이상 필요합니다.'};
const ACCOUNTS={dept:'학과',personal:'개인'};
const KINDS={diorama:'디오라마',diagram:'도식'};
const ACTIVE=['queued','preparing','rendering','awaiting_review','rendered','unknown'];
const TASK_ID=/^[A-Za-z0-9_-]{1,100}$/;
const HEX64=/^[0-9a-f]{64}$/;
const UNCERTAIN='접수 결과를 알 수 없습니다. 영상 작업 목록을 다시 조회해 확인하기 전에는 제작을 다시 요청하지 마세요. 자동으로 다시 요청하지 않습니다.';
const exactKeys=(o,keys)=>!!o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).length===keys.length&&keys.every(k=>Object.hasOwn(o,k));
const isStr=v=>typeof v==='string';
const isCount=v=>Number.isInteger(v)&&v>=0;
const isPositive=v=>Number.isInteger(v)&&v>0;
const nullable=(v,test)=>v===null||test(v);
const validCaps=c=>exactKeys(c,CAP_KEYS)&&c.provider_id==='remotion-local'&&typeof c.service_available==='boolean'&&typeof c.execution_enabled==='boolean'&&c.review_status==='not_checked';
const validScene=s=>exactKeys(s,SCENE_KEYS)&&isStr(s.asset_id)&&(s.kind==='diorama'||s.kind==='diagram')&&typeof s.seconds==='number'&&Number.isFinite(s.seconds)&&s.seconds>0&&isStr(s.title)&&isStr(s.caption);
const validPlanBody=p=>exactKeys(p,PLAN_BODY_KEYS)&&['exam','field','source','footer','disclosure'].every(k=>isStr(p[k]))&&nullable(p.voice_asset_id,isStr)&&Array.isArray(p.scenes)&&p.scenes.every(validScene);
const validPlan=(r,c)=>exactKeys(r,PLAN_KEYS)&&r.content_id===c.id&&r.content_revision===c.revision&&r.manifest_hash===c.manifest_hash&&r.owner_account_id===c.owner_account_id&&Number.isInteger(r.plan_revision)&&r.plan_revision>=0&&validPlanBody(r.plan)&&typeof r.inputs_ready==='boolean'&&Array.isArray(r.blockers)&&r.blockers.every(isStr)&&r.execution_enabled===false&&r.review_status==='not_checked';
const validRow=(r,c)=>exactKeys(r,FIELDS)&&isStr(r.task_id)&&TASK_ID.test(r.task_id)&&isStr(r.state)&&Object.hasOwn(STATES,r.state)&&nullable(r.reason_code,isStr)&&r.content_id===c.id&&r.input_revision===c.revision&&Number.isInteger(r.plan_revision)&&r.plan_revision>=1&&nullable(r.output_revision,isCount)&&nullable(r.asset_id,isStr)&&r.review_status==='not_checked'&&(r.state!=='completed'||(Number.isInteger(r.output_revision)&&r.output_revision>r.input_revision&&isStr(r.asset_id)&&r.asset_id!==''));
const validMedia=m=>exactKeys(m,MEDIA_KEYS)&&m.filename==='short.mp4'&&m.media_type==='video/mp4'&&isPositive(m.size)&&isStr(m.sha256)&&HEX64.test(m.sha256)&&typeof m.seconds==='number'&&Number.isFinite(m.seconds)&&m.seconds>=0&&m.seconds<=20&&m.width===1080&&m.height===1920&&m.has_audio===true;
const validReviewScene=(s,i)=>exactKeys(s,REVIEW_SCENE_KEYS)&&s.index===i+1&&(s.kind==='diorama'||s.kind==='diagram')&&typeof s.seconds==='number'&&Number.isFinite(s.seconds)&&s.seconds>0&&isStr(s.title)&&isStr(s.caption);
const validManifest=(m,count)=>exactKeys(m,MANIFEST_KEYS)&&['exam','field','source','footer','disclosure'].every(k=>isStr(m[k]))&&Array.isArray(m.scenes)&&m.scenes.length===count&&m.scene_count===count&&m.scenes.every(validReviewScene);
// 응답은 현재 작업 행과 정확히 같은 작업·원고·계획 버전일 때만 쓴다. 틀리면 통째로 버리고 내용을 보여주지 않는다.
const validReview=(d,row)=>exactKeys(d,REVIEW_KEYS)&&d.task_id===row.task_id&&d.state==='awaiting_review'&&d.content_id===row.content_id&&d.input_revision===row.input_revision&&d.plan_revision===row.plan_revision&&isStr(d.context_fingerprint)&&HEX64.test(d.context_fingerprint)&&isPositive(d.scene_count)&&validMedia(d.media)&&validManifest(d.manifest,d.scene_count)&&d.review_status==='not_checked';
const pick=r=>Object.fromEntries(FIELDS.map(k=>[k,r[k]]));
const invalid=()=>Object.assign(new Error('invalid'),{kind:'invalid'});
const previewUrl=id=>'/api/v2/video-tasks/'+encodeURIComponent(id)+'/preview';

export function createVideoTaskPanel({document,fetcher=globalThis.fetch,onChange=()=>{},onCompleted=()=>{},requestTimeoutMs=45000}={}) {
  const root=document.createElement('details');root.className='panel video-task';
  // stale: 마지막 조회가 실패했거나 아직 성공하지 않아 상태를 믿을 수 없다. uncertain: 제작 접수·검토 저장 결과가 불명확하다. 둘 다 전체 조회가 성공해야 풀린다.
  // review: 열어 둔 검토 초안. 서버 응답에서 검증한 표시값(info)과 사람이 고친 값(checks·decision·notes)만 가진다.
  let ctx=null,writable=true,caps=null,plan=null,tasks=[],pending=null,message='',generation=0,seen=new Set(),queue=[],stale=true,uncertain=false,review=null,fields={},submitBtn=null;
  const isDirty=()=>!!review&&(CHECK_KEYS.some(k=>review.checks[k]===true)||review.notes!==''||review.decision!=='pass');
  const reviewReady=r=>r.notes.length<=MAX_NOTES&&(r.decision==='pass'?CHECK_KEYS.every(k=>r.checks[k]===true):r.decision==='changes_requested'&&r.notes.trim()!=='');
  const canMutate=()=>!!ctx&&writable&&pending===null&&!stale&&!uncertain&&caps!==null&&caps.service_available===true&&caps.execution_enabled===true;
  const canEnqueue=()=>canMutate()&&plan!==null&&plan.inputs_ready===true&&plan.plan_revision>=1&&!tasks.some(t=>ACTIVE.includes(t.state));
  const canSubmit=()=>!!review&&canMutate()&&tasks.some(t=>t.task_id===review.id&&t.state==='awaiting_review')&&reviewReady(review);
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
  const readMessage=e=>e.kind==='invalid'?'응답의 원고 버전·소유 계정·형식을 확인할 수 없어 표시하지 않았습니다.':e.kind==='http'&&e.status===401?'로그인 후 다시 조회하세요.':e.kind==='network'?'서버에 연결하지 못했습니다.':'영상 제작 상태를 조회하지 못했습니다.';
  const definite=e=>e.kind==='http'&&[400,401,404,409,422].includes(e.status);
  const writeMessage=e=>{
    if(e.kind==='http'&&e.status===401)return '로그인 후 다시 시도하세요. 요청은 접수되지 않았습니다.';
    if(e.kind==='http'&&e.status===409)return '원고·제작 계획 버전이 바뀌었거나 이미지 재사용 확인이 부족하거나 이미 진행 중인 작업이 있습니다. 요청은 접수되지 않았습니다. 영상 작업을 다시 조회해 확인하세요.';
    if(e.kind==='http'&&(e.status===400||e.status===404||e.status===422))return '서버가 요청을 받아들이지 않았습니다. 영상 작업을 다시 조회해 확인하세요.';
    return UNCERTAIN;
  };
  const reviewReadMessage=e=>{
    if(e.kind==='invalid')return '검토 정보의 작업·원고 버전·형식을 확인할 수 없어 표시하지 않았습니다.';
    if(e.kind==='http'&&e.status===401)return '로그인 후 다시 시도하세요.';
    if(e.kind==='http'&&[404,409].includes(e.status))return '검토할 수 있는 상태가 아니거나 영상이 바뀌었습니다. 영상 작업을 다시 조회하세요.';
    if(e.kind==='network')return '서버에 연결하지 못했습니다.';
    return '영상 검토 정보를 조회하지 못했습니다.';
  };
  const reviewWriteMessage=e=>{
    if(e.kind==='http'&&e.status===401)return '로그인 후 다시 시도하세요. 입력은 그대로 두었고 요청은 접수되지 않았습니다.';
    if(e.kind==='http'&&e.status===409)return '영상 또는 작업 상태가 바뀌어 저장되지 않았습니다. 입력은 그대로 두었습니다. 영상 작업을 다시 조회해 확인하세요.';
    if(e.kind==='http'&&(e.status===400||e.status===404||e.status===422))return '서버가 검토 기록을 받아들이지 않았습니다. 입력은 그대로 두었습니다. 영상 작업을 다시 조회해 확인하세요.';
    return '검토 저장 결과를 알 수 없습니다. 입력은 그대로 두었습니다. 영상 작업을 다시 조회해 확인하기 전에는 다시 보내지 마세요. 자동으로 다시 요청하지 않습니다.';
  };
  async function fetchCaps(){
    const data=await send('/api/v2/video/capabilities','GET');
    if(!validCaps(data))throw invalid();
    return {provider_id:data.provider_id,service_available:data.service_available,execution_enabled:data.execution_enabled,review_status:data.review_status};
  }
  async function fetchPlan(mine){
    const data=await send('/api/v2/contents/'+encodeURIComponent(mine.id)+'/media-plan?revision='+mine.revision,'GET');
    if(!validPlan(data,mine))throw invalid();
    return {plan_revision:data.plan_revision,inputs_ready:data.inputs_ready,blockers:[...data.blockers],scene_count:data.plan.scenes.length};
  }
  async function fetchTasks(mine){
    const data=await send('/api/v2/contents/'+encodeURIComponent(mine.id)+'/video-tasks?revision='+mine.revision,'GET');
    if(!exactKeys(data,['items'])||!Array.isArray(data.items))throw invalid();
    if(!data.items.every(r=>validRow(r,mine)))throw invalid();
    const rows=data.items.map(pick);
    if(new Set(rows.map(r=>r.task_id)).size!==rows.length)throw invalid();
    return rows;
  }
  const note=row=>{if(row.state==='completed'&&!seen.has(row.task_id)){seen.add(row.task_id);queue.push(row);}};
  const flush=()=>{const q=queue;queue=[];for(const row of q){try{onCompleted({...row});}catch{}}};
  function upsert(row){const i=tasks.findIndex(t=>t.task_id===row.task_id);if(i<0)tasks=[row,...tasks];else tasks=tasks.map((t,j)=>j===i?row:t);note(row);}
  // 세 GET을 함께 조회한다. 하나라도 실패하면 이전 값을 지우지 않고 변경 요청만 닫는다.
  async function loadAll(mine,token){
    const settle=p=>p.then(v=>({v}),e=>({e}));
    const [c,p,l]=await Promise.all([settle(fetchCaps()),settle(fetchPlan(mine)),settle(fetchTasks(mine))]);
    if(token!==generation)return false;
    const problems=[];
    if(!c.e)caps=c.v;else{caps=null;problems.push('영상 제작 기능 상태를 확인하지 못해 요청을 막았습니다.');}
    if(!p.e)plan=p.v;else{plan=null;problems.push('저장된 제작 계획을 확인하지 못해 요청을 막았습니다. '+readMessage(p.e));}
    if(!l.e){tasks=l.v;l.v.forEach(note);if(review&&!isDirty())review=null;}else problems.push('영상 작업 목록을 갱신하지 못해 이전 목록을 그대로 두고 요청을 막았습니다. '+readMessage(l.e));
    stale=problems.length>0;
    if(!stale)uncertain=false;
    message=stale?problems.join(' '):'저장된 영상 작업과 제작 계획을 조회했습니다. 제작 요청은 버튼을 눌러야만 보냅니다.';
    return true;
  }
  function capText(){
    if(caps===null)return '영상 제작 기능 상태를 확인하지 못해 요청을 막았습니다. 영상 작업을 다시 조회하세요.';
    if(caps.service_available!==true)return '영상 제작 서비스가 연결되어 있지 않아 제작 요청을 할 수 없습니다. 저장된 작업 조회만 가능합니다.';
    if(caps.execution_enabled!==true)return '로컬 영상 제작이 꺼져 있어 제작 요청을 할 수 없습니다. 저장된 작업 조회만 가능합니다.';
    return '로컬 영상 제작을 사용할 수 있습니다. 외부 서비스로 대체하지 않으며 게시도 하지 않습니다.';
  }
  function planText(){
    if(plan===null)return '저장된 제작 계획을 확인하지 못했습니다.';
    if(plan.plan_revision<1)return '저장된 제작 계획이 없습니다. 제작 계획을 먼저 저장하세요.';
    const head=`저장된 계획 버전 ${plan.plan_revision} · 장면 ${plan.scene_count}개 · `;
    return head+(plan.inputs_ready?'입력 조건을 모두 채웠습니다. 다만 영상 품질 검토를 마쳤다는 뜻은 아닙니다.':'부족한 입력: '+plan.blockers.map(b=>BLOCKERS[b]||'확인이 필요한 입력').join(' '));
  }
  function taskCard(row){
    const card=node('div',{class:'video-task-row','data-video-task':row.task_id});
    card.append(node('p',{},`작업 ${row.task_id} · ${STATES[row.state]}`));
    if(row.reason_code!==null)card.append(node('p',{class:'sub'},Object.hasOwn(REASONS,row.reason_code)?REASONS[row.reason_code]:'자세한 사유는 표시하지 않습니다.'));
    const facts=[`입력 원고 버전 ${row.input_revision}`,`계획 버전 ${row.plan_revision}`];
    if(row.output_revision!==null)facts.push(`결과 원고 버전 ${row.output_revision}`);
    if(row.asset_id!==null)facts.push(`자산 ${row.asset_id}`);
    facts.push('검토 전');
    card.append(node('p',{class:'sub'},facts.join(' · ')));
    if(row.state==='preparing'||row.state==='rendering'||row.state==='unknown')card.append(node('p',{class:'sub'},'이 작업은 앱이 자동으로 다시 시작할 수 없습니다. 위 "영상 작업 다시 조회"로 상태만 확인하세요. 확인하기 전 다시 제작을 요청하지 마세요.'));
    if(row.state==='queued')card.append(node('p',{class:'sub'},'대기열에 등록된 작업입니다. 같은 원고에서 새 제작 요청은 이 작업이 끝날 때까지 막습니다.'));
    if(row.state==='awaiting_review'){
      card.append(node('p',{class:'sub'},'영상 파일은 만들어졌지만 등록 전입니다. 사람이 영상을 직접 보고 기록해야 등록됩니다.'));
      const open=node('button',{type:'button',class:'btn btn-small','data-video-action':'review-open','data-video-review-open':row.task_id,disabled:pending!==null||!ctx||isDirty()},pending==='review_loading'?'조회 중…':'영상 검토 열기');
      open.addEventListener('click',()=>openReview(row.task_id));card.append(open);
    }
    if(row.state==='rendered'){
      const resume=node('button',{type:'button',class:'btn btn-small','data-video-action':'resume','data-video-resume':row.task_id,disabled:!canMutate()},'결과 등록 재개');
      resume.addEventListener('click',()=>resumeTask(row.task_id));card.append(resume);
    }
    return card;
  }
  // 입력 중에는 다시 그리지 않고 제출 버튼 상태와 부모 변경 표시만 갱신한다. 그래야 포커스·커서가 유지된다.
  const sync=()=>{
    if(submitBtn)submitBtn.disabled=!canSubmit();
    root.querySelectorAll('[data-video-review-open]').forEach(button=>button.disabled=pending!==null||!ctx||isDirty());
    onChange();
  };
  function reviewSection(){
    const r=review,m=r.info.media,mf=r.info.manifest;
    const locked=!writable||pending!==null;
    const sec=node('div',{class:'video-review','data-video-review':r.id});
    sec.append(node('h4',{},`영상 검토 · 작업 ${r.id}`));
    sec.append(node('video',{controls:'controls',preload:'none',src:previewUrl(r.id),'data-video-field':'player'}));
    sec.append(node('p',{class:'sub','data-video-info':'review-media'},`영상 규격 ${m.width}×${m.height} · ${m.seconds}초 · 음성 있음 · 파일 ${m.filename} (${m.media_type}) · ${m.size}바이트 · 해시 ${m.sha256.slice(0,12)}`));
    sec.append(node('p',{class:'sub','data-video-info':'review-manifest'},`시험 ${mf.exam} · 분야 ${mf.field} · 출처 ${mf.source} · 하단 ${mf.footer}`));
    sec.append(node('p',{class:'sub','data-video-info':'review-disclosure'},`고지 ${mf.disclosure}`));
    const list=node('ul',{'data-video-info':'review-scenes'});
    mf.scenes.forEach(s=>list.append(node('li',{},`장면 ${s.index} · ${KINDS[s.kind]} · ${s.seconds}초 · 제목 ${s.title} · 자막 ${s.caption}`)));
    sec.append(list);
    sec.append(node('p',{class:'sub','data-video-info':'review-note'},'사람이 확인한 수동 기록입니다. 독립 AI 검사나 최종 콘텐츠 검토 완료를 뜻하지 않습니다.'));
    if(!tasks.some(t=>t.task_id===r.id&&t.state==='awaiting_review'))sec.append(node('p',{class:'sub','data-video-info':'review-closed'},'이 작업은 더 이상 검토 대기 상태가 아니라 저장할 수 없습니다. 입력 버리기로 닫으세요.'));
    for(const [key,label] of CHECKS){
      const box=node('input',{type:'checkbox','data-video-field':'check:'+key,'aria-label':label,disabled:locked});box.checked=r.checks[key]===true;
      const onBox=()=>{if(!writable||pending!==null||review!==r)return;r.checks[key]=box.checked===true;sync();};
      box.addEventListener('change',onBox);box.addEventListener('input',onBox);fields['check:'+key]=box;
      const l=node('label');l.append(box,document.createTextNode(' '+label));sec.append(l);
    }
    const select=node('select',{'data-video-field':'decision','aria-label':'검토 결정',disabled:locked});
    DECISIONS.forEach(([value,label])=>select.append(node('option',{value},label)));select.value=r.decision;
    const onSelect=()=>{if(!writable||pending!==null||review!==r||!DECISIONS.some(([v])=>v===select.value))return;r.decision=select.value;sync();};
    select.addEventListener('change',onSelect);select.addEventListener('input',onSelect);fields.decision=select;
    const dl=node('label');dl.append(document.createTextNode('결정 '),select);sec.append(dl);
    const notes=node('textarea',{maxlength:MAX_NOTES,'data-video-field':'notes','aria-label':'검토 메모',disabled:locked});notes.value=r.notes;
    notes.addEventListener('input',()=>{
      if(!writable||pending!==null||review!==r)return;
      if(notes.value.length>MAX_NOTES)notes.value=notes.value.slice(0,MAX_NOTES);
      r.notes=notes.value;sync();
    });fields.notes=notes;
    const nl=node('label');nl.append(document.createTextNode(`메모 (최대 ${MAX_NOTES}자 · 수정 요청에는 필수) `),notes);sec.append(nl);
    submitBtn=node('button',{type:'button',class:'btn btn-small','data-video-action':'review-submit',disabled:!canSubmit()},pending==='reviewing'?'저장 중…':'검토 저장·영상 등록');
    submitBtn.addEventListener('click',submitReview);sec.append(submitBtn);
    const discard=node('button',{type:'button',class:'btn btn-small','data-video-action':'review-discard',disabled:pending!==null},'검토 입력 버리기');
    discard.addEventListener('click',()=>{
      if(!review||pending!==null)return;
      if(isDirty()&&typeof globalThis.confirm==='function'&&!globalThis.confirm('체크·결정·메모 등 저장하지 않은 검토 입력을 버릴까요? 만들어진 영상 파일과 작업은 그대로 보존됩니다.'))return;
      review=null;message='검토 입력을 버렸습니다. 저장된 영상 작업과 파일은 보존됩니다.';paint();onChange();
    });sec.append(discard);
    return sec;
  }
  function paint(){
    const active=document.activeElement;
    const focusKey=active&&root.contains(active)&&active.getAttribute?active.getAttribute('data-video-field'):null;
    const range=focusKey&&typeof active.selectionStart==='number'?[active.selectionStart,active.selectionEnd]:null;
    fields={};submitBtn=null;
    const summary=node('summary',{},'영상 제작');const body=node('div',{class:'panel-body'});
    body.append(node('p',{},'영상 규격: 1080×1920 · 20초 이하 · 등록된 WAV 음성과 등록 이미지가 필요합니다. 입력이 준비되었다는 것은 품질 검토를 마쳤다는 뜻이 아닙니다.'));
    body.append(node('p',{class:'sub'},'제작 요청은 대기열 등록일 뿐 즉시 렌더링이 끝났다는 뜻이 아닙니다. 요청과 결과 확인은 버튼을 눌렀을 때만 한 번 보내며 자동 재시도나 반복 조회는 없습니다. 게시는 하지 않습니다.'));
    if(ctx){
      body.append(node('p',{'data-video-info':'content'},`원고 ${ctx.title||ctx.id} · 원고 버전 ${ctx.revision} · 소유 계정 ${ACCOUNTS[ctx.owner_account_id]||'계정 미확인'}`));
      body.append(node('p',{class:'sub'},`원고 해시 ${ctx.manifest_hash.slice(0,12)}`));
      body.append(node('p',{'data-video-info':'capability'},capText()));
      body.append(node('p',{'data-video-info':'plan'},planText()));
      if(!writable)body.append(node('p',{class:'sub','data-video-info':'readonly'},'원고 또는 제작 계획에 저장하지 않은 변경이 있거나 읽기 전용이라 제작 요청과 결과 등록 재개를 막았습니다. 제작 계획을 저장한 뒤 이 패널의 "영상 작업 다시 조회"로 저장된 계획 버전을 읽으세요.'));
      else body.append(node('p',{class:'sub'},'제작 계획을 저장했다면 "영상 작업 다시 조회"로 저장된 계획 버전을 읽은 뒤 요청하세요.'));
      if(uncertain)body.append(node('p',{class:'sub','data-video-info':'uncertain'},'이전 요청의 접수 결과가 불명확합니다. 작업 목록을 다시 조회해 확인할 때까지 제작 요청을 막았습니다.'));
      const enqueue=node('button',{type:'button',class:'btn btn-small','data-video-action':'enqueue',disabled:!canEnqueue()},pending==='creating'?'요청 중…':'영상 제작 요청');
      enqueue.addEventListener('click',enqueueTask);body.append(enqueue);
      body.append(node('h4',{},'영상 작업'));
      if(!tasks.length)body.append(node('p',{class:'sub'},'조회된 영상 작업이 없습니다.'));
      tasks.forEach(t=>body.append(taskCard(t)));
      if(review)body.append(reviewSection());
    }else body.append(node('p',{},'원고를 열면 저장된 영상 작업을 조회합니다.'));
    const reload=node('button',{type:'button',class:'btn btn-small','data-video-action':'reload',disabled:pending!==null||!ctx},'영상 작업 다시 조회');
    reload.addEventListener('click',reloadAll);
    body.append(reload,node('p',{role:'status'},message));
    root.replaceChildren(summary,body);
    const target=focusKey?fields[focusKey]:null;
    if(target){target.focus();if(range&&typeof target.setSelectionRange==='function')target.setSelectionRange(range[0],range[1]);}
  }
  async function reloadAll(){
    if(!ctx||pending!==null)return;
    const token=++generation,mine=ctx;pending='loading';message='영상 작업 조회 중';paint();onChange();
    try{await loadAll(mine,token);}
    finally{if(token===generation){pending=null;paint();onChange();flush();}}
  }
  async function enqueueTask(){
    if(!canEnqueue())return;
    const token=++generation,mine=ctx,planRevision=plan.plan_revision;
    pending='creating';message='제작 요청 전송 중 · 결과가 나올 때까지 다시 누르지 마세요';paint();onChange();
    try{
      const data=await send('/api/v2/contents/'+encodeURIComponent(mine.id)+'/video-tasks','POST',{expected_revision:mine.revision,expected_plan_revision:planRevision});
      if(token!==generation)return;
      if(!validRow(data,mine)||data.plan_revision!==planRevision)throw invalid();
      upsert(pick(data));message='제작 요청을 대기열에 등록했습니다. 렌더링이 끝났다는 뜻이 아닙니다. 상태는 "영상 작업 다시 조회"로 확인하세요. 검토 전입니다.';
    }catch(e){if(token===generation){message=writeMessage(e);if(!definite(e))uncertain=true;}}
    finally{if(token===generation){pending=null;paint();onChange();flush();}}
  }
  async function resumeTask(id){
    if(!canMutate())return;
    const target=tasks.find(t=>t.task_id===id);
    if(!target||target.state!=='rendered')return;
    const token=++generation,mine=ctx;
    pending='resuming';message='결과 등록 재개 요청 전송 중';paint();onChange();
    try{
      const data=await send('/api/v2/video-tasks/'+encodeURIComponent(id)+'/resume','POST',{});
      if(token!==generation)return;
      if(!validRow(data,mine)||data.task_id!==id)throw invalid();
      upsert(pick(data));message='결과 등록을 이어서 확인했습니다. 검토 전입니다.';
    }catch(e){if(token===generation){message=e.kind==='http'&&e.status===401?'로그인 후 다시 시도하세요. 요청은 접수되지 않았습니다.':'결과 등록 확인 결과를 알 수 없습니다. 영상 작업을 다시 조회해 확인하세요. 자동으로 다시 요청하지 않습니다.';if(!definite(e))stale=true;}}
    finally{if(token===generation){pending=null;paint();onChange();flush();}}
  }
  // 검토 열기는 GET 한 번뿐이다. 입력이 남은 초안이 있으면 덮어쓰지 않고 거부한다.
  async function openReview(id){
    if(!ctx||pending!==null||isDirty())return;
    const target=tasks.find(t=>t.task_id===id);
    if(!target||target.state!=='awaiting_review')return;
    const token=++generation;
    pending='review_loading';message='영상 검토 정보 조회 중';paint();onChange();
    try{
      const data=await send('/api/v2/video-tasks/'+encodeURIComponent(id)+'/review','GET');
      if(token!==generation)return;
      if(!validReview(data,target))throw invalid();
      review={id,fingerprint:data.context_fingerprint,plan_revision:target.plan_revision,info:{media:{...data.media},manifest:{...data.manifest,scenes:data.manifest.scenes.map(s=>({...s}))}},checks:Object.fromEntries(CHECK_KEYS.map(k=>[k,false])),decision:'pass',notes:''};
      message='영상 검토 정보를 조회했습니다. 영상을 직접 확인한 뒤 기록하세요.';
    }catch(e){if(token===generation)message=reviewReadMessage(e);}
    finally{if(token===generation){pending=null;paint();onChange();flush();}}
  }
  async function submitReview(){
    if(!canSubmit())return;
    const token=++generation,mine=ctx,r=review;
    const body={context_fingerprint:r.fingerprint,decision:r.decision,checks:Object.fromEntries(CHECK_KEYS.map(k=>[k,r.checks[k]===true])),notes:r.notes};
    const accepted=r.decision==='pass'?['completed','rendered']:['blocked'];
    pending='reviewing';message='검토 기록 전송 중 · 결과가 나올 때까지 다시 누르지 마세요';paint();onChange();
    try{
      const data=await send('/api/v2/video-tasks/'+encodeURIComponent(r.id)+'/review','POST',body);
      if(token!==generation)return;
      if(!validRow(data,mine)||data.task_id!==r.id||data.plan_revision!==r.plan_revision||!accepted.includes(data.state))throw invalid();
      if(review===r)review=null;
      upsert(pick(data));
      message=r.decision==='pass'?(data.state==='completed'?'사람이 확인한 기록을 저장하고 영상을 등록했습니다.':'사람이 확인한 기록을 저장했습니다. 등록 확인이 남았으니 "결과 등록 재개"로 확인하세요.')+' 독립 AI 검사나 최종 콘텐츠 검토 완료를 뜻하지 않습니다.':'수정 요청으로 기록했습니다. 영상은 등록하지 않았습니다.';
    }catch(e){
      if(token===generation){
        message=reviewWriteMessage(e);
        if(e.kind==='http'&&[404,409].includes(e.status))stale=true;
        else if(!definite(e))uncertain=true;
      }
    }
    finally{if(token===generation){pending=null;paint();onChange();flush();}}
  }
  paint();
  return {
    element:root,isDirty,isBusy:()=>pending!==null,
    discardChanges(){review=null;paint();onChange();},
    refreshControls(options={}){
      if(!options||options.writable===undefined)return;
      const next=options.writable===true;
      if(next===writable)return;
      writable=next;paint();
    },
    open(content,{writable:w=true}={}){
      generation++;pending=null;caps=null;plan=null;tasks=[];seen=new Set();queue=[];message='';stale=true;uncertain=false;review=null;writable=w===true;
      const ok=content&&typeof content.id==='string'&&content.id&&Number.isInteger(content.revision)&&content.revision>=1&&typeof content.manifest_hash==='string'&&typeof content.owner_account_id==='string'&&content.owner_account_id;
      if(!ok){ctx=null;if(content)message='원고 정보를 확인할 수 없어 영상 작업을 조회하지 않았습니다.';paint();onChange();return Promise.resolve();}
      ctx={id:content.id,revision:content.revision,manifest_hash:content.manifest_hash,owner_account_id:content.owner_account_id,title:String(content.title??'')};
      const mine=ctx,token=generation;pending='loading';message='조회 중';paint();onChange();
      return (async()=>{
        try{await loadAll(mine,token);}
        finally{if(token===generation){pending=null;paint();onChange();flush();}}
      })();
    }
  };
}
