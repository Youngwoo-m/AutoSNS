// 이미지 재사용 확인 패널. 사람이 남기는 수동 확인 기록만 다루며 AI 검사·렌더·게시가 아니다. 조회·저장은 버튼 한 번이 요청 한 번이고 자동 재시도·반복 조회가 없다.
const IMAGE_TYPES=['image/png','image/jpeg','image/webp'];
const ROW_KEYS=['content_id','content_revision','manifest_hash','owner_account_id','asset_id','sha256','approval_revision','approved_revision','rights_confirmed','visual_checked','notes','status','review_method'];
const MAX_NOTES=2000,SHORT_SHA=12;
const SHA=/^[a-f0-9]{64}$/;
const exactKeys=(o,keys)=>!!o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).length===keys.length&&keys.every(k=>Object.hasOwn(o,k));
const isCount=v=>Number.isInteger(v)&&v>=0;
const noteLength=s=>Array.from(s).length;
const validRow=(r,c)=>{
  if(!exactKeys(r,ROW_KEYS))return false;
  const asset=typeof r.asset_id==='string'?c.assets.find(a=>a.id===r.asset_id):null;
  return r.content_id===c.id&&r.content_revision===c.revision&&r.manifest_hash===c.manifest_hash&&r.owner_account_id===c.owner_account_id
    &&!!asset&&r.sha256===asset.sha256
    &&isCount(r.approval_revision)
    &&(r.approved_revision===null||(Number.isInteger(r.approved_revision)&&r.approved_revision>=1))
    &&(r.approval_revision===0)===(r.approved_revision===null)
    &&typeof r.rights_confirmed==='boolean'&&typeof r.visual_checked==='boolean'
    &&typeof r.notes==='string'&&noteLength(r.notes)<=MAX_NOTES
    &&(r.status==='approved'||r.status==='not_approved')&&(r.status==='approved')===(r.rights_confirmed&&r.visual_checked)
    &&r.review_method==='manual';
};
const pick=r=>Object.fromEntries(ROW_KEYS.map(k=>[k,r[k]]));
const fromRow=r=>({rights:r.rights_confirmed,visual:r.visual_checked,notes:r.notes});
const record=r=>({pub:pick(r),base:fromRow(r),draft:fromRow(r)});
const same=(a,b)=>a.rights===b.rights&&a.visual===b.visual&&a.notes===b.notes;
const invalid=()=>Object.assign(new Error('invalid'),{kind:'invalid'});

