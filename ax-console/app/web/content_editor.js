import {createImageTaskPanel} from './image_task_panel.js';
import {createReuseApprovalPanel} from './reuse_approval_panel.js';
import {createVideoTaskPanel} from './video_task_panel.js';
import {createVoiceTaskPanel} from './voice_task_panel.js';
import {createMediaPlanPanel} from './media_plan_panel.js';
import {createToolkitApi} from './toolkit_api.js';
import {createToolkitController} from './toolkit_controller.js';
import {createToolkitPanel} from './toolkit_panel.js';
import {createDeliveryEditor} from './delivery_editor.js';
import {accountLabel,kindLabel,statusLabel,formatDateTime,safeUrl} from './view_helpers.js';
const fields=['title','kind','series','status','original','variants','sources'];
const clone=value=>JSON.parse(JSON.stringify(value));
export const emptyDraft=()=>({owner_account_id:'',title:'',kind:'article',series:'',status:'idea',original:'',variants:[],sources:[]});
export function draftFromContent(content) {return {...emptyDraft(),...Object.fromEntries(['owner_account_id',...fields].filter(key=>content[key]!==undefined).map(key=>[key,clone(content[key])]))};}
export function toContentPayload(draft,content=null) {
  if(!content&&!['personal','dept'].includes(draft.owner_account_id))throw new Error('원본 소유 계정을 직접 선택해 주세요.');
  if(!draft.title.trim())throw new Error('제목을 입력해 주세요.');
  const payload=Object.fromEntries(fields.map(key=>[key,clone(draft[key])]));
  if(content)payload.expected_revision=content.revision;else payload.owner_account_id=draft.owner_account_id;
  return payload;
}
export const copyLegacySummary=content=>({...emptyDraft(),title:content.title||'',kind:['article','card','short','video'].includes(content.kind)?content.kind:'article',series:content.series||'',original:content.summary||''});
export const reviewPayload=(content,kind,decision,notes)=>({revision:content.revision,manifest_hash:content.manifest_hash,kind,decision,notes});
export const reviewLabel=review=>`버전 ${review.revision} · 사람 수동 기록 · ${review.decision==='pass'?'통과 기록':'수정 요청'} · ${review.kind}`;
export function createEditSession(content=null) {
  const session={content,draft:content?draftFromContent(content):emptyDraft(),phase:'idle',error:'',baseline:null,
    dirty(){return JSON.stringify(this.draft)!==this.baseline;},
    async save(write){
      this.phase='saving';this.error='';
      try {const next=await write(toContentPayload(this.draft,this.content));this.content=next;this.draft=draftFromContent(next);this.baseline=JSON.stringify(this.draft);this.phase='saved';return next;}
      catch(error){this.phase=error.status===409?'conflict':error.status===401?'unauthorized':'error';this.error=error.message;return null;}
    }};
  session.baseline=JSON.stringify(session.draft);return session;
}
const platforms=['youtube','tiktok','instagram','threads','x','facebook','tistory','naver_blog','blogger','homepage','kakao'];
export function createContentEditor({api,onSaved=()=>{},writable=()=>false,execution=null}) {
  const root=document.createElement('div');root.className='content-editor';
  const validAccount=id=>id==='personal'||id==='dept';
  let scopedAccount='';
  let session=createEditSession(),historical=false,busy=false,loadFailed=false,generation=0,revisions=[],message='',reviewDraft={kind:'general',decision:'pass',notes:''};
  const el=(tag,attrs={},...children)=>{
    const node=document.createElement(tag);
    for(const [key,value] of Object.entries(attrs))if(key.startsWith('on'))node.addEventListener(key.slice(2),value);else if(key==='disabled')node.disabled=Boolean(value);else node.setAttribute(key,String(value));
    for(const child of children.flat(Infinity))if(child!=null)node.append(typeof child==='object'?child:document.createTextNode(String(child)));
    return node;
  };
  const button=(label,fn,disabled=false)=>el('button',{type:'button',class:'btn btn-small',disabled,onclick:fn},label);
  const canWrite=()=>writable()===true&&!historical&&!busy&&!loadFailed;
  const toolkitController=createToolkitController({api:createToolkitApi(),onChange:()=>updateRevisionControls()});
  const toolkit=createToolkitPanel({controller:toolkitController,document});
  function toolkitContext(){return {account:session.content?.owner_account_id||session.draft.owner_account_id||'all',
    contentId:session.content?.id,revision:session.content?.revision,
    inputHash:JSON.stringify(session.draft),editorDirty:session.dirty(),
    variants:clone(session.draft.variants),assets:clone(session.content?.assets||[]),deliveries:delivery.getItems(),
    connectionId:toolkitController.getState().inputs.connection_id||null};}
  function syncToolkit(){return toolkit.render({section:'editor',context:toolkitContext(),writable:canWrite()&&!childBlocksRevision()});}
  toolkit.element.addEventListener('toolkit-stage',event=>{
    const patch=event.detail,context=toolkitContext(),state=toolkitController.getState();
    if(!canWrite()||childBlocksRevision()||session.dirty()||context.inputHash!==state.context.inputHash)return;
    // 전달된 patch를 현재 preview의 clean hash·revision·connection으로 다시 결속한다.
    const candidates=state.reports.packaging?.candidates||[];
    const valid=candidates.some(candidate=>[undefined,...session.draft.variants.map((_,index)=>index)].some(variantIndex=>{
      try{return JSON.stringify(toolkitController.stageCandidate(candidate.id??candidate.candidate_id,{...context,variantIndex}))===JSON.stringify(patch);}catch{return false;}
    }));
    if(!valid)return;
    if(typeof patch.title==='string')session.draft.title=patch.title;
    if(patch.variant)session.draft.variants[patch.variant.index].text=patch.variant.text;
    message='후보를 미저장 초안에 반영했습니다. 원본 저장 시 새 버전과 독립 검토가 필요합니다.';
    render();
  });
  let imageKey='',imageWritable=null,deliveryKey='',mediaKey='',voiceKey='',videoKey='',reuseKey='',mediaWritable=null,voiceWritable=null,videoWritable=null,reuseWritable=null;
  const delivery=createDeliveryEditor({api,writable:()=>canWrite()&&!session.dirty(),onSaved,onStateChange:()=>updateRevisionControls()});
  const image=createImageTaskPanel({document,onChange:()=>updateRevisionControls(),onCompleted:row=>productionCompleted(row,'이미지')});
  const media=createMediaPlanPanel({document,onChange:()=>updateRevisionControls()});
  const voice=createVoiceTaskPanel({document,onChange:()=>updateRevisionControls(),onCompleted:voiceCompleted});
  const reuse=createReuseApprovalPanel({document,onChange:()=>updateRevisionControls()});
  const video=createVideoTaskPanel({document,onChange:()=>updateRevisionControls(),onCompleted:row=>productionCompleted(row,'영상')});
  function voiceCompleted(row){return productionCompleted(row,'음성');}
  async function productionCompleted(row,label){
    const current=session.content;
    if(!current||row.content_id!==current.id||row.input_revision!==current.revision||!Number.isInteger(row.output_revision)||row.output_revision<=current.revision)return;
    const token=generation;
    try{const history=await api.listRevisions(current.id);if(token!==generation||session.content!==current)return;revisions=history.items||[];historical=true;message=label==='이미지'?'이미지 자산이 새 버전에 등록되었습니다. 최신 버전을 열어 PNG를 확인하세요. 검토는 아직 하지 않았습니다.':label==='영상'?'영상 자산이 새 버전에 등록되었습니다. 최신 버전을 열어 MP4를 확인하세요. 검토는 아직 하지 않았습니다.':'음성 자산이 새 버전에 등록되었습니다. 최신 버전을 열어 WAV를 확인하세요. 검토는 아직 하지 않았습니다.';render();}
    catch{if(token===generation){message=label+' 등록이 끝났습니다. 최신 원고를 다시 조회해 자산을 확인하세요.';}}
  }
  const childBlocksRevision=()=>image.isBusy()||image.isDirty()||reuse.isBusy()||reuse.isDirty()||video.isBusy()||video.isDirty()||voice.isBusy()||voice.isDirty()||media.isBusy()||media.isDirty()||toolkit.isBusy()||delivery.hasUnsavedChanges()||delivery.isBusy()||!!execution?.isDirty()||!!execution?.isBusy();
  function updateRevisionControls(){
    const base=canWrite()&&!session.dirty()&&!delivery.isBusy()&&!delivery.hasUnsavedChanges()&&!execution?.isBusy()&&!execution?.isDirty()&&!toolkit.isBusy();
    const allowed=base&&!image.isBusy()&&!image.isDirty()&&!reuse.isBusy()&&!reuse.isDirty()&&!video.isBusy()&&!video.isDirty()&&!voice.isBusy()&&!voice.isDirty();
    if(allowed!==mediaWritable){mediaWritable=allowed;media.refreshControls({writable:allowed});}
    const voiceAllowed=base&&!image.isBusy()&&!image.isDirty()&&!reuse.isBusy()&&!reuse.isDirty()&&!video.isBusy()&&!video.isDirty()&&!media.isBusy()&&!media.isDirty();
    if(voiceAllowed!==voiceWritable){voiceWritable=voiceAllowed;voice.refreshControls({writable:voiceAllowed});}
    const videoAllowed=base&&!image.isBusy()&&!image.isDirty()&&!reuse.isBusy()&&!reuse.isDirty()&&!voice.isBusy()&&!voice.isDirty()&&!media.isBusy()&&!media.isDirty();
    if(videoAllowed!==videoWritable){videoWritable=videoAllowed;video.refreshControls({writable:videoAllowed});}
    const reuseAllowed=base&&!image.isBusy()&&!image.isDirty()&&!voice.isBusy()&&!voice.isDirty()&&!media.isBusy()&&!media.isDirty()&&!video.isBusy()&&!video.isDirty();
    if(reuseAllowed!==reuseWritable){reuseWritable=reuseAllowed;reuse.refreshControls({writable:reuseAllowed});}
    const imageAllowed=base&&!reuse.isBusy()&&!reuse.isDirty()&&!video.isBusy()&&!video.isDirty()&&!voice.isBusy()&&!voice.isDirty()&&!media.isBusy()&&!media.isDirty();
    if(imageAllowed!==imageWritable){imageWritable=imageAllowed;image.refreshControls({writable:imageAllowed});}
    const blocked=childBlocksRevision();
    toolkit.refreshControls({context:toolkitContext(),writable:canWrite()&&!blocked});
    root.querySelectorAll('[data-revision-write]').forEach(node=>node.disabled=!canWrite()||blocked||(node.getAttribute?.('type')==='file'&&session.dirty()));
    const select=root.querySelector('[data-parent-switch]');if(select)select.disabled=busy||blocked;
    const notice=root.querySelector('[data-child-block]');
    if(notice)notice.textContent=blocked?(image.isBusy()?'이미지 작업을 처리하는 중입니다.':image.isDirty()?'이미지 제작 입력이 남아 있습니다. 제작 또는 입력 버리기 후 원본을 변경하세요.':execution?.isBusy()?'실행 요청 처리 중입니다. 완료 후 원본 변경을 검토하세요.':execution?.isDirty()?'실행 요청·발행 확인 입력이 보존되어 있습니다. 처리 상태 조회와 명시적 검토 후 원본을 변경하세요.':reuse.isBusy()?'이미지 확인 기록을 조회·저장하는 중입니다.':reuse.isDirty()?'이미지 재사용 확인에 미저장 입력이 있습니다. 확인 기록 저장 또는 입력 버리기 후 원본을 변경하세요.':video.isBusy()?'영상 작업을 조회·접수하는 중입니다.':video.isDirty()?'영상 검토 입력이 남아 있습니다. 검토 저장 또는 입력 버리기 후 원본을 변경하세요.':voice.isBusy()?'음성 작업을 처리하는 중입니다.':voice.isDirty()?'음성 대본·복구 입력이 남아 있습니다. 처리 또는 입력 버리기 후 원본을 변경하세요.':media.isBusy()?'숏츠 제작 계획을 조회·저장하는 중입니다.':media.isDirty()?'숏츠 제작 계획에 미저장 입력이 있습니다. 계획 저장 또는 입력 버리기 후 원본을 변경하세요.':toolkit.isBusy()?'로컬 도구 처리 중입니다. 완료 후 원본 저장과 버전 전환을 검토하세요.':delivery.isBusy()?'배포 계획 처리 중입니다. 완료 후 원본을 저장할 수 있습니다.':'배포 계획에 미저장 입력이 있습니다. 계획 저장 또는 입력 버리기 후 원본을 저장하세요.') : '';
  }
  const hasChanges=()=>image.isDirty()||reuse.isDirty()||video.isDirty()||voice.isDirty()||media.isDirty()||toolkit.isDirty()||!!execution?.isDirty()||delivery.hasUnsavedChanges()||session.dirty()||Boolean(reviewDraft.notes)||reviewDraft.kind!=='general'||reviewDraft.decision!=='pass';
  function field(label,value,onChange,{type='input',options,maxLength,locked=false}={}) {
    const input=el(type,{...(maxLength?{maxlength:maxLength}:{}),disabled:locked||!canWrite(),oninput:e=>{onChange(e.target.value);updateNotice();}});
    if(options)for(const [id,text] of options)input.append(el('option',{value:id},text));
    input.value=value;return el('label',{class:'editor-field'},el('span',{},label),input);
  }
  function updateNotice(){toolkit.refreshControls({context:toolkitContext(),writable:canWrite()&&!childBlocksRevision()});if(session.content&&execution)execution.forContent(session.content,{dirty:session.dirty(),readOnly:!canWrite()});delivery.refreshControls();updateRevisionControls();const notice=root.querySelector('[data-dirty]');if(notice)notice.textContent=session.dirty()?'미저장 변경 있음':'';root.querySelectorAll('[data-needs-clean]').forEach(node=>node.disabled=!canWrite()||session.dirty()||childBlocksRevision());}
  function notice(){return el('p',{class:'editor-message',role:'status','aria-live':'polite'},session.error||message|| (session.phase==='saved'?'저장했습니다.':busy?'처리 중입니다.':''));}
  async function action(task) {
    if(image.isBusy()||reuse.isBusy()||video.isBusy()||voice.isBusy()||media.isBusy()||delivery.isBusy()||execution?.isBusy()||toolkit.isBusy())return;
    busy=true;message='';session.error='';render();
    try {await task();}catch(error){session.error=error.message;session.phase=error.status===401?'unauthorized':error.status===409?'conflict':'error';}
    finally {busy=false;render();}
  }
  async function refreshVersions(){if(session.content){const data=await api.listRevisions(session.content.id);revisions=data.items||[];}}
  function render() {
    const c=session.content,d=session.draft;
    const form=el('form',{onsubmit:async event=>{event.preventDefault();if(!canWrite()||childBlocksRevision())return;await action(async()=>{const saved=await session.save(payload=>c?api.updateContent(c.id,payload):api.createContent(payload));if(saved){await refreshVersions();onSaved(saved);}});}});
    form.append(el('p',{'data-child-block':'',role:'status'}),el('p',{class:'inline-note'},historical?'과거 버전 · 읽기 전용':c?'새 관리 원본 · 소유 계정 고정':scopedAccount?'새 관리 원본 · 현재 계정 소유로 시작합니다.':'새 관리 원본 · 소유 계정을 선택하세요.'),notice());
    if(session.phase==='unauthorized')form.append(el('a',{href:'/login',target:'_blank',rel:'noopener'},'다른 탭에서 로그인 후 다시 시도'));
    if(c){
      const select=el('select',{'aria-label':'원본 버전 선택','data-parent-switch':'',disabled:busy||childBlocksRevision(),onchange:async event=>{
        if(childBlocksRevision()){event.target.value=String(c.revision);return;}
        if(hasChanges()&&!globalThis.confirm('저장하지 않은 변경을 버리고 버전을 전환할까요?')){event.target.value=String(c.revision);return;}
        const revision=Number(event.target.value);await action(async()=>{const next=await api.getContent(c.id,revision);historical=revision!==Math.max(...revisions.map(r=>r.revision),c.revision);session=createEditSession(next);reviewDraft={kind:'general',decision:'pass',notes:''};});
      }});
      for(const rev of revisions)select.append(el('option',{value:rev.revision},`버전 ${rev.revision} · ${formatDateTime(rev.created_at)}`));select.value=String(c.revision);
      form.append(el('label',{class:'editor-field'},'저장 버전',select));
      if(historical)form.append(button('최신 버전 열기',()=>{if(childBlocksRevision())return;if(hasChanges()&&!globalThis.confirm('저장하지 않은 변경을 버리고 최신 버전을 열까요?'))return;return open({id:c.id,source:'managed'});},busy||childBlocksRevision()));
      form.append(el('p',{},`원본 소유: ${accountLabel(c.owner_account_id)} · 버전 ${c.revision}`));
    }else if(scopedAccount&&d.owner_account_id===scopedAccount){
      form.append(field(`원본 소유 계정 (현재 계정: ${accountLabel(scopedAccount)})`,d.owner_account_id,()=>{},{type:'select',options:[['personal','개인'],['dept','학과']],locked:true}),el('p',{class:'sub'},'이 계정 메뉴에서 만드는 새 원본은 현재 계정 소유로 고정됩니다. 다른 계정 소유로 만들려면 해당 계정 메뉴로 돌아가 새로 만드세요.'));
    }else form.append(field('원본 소유 계정 (필수)',d.owner_account_id,v=>d.owner_account_id=v,{type:'select',options:[['','직접 선택'],['personal','개인'],['dept','학과']]}));
    form.append(field('제목',d.title,v=>d.title=v,{maxLength:300}),el('div',{class:'editor-grid'},field('형식',d.kind,v=>d.kind=v,{type:'select',options:['article','card','short','video'].map(k=>[k,kindLabel(k)])}),field('상태',d.status,v=>d.status=v,{type:'select',options:['idea','drafting','production','review','archived'].map(k=>[k,statusLabel(k)])})),field('시리즈',d.series,v=>d.series=v),field('원문',d.original,v=>d.original=v,{type:'textarea',maxLength:200000}));
    const variants=el('section',{class:'editor-section'},el('h3',{},'대상별 변환본'),el('p',{class:'sub'},'목표 계정·채널은 기획 정보입니다. 예약이나 발행을 만들지 않습니다.'));
    d.variants.forEach((variant,i)=>variants.append(el('div',{class:'editor-row'},field('대상 계정',variant.destination_account_id,v=>variant.destination_account_id=v,{type:'select',options:[['personal','개인'],['dept','학과']]}),field('목표 채널',variant.platform,v=>variant.platform=v,{type:'select',options:platforms.map(p=>[p,p])}),field('변환 원고',variant.text,v=>variant.text=v,{type:'textarea',maxLength:200000}),button('변환본 삭제',()=>{d.variants.splice(i,1);render();},!canWrite()))));
    variants.append(button('변환본 추가',()=>{const owner=c?.owner_account_id||d.owner_account_id;d.variants.push({destination_account_id:validAccount(owner)?owner:'personal',platform:'youtube',text:''});render();},!canWrite()||d.variants.length>=30));form.append(variants);
    const sources=el('section',{class:'editor-section'},el('h3',{},'출처'));
    d.sources.forEach((source,i)=>sources.append(el('div',{class:'editor-row'},field('출처 주소 (http/https)',source.url,v=>source.url=v),field('출처 메모',source.note,v=>source.note=v,{type:'textarea',maxLength:2000}),safeUrl(source.url)?el('a',{href:safeUrl(source.url),target:'_blank',rel:'noopener noreferrer'},'출처 열기'):null,button('출처 삭제',()=>{d.sources.splice(i,1);render();},!canWrite()))));
    sources.append(button('출처 추가',()=>{d.sources.push({url:'',note:''});render();},!canWrite()||d.sources.length>=100));form.append(sources);
    form.append(el('div',{class:'editor-actions'},el('button',{type:'submit','data-revision-write':'',class:'btn btn-primary',disabled:!canWrite()||childBlocksRevision()},busy?'저장 중…':'원본 저장'),el('span',{'data-dirty':'',role:'status'},session.dirty()?'미저장 변경 있음':'')));
    if(c){
      const assets=el('section',{class:'editor-section'},el('h3',{},'이미지·영상·음성 자산'));
      for(const asset of c.assets||[]){const expected=`/api/v2/contents/${encodeURIComponent(c.id)}/revisions/${c.revision}/assets/${encodeURIComponent(asset.id)}`;assets.append(el('p',{},el('a',{href:expected,target:'_blank',rel:'noopener'},asset.filename),` · ${asset.media_type} · ${asset.size} bytes`));}
      const upload=el('input',{'data-needs-clean':'','data-revision-write':'',type:'file',accept:'.jpg,.jpeg,.png,.webp,.mp4,.mp3,.wav',disabled:!canWrite()||session.dirty(),onchange:async event=>{const file=event.target.files[0];if(!file||!canWrite()||session.dirty()||childBlocksRevision())return;await action(async()=>{const next=await api.uploadAsset(c.id,c.revision,file);session=createEditSession(next);await refreshVersions();onSaved(next);});}});
      assets.append(el('label',{class:'editor-field'},'자산 등록 (먼저 원본 변경을 저장하세요)',upload),el('p',{class:'sub'},'JPEG·PNG·WebP·MP4·MP3·WAV, 파일당 100MiB. 등록 시 새 버전을 만듭니다.'));form.append(assets);
      const reviews=el('section',{class:'editor-section'},el('h3',{},'사람의 수동 검토 기록'),el('p',{class:'sub'},'아래 기록은 독립 검산·출처 검토 도구를 실행한 결과가 아닙니다. 승인·예약·발행 상태를 바꾸지 않습니다.'));
      for(const review of c.reviews||[])reviews.append(el('article',{class:'editor-row'},el('strong',{},reviewLabel(review)),el('p',{},review.notes||'메모 없음'),el('p',{class:'sub'},`해시 ${review.manifest_hash} · ${formatDateTime(review.created_at)}`)));
      const rd=reviewDraft;
      const reviewSelect=(label,options,fn)=>{const select=el('select',{'data-needs-clean':'',disabled:!canWrite()||session.dirty(),onchange:e=>fn(e.target.value)},options.map(([value,text])=>el('option',{value},text)));select.value=label==='검토 종류'?rd.kind:rd.decision;return el('label',{class:'editor-field'},label,select);};
      const note=el('textarea',{'data-needs-clean':'',maxlength:10000,disabled:!canWrite()||session.dirty(),oninput:e=>rd.notes=e.target.value});
      note.value=rd.notes;
      reviews.append(reviewSelect('검토 종류',[['general','일반'],['calculation','계산'],['source','출처']],v=>rd.kind=v),reviewSelect('기록 결과',[['pass','통과 기록'],['changes_requested','수정 요청']],v=>rd.decision=v),el('label',{class:'editor-field'},`버전 ${c.revision} 수동 검토 메모`,note),button('이 버전의 수동 검토 기록 저장',()=>action(async()=>{await api.recordReview(c.id,reviewPayload(c,rd.kind,rd.decision,rd.notes));session=createEditSession(await api.getContent(c.id,c.revision));reviewDraft={kind:'general',decision:'pass',notes:''};message='이 버전에 수동 검토 기록을 저장했습니다.';}),!canWrite()||session.dirty()));form.append(reviews);
    }
    const reviewButton=[...form.querySelectorAll('button')].find(node=>node.textContent==='이 버전의 수동 검토 기록 저장');if(reviewButton)reviewButton.setAttribute('data-needs-clean','');
    root.replaceChildren(form);
    root.append(syncToolkit());
    if(c){root.append(image.element);const key=`${c.id}:${c.revision}:${c.manifest_hash}`;if(key!==imageKey){imageKey=key;image.open(c,{writable:canWrite()&&!session.dirty()});}}
    if(c){root.append(reuse.element);const key=`${c.id}:${c.revision}:${c.manifest_hash}`;if(key!==reuseKey){reuseKey=key;reuse.open(c,{writable:canWrite()&&!session.dirty()});}}
    if(c){root.append(voice.element);const key=`${c.id}:${c.revision}:${c.manifest_hash}`;if(key!==voiceKey){voiceKey=key;voice.open(c,{writable:canWrite()&&!session.dirty()});}}
    if(c){root.append(media.element);const key=`${c.id}:${c.revision}:${c.manifest_hash}`;if(key!==mediaKey){mediaKey=key;media.open(c,{writable:canWrite()&&!session.dirty()});}}
    if(c){root.append(video.element);const key=`${c.id}:${c.revision}:${c.manifest_hash}`;if(key!==videoKey){videoKey=key;video.open(c,{writable:canWrite()&&!session.dirty()});}}
    if(c&&!historical){root.append(delivery.element);const key=`${c.id}:${c.revision}:${c.manifest_hash}`;if(key!==deliveryKey){deliveryKey=key;delivery.open(c);}else delivery.refreshControls();}
    if(c&&execution)root.append(execution.forContent(c,{dirty:session.dirty(),readOnly:!canWrite()}));
    updateRevisionControls();
  }
  async function open(content=null,{accountId}={}) {
    const token=++generation;imageKey=deliveryKey=mediaKey=voiceKey=videoKey=reuseKey='';imageWritable=null;image.open(null);mediaWritable=voiceWritable=videoWritable=reuseWritable=null;reuse.open(null);video.open(null);voice.open(null);media.open(null);delivery.open(null);historical=false;loadFailed=false;reviewDraft={kind:'general',decision:'pass',notes:''};message='';revisions=[];
    scopedAccount=validAccount(accountId)?accountId:'';
    session=createEditSession();
    // 새 원본(관리 원본이 아닌 경우)에만 현재 계정 컨텍스트를 소유 계정 초기값으로 쓴다. baseline도 맞춰 dirty=false 유지.
    if(scopedAccount&&content?.source!=='managed'){session.draft.owner_account_id=scopedAccount;if(!content)session.baseline=JSON.stringify(session.draft);}
    busy=true;toolkitController.setContext(toolkitContext());render();
    try {
      if(content?.source==='managed'){scopedAccount='';const [full,history]=await Promise.all([api.getContent(content.id,content.revision),api.listRevisions(content.id)]);if(token!==generation)return;session=createEditSession(full);revisions=history.items||[];historical=full.revision<Math.max(full.revision,...revisions.map(item=>item.revision));}
      else if(content){
        // 원본은 바꾸지 않는다. 수집 요약만 새 복사본 초안으로 복사하며 baseline은 빈 초안이라 dirty=true.
        session.draft=copyLegacySummary(content);if(scopedAccount)session.draft.owner_account_id=scopedAccount;session.baseline=JSON.stringify(emptyDraft());
        message=scopedAccount?`기존 자료는 변경되지 않으며, 수집 요약만 새 복사본 초안으로 복사했습니다. 전체 원문은 제공되지 않았습니다. 새 복사본의 소유 계정은 현재 계정(${accountLabel(scopedAccount)})으로 설정되었습니다.`:'기존 자료의 수집 요약만 복사했습니다. 기존 자료는 변경되지 않는 복사본입니다. 전체 원문은 제공되지 않았습니다. 새 원본 소유 계정을 선택해 저장하세요.';
      }
    }catch(error){if(token===generation){loadFailed=true;session.error=error.message;session.phase=error.status===401?'unauthorized':'error';}}
    finally {if(token===generation){busy=false;render();}}
  }
  execution?.subscribe?.(()=>updateRevisionControls());
  return {element:root,open,hasUnsavedChanges:hasChanges,isBusy:()=>busy||image.isBusy()||reuse.isBusy()||video.isBusy()||voice.isBusy()||media.isBusy()||delivery.isBusy()||!!execution?.isBusy()||toolkit.isBusy()};
}
