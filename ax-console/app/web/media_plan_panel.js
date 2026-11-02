// 숏츠 제작 계획 입력. 저장은 계획 초안 보존일 뿐 렌더러·Voicebox 실행이나 검토가 아니다.
const IMAGE_TYPES=['image/png','image/jpeg','image/webp'],WAV_TYPES=['audio/wav'];
const KINDS=[['diorama','디오라마'],['diagram','도식']];
const ROW_KEYS=['content_id','content_revision','manifest_hash','owner_account_id','plan_revision','plan','inputs_ready','blockers','execution_enabled','review_status'];
const PLAN_KEYS=['exam','field','source','footer','disclosure','voice_asset_id','scenes'];
const SCENE_KEYS=['asset_id','kind','seconds','title','caption'];
const BLOCKERS={voice_required:'WAV 음성이 필요합니다.',diorama_required:'디오라마 장면이 2~3장이어야 합니다.',distinct_diorama_required:'디오라마에 서로 다른 이미지가 2장 이상 필요합니다.',scenes_required:'장면이 하나 이상 필요합니다.'};
const MAX_SECONDS=20,MAX_SCENES=30;
const exactKeys=(o,keys)=>!!o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).length===keys.length&&keys.every(k=>Object.hasOwn(o,k));
const validScene=s=>exactKeys(s,SCENE_KEYS)&&typeof s.asset_id==='string'&&KINDS.some(([k])=>k===s.kind)&&typeof s.seconds==='number'&&Number.isFinite(s.seconds)&&s.seconds>0&&typeof s.title==='string'&&typeof s.caption==='string';
const validPlan=p=>exactKeys(p,PLAN_KEYS)&&['exam','field','source','footer','disclosure'].every(k=>typeof p[k]==='string')&&(p.voice_asset_id===null||typeof p.voice_asset_id==='string')&&Array.isArray(p.scenes)&&p.scenes.every(validScene);
const validRow=(row,c)=>exactKeys(row,ROW_KEYS)&&row.content_id===c.id&&row.content_revision===c.revision&&row.manifest_hash===c.manifest_hash&&row.owner_account_id===c.owner_account_id&&Number.isInteger(row.plan_revision)&&row.plan_revision>=0&&validPlan(row.plan)&&typeof row.inputs_ready==='boolean'&&Array.isArray(row.blockers)&&row.blockers.every(b=>typeof b==='string')&&row.execution_enabled===false&&row.review_status==='not_checked';

