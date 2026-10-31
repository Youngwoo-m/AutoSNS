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
  let session=createEditSession(),historical=false,busy=false,loadFailed=false,generation=0,revisions=[],message='',reviewDraft={kind:'general',decision:'pass',notes:''};
  const el=(tag,attrs={},...children)=>{
    const node=document.createElement(tag);
    for(const [key,value] of Object.entries(attrs))if(key.startsWith('on'))node.addEventListener(key.slice(2),value);else if(key==='disabled')node.disabled=Boolean(value);else node.setAttribute(key,String(value));
    for(const child of children.flat(Infinity))if(child!=null)node.append(typeof child==='object'?child:document.createTextNode(String(child)));
    return node;
  };
  const button=(label,fn,disabled=false)=>el('button',{type:'button',class:'btn btn-small',disabled,onclick:fn},label);
  const canWrite=()=>writable()===true&&!historical&&!busy&&!loadFailed;
  let deliveryKey='';
  const delivery=createDeliveryEditor({api,writable:()=>canWrite()&&!session.dirty(),onSaved,onStateChange:()=>updateRevisionControls()});
  const childBlocksRevision=()=>delivery.hasUnsavedChanges()||delivery.isBusy()||!!execution?.isDirty()||!!execution?.isBusy();
  function updateRevisionControls(){const blocked=childBlocksRevision();root.querySelectorAll('[data-revision-write]').forEach(node=>node.disabled=!canWrite()||blocked||(node.getAttribute?.('type')==='file'&&session.dirty()));const select=root.querySelector('[data-parent-switch]');if(select)select.disabled=busy||blocked;const notice=root.querySelector('[data-child-block]');if(notice)notice.textContent=blocked?(execution?.isBusy()?'실행 요청 처리 중입니다. 완료 후 원본 변경을 검토하세요.':execution?.isDirty()?'실행 요청·발행 확인 입력이 보존되어 있습니다. 처리 상태 조회와 명시적 검토 후 원본을 변경하세요.':delivery.isBusy()?'배포 계획 처리 중입니다. 완료 후 원본을 저장할 수 있습니다.':'배포 계획에 미저장 입력이 있습니다. 계획 저장 또는 입력 버리기 후 원본을 저장하세요.'):'';}
  const hasChanges=()=>!!execution?.isDirty()||delivery.hasUnsavedChanges()||session.dirty()||Boolean(reviewDraft.notes)||reviewDraft.kind!=='general'||reviewDraft.decision!=='pass';
  function field(label,value,onChange,{type='input',options,maxLength}={}) {
    const input=el(type,{...(maxLength?{maxlength:maxLength}:{}),disabled:!canWrite(),oninput:e=>{onChange(e.target.value);updateNotice();}});
    if(options)for(const [id,text] of options)input.append(el('option',{value:id},text));
    input.value=value;return el('label',{class:'editor-field'},el('span',{},label),input);
  }
  function updateNotice(){if(session.content&&execution)execution.forContent(session.content,{dirty:session.dirty(),readOnly:!canWrite()});delivery.refreshControls();updateRevisionControls();const notice=root.querySelector('[data-dirty]');if(notice)notice.textContent=session.dirty()?'미저장 변경 있음':'';root.querySelectorAll('[data-needs-clean]').forEach(node=>node.disabled=!canWrite()||session.dirty()||childBlocksRevision());}
  function notice(){return el('p',{class:'editor-message',role:'status','aria-live':'polite'},session.error||message|| (session.phase==='saved'?'저장했습니다.':busy?'처리 중입니다.':''));}
  async function action(task) {
    if(delivery.isBusy()||execution?.isBusy())return;
    busy=true;message='';session.error='';render();
    try {await task();}catch(error){session.error=error.message;session.phase=error.status===401?'unauthorized':error.status===409?'conflict':'error';}
    finally {busy=false;render();}
  }
  async function refreshVersions(){if(session.content){const data=await api.listRevisions(session.content.id);revisions=data.items||[];}}
  function render() {
    const c=session.content,d=session.draft;
    const form=el('form',{onsubmit:async event=>{event.preventDefault();if(!canWrite()||childBlocksRevision())return;await action(async()=>{const saved=await session.save(payload=>c?api.updateContent(c.id,payload):api.createContent(payload));if(saved){await refreshVersions();onSaved(saved);}});}});
    form.append(el('p',{'data-child-block':'',role:'status'}),el('p',{class:'inline-note'},historical?'과거 버전 · 읽기 전용':c?'새 관리 원본 · 소유 계정 고정':'새 관리 원본 · 조회 필터와 별도로 소유 계정을 선택하세요.'),notice());
    if(session.phase==='unauthorized')form.append(el('a',{href:'/login',target:'_blank',rel:'noopener'},'다른 탭에서 로그인 후 다시 시도'));
    if(c){
      const select=el('select',{'aria-label':'원본 버전 선택','data-parent-switch':'',disabled:busy||childBlocksRevision(),onchange:async event=>{
        if(childBlocksRevision()){event.target.value=String(c.revision);return;}
        if(hasChanges()&&!globalThis.confirm('저장하지 않은 변경을 버리고 버전을 전환할까요?')){event.target.value=String(c.revision);return;}
        const revision=Number(event.target.value);await action(async()=>{const next=await api.getContent(c.id,revision);historical=revision!==Math.max(...revisions.map(r=>r.revision),c.revision);session=createEditSession(next);reviewDraft={kind:'general',decision:'pass',notes:''};});
      }});
      for(const rev of revisions)select.append(el('option',{value:rev.revision},`버전 ${rev.revision} · ${formatDateTime(rev.created_at)}`));select.value=String(c.revision);
      form.append(el('label',{class:'editor-field'},'저장 버전',select));
      if(historical)form.append(button('최신 버전 열기',()=>open({id:c.id,source:'managed'}),busy));
      form.append(el('p',{},`원본 소유: ${accountLabel(c.owner_account_id)} · 버전 ${c.revision}`));
    }else form.append(field('원본 소유 계정 (필수)',d.owner_account_id,v=>d.owner_account_id=v,{type:'select',options:[['','직접 선택'],['personal','개인'],['dept','학과']]}));
    form.append(field('제목',d.title,v=>d.title=v,{maxLength:300}),el('div',{class:'editor-grid'},field('형식',d.kind,v=>d.kind=v,{type:'select',options:['article','card','short','video'].map(k=>[k,kindLabel(k)])}),field('상태',d.status,v=>d.status=v,{type:'select',options:['idea','drafting','production','review','archived'].map(k=>[k,statusLabel(k)])})),field('시리즈',d.series,v=>d.series=v),field('원문',d.original,v=>d.original=v,{type:'textarea',maxLength:200000}));
    const variants=el('section',{class:'editor-section'},el('h3',{},'대상별 변환본'),el('p',{class:'sub'},'목표 계정·채널은 기획 정보입니다. 예약이나 발행을 만들지 않습니다.'));
    d.variants.forEach((variant,i)=>variants.append(el('div',{class:'editor-row'},field('대상 계정',variant.destination_account_id,v=>variant.destination_account_id=v,{type:'select',options:[['personal','개인'],['dept','학과']]}),field('목표 채널',variant.platform,v=>variant.platform=v,{type:'select',options:platforms.map(p=>[p,p])}),field('변환 원고',variant.text,v=>variant.text=v,{type:'textarea',maxLength:200000}),button('변환본 삭제',()=>{d.variants.splice(i,1);render();},!canWrite()))));
    variants.append(button('변환본 추가',()=>{d.variants.push({destination_account_id:'personal',platform:'youtube',text:''});render();},!canWrite()||d.variants.length>=30));form.append(variants);
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
    if(c&&!historical){root.append(delivery.element);const key=`${c.id}:${c.revision}:${c.manifest_hash}`;if(key!==deliveryKey){deliveryKey=key;delivery.open(c);}else delivery.refreshControls();}
    if(c&&execution)root.append(execution.forContent(c,{dirty:session.dirty(),readOnly:!canWrite()}));
    updateRevisionControls();
  }
  async function open(content=null) {
    const token=++generation;deliveryKey='';delivery.open(null);historical=false;loadFailed=false;reviewDraft={kind:'general',decision:'pass',notes:''};message='';revisions=[];session=createEditSession();busy=true;render();
    try {
      if(content?.source==='managed'){const [full,history]=await Promise.all([api.getContent(content.id,content.revision),api.listRevisions(content.id)]);if(token!==generation)return;session=createEditSession(full);revisions=history.items||[];historical=full.revision<Math.max(full.revision,...revisions.map(item=>item.revision));}
      else if(content){session.draft=copyLegacySummary(content);session.baseline=JSON.stringify(emptyDraft());message='기존 자료의 수집 요약만 복사했습니다. 전체 원문은 제공되지 않았습니다. 새 원본 소유 계정을 선택해 저장하세요.';}
    }catch(error){if(token===generation){loadFailed=true;session.error=error.message;session.phase=error.status===401?'unauthorized':'error';}}
    finally {if(token===generation){busy=false;render();}}
  }
  execution?.subscribe?.(()=>updateRevisionControls());
  return {element:root,open,hasUnsavedChanges:hasChanges,isBusy:()=>busy||delivery.isBusy()||!!execution?.isBusy()};
}