export function createReuseApprovalPanel({document,fetcher=globalThis.fetch,onChange=()=>{},requestTimeoutMs=45000}={}) {
  const root=document.createElement('details');root.className='panel reuse-approval';
  let ctx=null,writable=true,rows=[],loaded=false,busy=null,busyId=null,message='',generation=0,inflight=null;
  let views=new Map(),inputs=new Map(),bannerNode=null,discardNode=null;
  const rowDirty=rec=>!same(rec.draft,rec.base);
  const dirty=()=>rows.some(rowDirty);
  const canEdit=()=>!!ctx&&writable&&busy===null;
  const node=(tag,attrs={},text)=>{const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='disabled')n.disabled=v;else n.setAttribute(k,String(v));}if(text!==undefined)n.textContent=text;return n;};
  const baseUrl=mine=>'/api/v2/contents/'+encodeURIComponent(mine.id);
  const listUrl=mine=>baseUrl(mine)+'/reuse-approvals?revision='+mine.revision;
  const imageUrl=(mine,assetId)=>baseUrl(mine)+'/revisions/'+mine.revision+'/assets/'+encodeURIComponent(assetId);
  async function send(url,method,body){
    const controller=new AbortController();let timer;
    const wait=Number.isFinite(requestTimeoutMs)&&requestTimeoutMs>0&&requestTimeoutMs<=120000?requestTimeoutMs:45000;
    inflight=controller;
    try{
      const operation=(async()=>{
        let response;
        try{response=await fetcher(url,{method,credentials:'same-origin',cache:'no-store',signal:controller.signal,headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});}
        catch{throw Object.assign(new Error('network'),{kind:'network'});}
        if(!response.ok)throw Object.assign(new Error('http'),{kind:'http',status:response.status});
        try{return await response.json();}catch{return null;}
      })();
      const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(Object.assign(new Error('timeout'),{kind:'timeout'}));},wait);});
      return await Promise.race([operation,deadline]);
    }finally{clearTimeout(timer);if(inflight===controller)inflight=null;}
  }
  const readMessage=e=>{
    if(e.kind==='invalid')return '응답의 원고 버전·소유 계정·이미지 정보를 확인할 수 없어 표시하지 않았습니다. 입력은 유지됩니다.';
    if(e.kind==='http'&&e.status===401)return '로그인 후 다시 시도하세요. 입력은 유지됩니다.';
    if(e.kind==='http'&&e.status===409)return '원고 버전이 맞지 않아 조회하지 못했습니다. 입력은 유지됩니다.';
    if(e.kind==='http'&&e.status===503)return '확인 기록 서버를 지금 사용할 수 없습니다. 입력은 유지됩니다. 잠시 뒤 직접 다시 조회하세요.';
    if(e.kind==='timeout')return '서버 응답이 늦어 조회를 중단했습니다. 자동으로 다시 요청하지 않습니다. 입력은 유지됩니다.';
    if(e.kind==='network')return '서버에 연결하지 못했습니다. 입력은 유지됩니다.';
    return '확인 기록을 조회하지 못했습니다. 입력은 유지됩니다.';
  };
  const UNCERTAIN='저장 결과를 알 수 없습니다. 입력은 보존했고 자동으로 다시 요청하지 않습니다. 저장된 확인 기록을 다시 조회해 확인한 뒤 필요하면 직접 다시 저장하세요.';
  const writeMessage=e=>{
    if(e.kind==='invalid')return '저장 응답의 원고 버전·이미지 정보를 확인할 수 없어 반영하지 않았습니다. 입력은 보존했습니다. 저장된 확인 기록을 다시 조회해 확인하세요.';
    if(e.kind==='http'&&e.status===401)return '로그인 후 다시 시도하세요. 기록은 저장되지 않았습니다. 입력은 보존했습니다.';
    if(e.kind==='http'&&e.status===409)return '다른 창에서 확인 기록이 바뀌었거나 원고 버전이 달라 저장하지 못했습니다. 입력을 보존했습니다. 저장된 확인 기록을 다시 조회해 비교하세요.';
    if(e.kind==='http'&&e.status===503)return '확인 기록 저장소를 지금 사용할 수 없어 저장 결과를 확인하지 못했습니다. 입력을 보존했습니다. 다시 조회해 확인한 뒤 필요하면 직접 다시 저장하세요. 자동으로 다시 요청하지 않습니다.';
    if(e.kind==='http'&&(e.status===400||e.status===422))return '서버가 입력을 받아들이지 않았습니다. 메모와 확인 항목을 점검하세요. 입력은 보존했습니다.';
    return UNCERTAIN;
  };
  async function fetchRows(mine){
    const data=await send(listUrl(mine),'GET');
    if(!exactKeys(data,['items'])||!Array.isArray(data.items))throw invalid();
    if(!data.items.every(r=>validRow(r,mine)))throw invalid();
    if(new Set(data.items.map(r=>r.asset_id)).size!==data.items.length)throw invalid();
    return data.items.map(record);
  }
  const hintText=rec=>{
    if(!rowDirty(rec))return '';
    const lead='저장하지 않은 변경이 있습니다. ';
    if(rec.draft.rights&&rec.draft.visual)return lead+'저장하면 두 확인이 모두 기록되어 승인으로 처리됩니다.';
    if(rec.pub.status==='approved')return lead+'저장하면 기존 승인이 철회된 기록으로 남습니다. 이전 기록은 삭제되지 않습니다.';
    return lead+'확인이 하나라도 빠지면 저장해도 승인되지 않습니다.';
  };
  const canSave=rec=>canEdit()&&rowDirty(rec);
  function touched(rec){
    const view=views.get(rec.pub.asset_id);
    if(view){view.save.disabled=!canSave(rec);view.hint.textContent=hintText(rec);}
    if(bannerNode)bannerNode.textContent=dirty()?'저장하지 않은 입력이 있습니다. 저장 버튼을 누른 이미지만 기록됩니다.':'';
    if(discardNode)discardNode.disabled=busy!==null||!dirty();
    onChange();
  }
  function rowCard(rec){
    const row=rec.pub,id=row.asset_id,asset=ctx.assets.find(a=>a.id===id);
    const card=node('div',{class:'reuse-approval-row','data-reuse-row':id});
    card.append(node('h4',{},asset.filename||'등록 이미지'));
    const img=node('img',{src:imageUrl(ctx,id),alt:`${asset.filename||'등록 이미지'} 미리보기`,loading:'lazy','data-reuse-image':id});
    img.style.maxWidth='240px';img.style.maxHeight='240px';card.append(img);
    card.append(node('p',{class:'sub'},`이미지 SHA-256 ${row.sha256.slice(0,SHORT_SHA)} · ${row.approval_revision>0?`확인 기록 버전 ${row.approval_revision}`:'확인 기록 없음'}`));
    card.append(node('p',{'data-reuse-status':id},`현재 상태: ${row.status==='approved'?'승인됨':'승인 전'} · 사람이 직접 남긴 수동 확인 기록이며 AI 검사가 아닙니다.`));
    if(row.approved_revision!==null){
      card.append(node('p',{class:'sub'},`확인 당시 원고 버전 ${row.approved_revision}`));
      if(row.status==='approved'&&row.approved_revision<ctx.revision)card.append(node('p',{class:'sub','data-reuse-info':'carried'},`같은 이미지의 과거 확인 기록을 적용 중입니다 (원고 버전 ${row.approved_revision}에서 확인).`));
      if(row.approved_revision>ctx.revision)card.append(node('p',{class:'sub'},'과거 원고를 보고 있습니다. 같은 이미지에 대해 이후 버전에서 남긴 최신 확인 상태를 표시합니다.'));
    }
    const locked=!canEdit();
    const box=(field,label)=>{
      const input=node('input',{type:'checkbox','data-reuse-for':id,'data-reuse-field':field,disabled:locked});input.checked=rec.draft[field];
      input.addEventListener('change',()=>{if(!canEdit()){input.checked=rec.draft[field];return;}rec.draft[field]=input.checked===true;touched(rec);});
      inputs.set(id+'\n'+field,input);
      const l=node('label');l.append(input,document.createTextNode(' '+label));return l;
    };
    card.append(box('rights','이 이미지를 동영상에 사용할 권리·허락을 확인했습니다'),box('visual','이미지 내용·글자·도식이 적절한지 사람이 직접 확인했습니다'));
    const notes=node('textarea',{maxlength:MAX_NOTES,'data-reuse-for':id,'data-reuse-field':'notes','aria-label':`${asset.filename||'등록 이미지'} 확인 메모`,disabled:locked});notes.value=rec.draft.notes;
    notes.addEventListener('input',()=>{if(!canEdit()){notes.value=rec.draft.notes;return;}rec.draft.notes=notes.value;touched(rec);});
    inputs.set(id+'\nnotes',notes);
    const nl=node('label');nl.append(document.createTextNode(`메모 (최대 ${MAX_NOTES}자) `),notes);card.append(nl);
    const hint=node('p',{class:'sub','data-reuse-hint':id},hintText(rec));card.append(hint);
    const save=node('button',{type:'button',class:'btn btn-small','data-reuse-action':'save','data-reuse-for':id,disabled:!canSave(rec)},busy==='saving'&&busyId===id?'저장 중…':'확인 기록 저장');
    save.addEventListener('click',()=>saveRow(id));card.append(save);
    views.set(id,{save,hint});
    return card;
  }
  function paint(){
    const active=document.activeElement;
    const focusKey=active&&root.contains(active)&&active.getAttribute&&active.getAttribute('data-reuse-field')?active.getAttribute('data-reuse-for')+'\n'+active.getAttribute('data-reuse-field'):null;
    const range=focusKey&&typeof active.selectionStart==='number'?[active.selectionStart,active.selectionEnd]:null;
    views=new Map();inputs=new Map();bannerNode=discardNode=null;
    const summary=node('summary',{},'이미지 재사용 확인');const body=node('div',{class:'panel-body'});
    body.append(node('p',{},'동영상에 쓸 이미지를 사람이 직접 확인한 기록입니다. 수동 확인 기록이며 AI 검사가 아닙니다. 저장은 기록만 남기고 모델 호출·렌더·게시는 하지 않으며, 두 확인을 모두 체크해 저장한 이미지만 승인으로 기록됩니다. 체크를 풀고 저장하면 철회 기록이 남습니다.'));
    if(ctx){
      body.append(node('p',{'data-reuse-info':'content'},`원고 버전 ${ctx.revision} · 소유 계정 ${ctx.owner_account_id} · ${ctx.title}`));
      if(!writable)body.append(node('p',{class:'sub'},'읽기 전용 상태라 확인 기록을 저장할 수 없습니다.'));
      if(loaded&&!rows.length)body.append(node('p',{'data-reuse-info':'empty'},'등록된 이미지 없음 (PNG·JPEG·WebP 이미지가 이 원고 버전에 없습니다).'));
      rows.forEach(rec=>body.append(rowCard(rec)));
      bannerNode=node('p',{class:'sub','data-reuse-info':'dirty'},dirty()?'저장하지 않은 입력이 있습니다. 저장 버튼을 누른 이미지만 기록됩니다.':'');body.append(bannerNode);
      discardNode=node('button',{type:'button',class:'btn btn-small','data-reuse-action':'discard',disabled:busy!==null||!dirty()},'입력 변경 버리기');
      discardNode.addEventListener('click',()=>{
        if(!ctx||busy!==null||!dirty())return;
        if(typeof globalThis.confirm!=='function'||!globalThis.confirm('저장하지 않은 입력 변경을 버릴까요? 이미 저장된 확인 기록은 지워지지 않습니다.'))return;
        resetDrafts();message='입력 변경을 버렸습니다. 저장된 확인 기록은 그대로입니다.';paint();onChange();
      });body.append(discardNode);
    }else body.append(node('p',{},'원고를 열면 저장된 이미지 확인 기록을 조회합니다.'));
    const reload=node('button',{type:'button',class:'btn btn-small','data-reuse-action':'reload',disabled:busy!==null||!ctx},busy==='loading'?'조회 중…':'저장된 확인 기록 다시 조회');
    reload.addEventListener('click',()=>{
      if(!ctx||busy!==null)return;
      if(dirty()&&(typeof globalThis.confirm!=='function'||!globalThis.confirm('저장하지 않은 입력을 버리고 저장된 확인 기록을 다시 조회할까요?')))return;
      return load();
    });
    body.append(reload,node('p',{role:'status'},message));
    root.replaceChildren(summary,body);
    const target=focusKey?inputs.get(focusKey):null;
    if(target&&!target.disabled){target.focus();if(range&&typeof target.setSelectionRange==='function')target.setSelectionRange(range[0],range[1]);}
  }
  const resetDrafts=()=>{for(const rec of rows)rec.draft={...rec.base};};
  async function load(){
    if(!ctx)return;
    const token=++generation,mine=ctx;busy='loading';busyId=null;message='조회 중';paint();onChange();
    try{const next=await fetchRows(mine);if(token!==generation)return;rows=next;loaded=true;message='저장된 확인 기록을 조회했습니다. 조회만 했으며 승인을 새로 만들지 않았습니다.';}
    catch(e){if(token===generation)message=readMessage(e);}
    finally{if(token===generation){busy=null;paint();onChange();}}
  }
  async function saveRow(id){
    const rec=rows.find(r=>r.pub.asset_id===id);
    if(!ctx||!writable||busy!==null||!rec||!rowDirty(rec))return;
    if(noteLength(rec.draft.notes)>MAX_NOTES){message=`메모는 ${MAX_NOTES}자 이하여야 합니다.`;paint();return;}
    const token=++generation,mine=ctx,sent={...rec.draft},wasApproved=rec.pub.status==='approved';
    const body={asset_id:id,expected_revision:rec.pub.approval_revision,rights_confirmed:sent.rights,visual_checked:sent.visual,notes:sent.notes};
    busy='saving';busyId=id;message='확인 기록 저장 중 · 결과가 나올 때까지 다시 누르지 마세요';paint();onChange();
    try{
      const data=await send(listUrl(mine),'POST',body);
      if(token!==generation)return;
      if(!validRow(data,mine)||data.asset_id!==id)throw invalid();
      rows=rows.map(r=>r===rec?record(data):r);
      message=data.status==='approved'?'확인 기록을 저장했습니다. 승인으로 기록되었으며 수동 확인입니다. 렌더·게시는 하지 않았습니다.':wasApproved?'승인 철회 기록을 저장했습니다. 이전 기록은 삭제되지 않습니다.':'확인 기록을 저장했습니다. 두 확인이 모두 체크되지 않아 승인되지 않았습니다.';
    }catch(e){if(token===generation)message=writeMessage(e);}
    finally{if(token===generation){busy=null;busyId=null;paint();onChange();}}
  }
  paint();
  return {
    element:root,isDirty:dirty,isBusy:()=>busy!==null,
    discardChanges(){resetDrafts();paint();onChange();},
    refreshControls(options={}){
      if(!options||options.writable===undefined)return;
      const next=options.writable===true;
      if(next===writable)return;
      writable=next;paint();
    },
    open(content,{writable:w=true}={}){
      generation++;if(inflight)inflight.abort();busy=null;busyId=null;rows=[];loaded=false;message='';writable=w===true;
      const ok=content&&typeof content.id==='string'&&content.id&&Number.isInteger(content.revision)&&content.revision>=1&&typeof content.manifest_hash==='string'&&typeof content.owner_account_id==='string'&&content.owner_account_id;
      if(!ok){ctx=null;if(content)message='원고 정보를 확인할 수 없어 이미지 확인 기록을 조회하지 않았습니다.';paint();onChange();return Promise.resolve();}
      ctx={id:content.id,revision:content.revision,manifest_hash:content.manifest_hash,owner_account_id:content.owner_account_id,title:String(content.title??''),assets:(Array.isArray(content.assets)?content.assets:[]).map(a=>({id:a?.id,filename:typeof a?.filename==='string'?a.filename:'',media_type:a?.media_type,sha256:a?.sha256})).filter(a=>typeof a.id==='string'&&a.id&&IMAGE_TYPES.includes(a.media_type)&&typeof a.sha256==='string'&&SHA.test(a.sha256))};
      return load();
    }
  };
}