export function createMediaPlanPanel({document,fetcher=globalThis.fetch,onChange=()=>{}}={}) {
  const root=document.createElement('details');root.className='panel media-plan';
  let ctx=null,writable=true,baseline=null,draft=null,planRevision=0,saved=null,busy=false,message='',generation=0,totalNode=null;
  const copy=value=>JSON.parse(JSON.stringify(value));
  const dirty=()=>!!draft&&JSON.stringify(draft)!==JSON.stringify(baseline);
  const editable=()=>writable&&!busy&&!!draft;
  const node=(tag,attrs={},text)=>{const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='disabled')n.disabled=v;else n.setAttribute(k,String(v));}if(text!==undefined)n.textContent=text;return n;};
  const assetsOf=types=>(ctx?.assets||[]).filter(a=>types.includes(a.media_type));
  const total=()=>draft.scenes.reduce((sum,s)=>sum+(Number.isFinite(s.seconds)?s.seconds:0),0);
  const totalText=()=>`장면 합계 ${Math.round(total()*1000)/1000}초 / 최대 ${MAX_SECONDS}초`;
  const changed=()=>{if(totalNode)totalNode.textContent=totalText();onChange();};
  async function request(mine,method,body){
    const url='/api/v2/contents/'+encodeURIComponent(mine.id)+'/media-plan?revision='+mine.revision;
    let response;
    try{response=await fetcher(url,{method,credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});}
    catch{throw new Error('제작 계획 서버에 연결하지 못했습니다. 입력은 유지됩니다.');}
    if(!response.ok)throw Object.assign(new Error(response.status===409?'다른 창에서 제작 계획이 바뀌었습니다. 입력을 보존했습니다. 저장된 계획을 다시 조회해 비교하세요.':response.status===401?'로그인 후 다시 시도하세요. 입력은 유지됩니다.':'제작 계획을 처리하지 못했습니다. 입력은 유지됩니다.'),{status:response.status});
    let row=null;try{row=await response.json();}catch{row=null;}
    if(!validRow(row,mine))throw new Error('제작 계획 응답의 원고 버전·소유 계정·형식을 확인할 수 없습니다. 입력은 유지됩니다.');
    return row;
  }
  function apply(row){baseline=copy(row.plan);draft=copy(row.plan);planRevision=row.plan_revision;saved={ready:row.inputs_ready,blockers:[...row.blockers]};}
  function textField(label,get,set,{area=false,max=2000}={}){
    const input=node(area?'textarea':'input',{...(area?{}:{type:'text'}),maxlength:max,disabled:!editable()});input.value=get();
    input.addEventListener('input',()=>{if(!editable())return;set(input.value);changed();});
    const l=node('label');l.append(document.createTextNode(label+' '),input);return l;
  }
  function selectField(label,options,value,set,{disabled=!editable()}={}){
    const list=options.some(([v])=>v===value)?options:[[value,'원고에 없는 자산 · 다시 선택하세요'],...options];
    const select=node('select',{disabled});
    for(const [v,text] of list)select.append(node('option',{value:v},text));
    select.value=value;
    select.addEventListener('change',()=>{if(!editable())return;set(select.value);changed();});
    const l=node('label');l.append(document.createTextNode(label+' '),select);return l;
  }
  function sceneCard(scene,index,images){
    const card=node('div',{class:'media-plan-scene','data-media-plan-scene':index});
    card.append(node('h4',{},`장면 ${index+1}`));
    card.append(selectField('이미지',images.map(a=>[a.id,a.filename||'등록 이미지']),scene.asset_id,v=>{scene.asset_id=v;}));
    card.append(selectField('종류',KINDS,scene.kind,v=>{scene.kind=v;}));
    const sec=node('input',{type:'number',min:0.5,step:0.5,'aria-label':`장면 ${index+1} 길이(초)`,'data-media-plan-field':'seconds',disabled:!editable()});sec.value=String(scene.seconds);
    sec.addEventListener('input',()=>{if(!editable())return;scene.seconds=sec.value===''?NaN:Number(sec.value);changed();});
    const sl=node('label');sl.append(document.createTextNode('길이(초) '),sec);card.append(sl);
    card.append(textField('제목',()=>scene.title,v=>{scene.title=v;},{max:300}));
    card.append(textField('자막',()=>scene.caption,v=>{scene.caption=v;},{area:true,max:1000}));
    const remove=node('button',{type:'button',class:'btn btn-small','data-media-plan-action':'remove-scene',disabled:!editable()},'장면 삭제');
    remove.addEventListener('click',()=>{if(!editable())return;draft.scenes.splice(index,1);paint();onChange();});card.append(remove);
    return card;
  }
  function paint(){
    totalNode=null;
    const summary=node('summary',{},'숏츠 제작 계획');const body=node('div',{class:'panel-body'});
    body.append(node('p',{},'저장은 제작 계획 초안만 보존합니다. 렌더러와 Voicebox 실행은 아직 연결되지 않았고, 검토나 게시도 하지 않습니다.'));
    body.append(node('p',{class:'sub'},'규칙: 장면 합계 최대 20초 · 디오라마 장면 2~3장에 서로 다른 이미지 · 등록된 WAV 음성 1개가 필요합니다.'));
    if(ctx){
      body.append(node('p',{'data-media-plan-info':'content'},`원고 버전 ${ctx.revision} · 소유 계정 ${ctx.owner_account_id} · ${ctx.title}`));
      body.append(node('p',{class:'sub'},`원고 해시 ${ctx.manifest_hash.slice(0,12)}`));
    }else body.append(node('p',{},'원고를 열면 저장된 제작 계획을 조회합니다.'));
    if(draft){
      const images=assetsOf(IMAGE_TYPES),wavs=assetsOf(WAV_TYPES);
      if(!writable)body.append(node('p',{class:'sub'},'읽기 전용 상태라 저장할 수 없습니다.'));
      if(!images.length)body.append(node('p',{class:'sub'},'등록된 이미지(PNG·JPEG·WebP)가 없습니다. 원고 자산에서 먼저 등록하세요.'));
      if(!wavs.length)body.append(node('p',{class:'sub'},'등록된 WAV 음성이 없습니다. 음성은 WAV 파일만 선택할 수 있습니다.'));
      body.append(textField('시험',()=>draft.exam,v=>{draft.exam=v;}),textField('분야',()=>draft.field,v=>{draft.field=v;}),textField('출처',()=>draft.source,v=>{draft.source=v;}),textField('하단 문구',()=>draft.footer,v=>{draft.footer=v;}),textField('고지 문구',()=>draft.disclosure,v=>{draft.disclosure=v;}));
      body.append(selectField('음성(WAV)',[['','음성 선택 안 함'],...wavs.map(a=>[a.id,a.filename||'등록 음성'])],draft.voice_asset_id??'',v=>{draft.voice_asset_id=v||null;}));
      draft.scenes.forEach((scene,i)=>body.append(sceneCard(scene,i,images)));
      totalNode=node('p',{'data-media-plan-info':'total'},totalText());body.append(totalNode);
      const add=node('button',{type:'button',class:'btn btn-small','data-media-plan-action':'add-scene',disabled:!editable()||!images.length||draft.scenes.length>=MAX_SCENES},'장면 추가');
      add.addEventListener('click',()=>{if(!editable()||!images.length||draft.scenes.length>=MAX_SCENES)return;draft.scenes.push({asset_id:images[0].id,kind:'diorama',seconds:3,title:'',caption:''});paint();onChange();});body.append(add);
      const save=node('button',{type:'button',class:'btn btn-small','data-media-plan-action':'save',disabled:!editable()},busy?'처리 중…':'제작 계획 저장');save.addEventListener('click',saveDraft);body.append(save);
      if(saved){
        body.append(node('p',{'data-media-plan-info':'readiness'},saved.ready?'저장된 계획은 입력 조건을 모두 채웠습니다. 다만 실행 연결 전이며 검토 상태는 확인되지 않았습니다.':'저장된 계획에서 부족한 입력: '+saved.blockers.map(b=>BLOCKERS[b]||b).join(' ')));
        if(dirty())body.append(node('p',{class:'sub'},'미저장 변경은 위 판정에 반영되지 않았습니다.'));
      }
    }
    const reload=node('button',{type:'button',class:'btn btn-small','data-media-plan-action':'reload',disabled:busy||!ctx},'저장된 계획 다시 조회');
    reload.addEventListener('click',()=>{if(!ctx||busy)return;if(!dirty()||globalThis.confirm('미저장 제작 계획을 버리고 다시 조회할까요?'))load();});
    body.append(reload,node('p',{role:'status'},message));
    root.replaceChildren(summary,body);
  }
  async function load(){
    if(!ctx)return;const token=++generation,mine=ctx;busy=true;message='조회 중';paint();onChange();
    try{const row=await request(mine,'GET');if(token!==generation)return;apply(row);message='저장된 제작 계획 · 실행·검토와 별개';}
    catch(e){if(token===generation)message=e.message;}
    finally{if(token===generation){busy=false;paint();onChange();}}
  }
  function localProblem(){
    if(draft.scenes.length>MAX_SCENES)return `장면은 ${MAX_SCENES}개 이하여야 합니다.`;
    if(draft.scenes.some(s=>!Number.isFinite(s.seconds)||s.seconds<=0))return '모든 장면 길이는 0보다 큰 숫자여야 합니다.';
    if(total()>MAX_SECONDS+1e-9)return `장면 합계는 ${MAX_SECONDS}초 이하여야 합니다.`;
    return '';
  }
  async function saveDraft(){
    if(!writable||busy||!draft||!ctx)return;
    const problem=localProblem();if(problem){message=problem;paint();return;}
    const token=++generation,mine=ctx,body={expected_revision:planRevision,plan:copy(draft)};busy=true;message='저장 중';paint();onChange();
    try{const row=await request(mine,'POST',body);if(token!==generation)return;apply(row);message='제작 계획을 저장했습니다. 렌더러·Voicebox 실행과 검토는 하지 않았습니다.';}
    catch(e){if(token===generation)message=e.message;}
    finally{if(token===generation){busy=false;paint();onChange();}}
  }
  paint();
  return {
    element:root,isDirty:dirty,isBusy:()=>busy,
    discardChanges(){if(baseline)draft=copy(baseline);paint();},
    refreshControls(options={}){if(options&&options.writable!==undefined)writable=options.writable===true;paint();},
    open(content,{writable:w=true}={}){
      generation++;busy=false;baseline=draft=saved=null;planRevision=0;message='';writable=w===true;
      const ok=content&&typeof content.id==='string'&&content.id&&Number.isInteger(content.revision)&&content.revision>=0&&typeof content.manifest_hash==='string'&&typeof content.owner_account_id==='string'&&content.owner_account_id;
      if(!ok){ctx=null;if(content)message='원고 정보를 확인할 수 없어 제작 계획을 조회하지 않았습니다.';paint();onChange();return Promise.resolve();}
      ctx={id:content.id,revision:content.revision,manifest_hash:content.manifest_hash,owner_account_id:content.owner_account_id,title:String(content.title??''),series:String(content.series??''),assets:(Array.isArray(content.assets)?content.assets:[]).map(a=>({id:a?.id,filename:a?.filename,media_type:a?.media_type})).filter(a=>typeof a.id==='string')};
      return load();
    }
  };
}
