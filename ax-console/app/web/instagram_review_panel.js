// Instagram 고정 배포 구성의 수동 확인 기록. 게시 승인·파일 공개·외부 호출을 실행하지 않는다.
const KEYS=['plan_id','content_id','content_revision','manifest_hash','owner_account_id','destination_account_id','connection_id','target_id','media_format','caption','assets','subject_hash','review_revision','decision','checks','notes','review_method','status','audio_required'];
const ASSET_KEYS=['id','sha256','size','media_type'];
const CHECKS=[['rights_confirmed','선택한 모든 자산의 사용 권리를 확인했습니다'],['visual_checked','선택한 모든 이미지·영상 화면을 확인했습니다'],['caption_checked','이 대상 계정의 캡션·출처·고지를 확인했습니다'],['composition_checked','게시 형식과 모든 자산의 순서·구성을 확인했습니다'],['audio_checked','모든 영상의 음성·음악·고지를 확인했습니다']];
const CHECK_KEYS=CHECKS.map(([key])=>key),HEX=/^[0-9a-f]{64}$/;
const exact=(v,keys)=>!!v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const text=(v,max,nonblank=false)=>typeof v==='string'&&Array.from(v).length<=max&&!v.includes('\0')&&(!nonblank||!!v.trim())&&Array.from(v).every(c=>{const cp=c.codePointAt(0);return cp<0xd800||cp>0xdfff;});
const account=v=>v==='personal'||v==='dept';
const validAsset=a=>exact(a,ASSET_KEYS)&&text(a.id,200,true)&&HEX.test(a.sha256)&&Number.isInteger(a.size)&&a.size>0&&['image/jpeg','video/mp4'].includes(a.media_type);
const invalid=()=>Object.assign(new Error('invalid'),{kind:'invalid'});
const copy=v=>JSON.parse(JSON.stringify(v));
function binding(plan){
 if(!plan||plan.platform!=='instagram'||!text(plan.id,200,true)||!text(plan.content_id,200,true)||!Number.isInteger(plan.revision)||plan.revision<1||!HEX.test(plan.manifest_hash)||!account(plan.owner_account_id)||!account(plan.destination_account_id)||!text(plan.connection_id,200,true)||typeof plan.target_id!=='string'||!/^[0-9]{1,64}$/.test(plan.target_id)||plan.target_status!=='verified')return null;
 const selection=plan.options?.instagram;if(!exact(selection,['format','asset_ids'])||!['image','reels','carousel'].includes(selection.format)||!Array.isArray(selection.asset_ids)||!selection.asset_ids.length||selection.asset_ids.some(id=>!text(id,200,true))||new Set(selection.asset_ids).size!==selection.asset_ids.length)return null;
 return {plan_id:plan.id,content_id:plan.content_id,content_revision:plan.revision,manifest_hash:plan.manifest_hash,owner_account_id:plan.owner_account_id,destination_account_id:plan.destination_account_id,connection_id:plan.connection_id,target_id:plan.target_id,media_format:selection.format,asset_ids:[...selection.asset_ids]};
}
function validRow(row,ctx){
 if(!exact(row,KEYS)||!['plan_id','content_id','content_revision','manifest_hash','owner_account_id','destination_account_id','connection_id','target_id','media_format'].every(k=>row[k]===ctx[k])||!HEX.test(row.subject_hash)||!text(row.caption,2200,true)||!Array.isArray(row.assets)||!row.assets.every(validAsset)||row.assets.length!==ctx.asset_ids.length||!row.assets.every((a,i)=>a.id===ctx.asset_ids[i])||!Number.isInteger(row.review_revision)||row.review_revision<0||!exact(row.checks,CHECK_KEYS)||!CHECK_KEYS.every(k=>typeof row.checks[k]==='boolean')||!text(row.notes,2000)||row.review_method!=='manual'||typeof row.audio_required!=='boolean'||row.audio_required!==row.assets.some(a=>a.media_type==='video/mp4'))return false;
 if(row.media_format==='image'&&(row.assets.length!==1||row.assets[0].media_type!=='image/jpeg'))return false;
 if(row.media_format==='reels'&&(row.assets.length!==1||row.assets[0].media_type!=='video/mp4'))return false;
 if(row.media_format==='carousel'&&(row.assets.length<2||row.assets.length>10))return false;
 if(row.decision===null)return row.status==='not_reviewed'&&row.review_revision===0;
 if(!['approved','revoked'].includes(row.decision)||row.status!==row.decision||row.review_revision<1)return false;
 return row.decision!=='approved'||CHECK_KEYS.filter(k=>k!=='audio_checked'||row.audio_required).every(k=>row.checks[k]);
}
export function createInstagramReviewPanel({document,api,onChange=()=>{},requestTimeoutMs=45000}={}){
 const root=document.createElement('details');root.className='panel instagram-review';
 let ctx=null,ctxKey='',writable=false,row=null,baseline=null,draft=null,busy=false,loaded=false,uncertain=false,uncertainIntent=false,message='',generation=0;
 const dirty=()=>!!draft&&(uncertainIntent||JSON.stringify(draft)!==JSON.stringify(baseline));
 const editable=()=>!!ctx&&!!draft&&writable&&!busy;
 const canWrite=()=>editable()&&!uncertain;
 const node=(tag,attrs={},value)=>{const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='disabled')n.disabled=v;else n.setAttribute(k,String(v));}if(value!==undefined)n.textContent=value;return n;};
 function controls(){for(const n of root.querySelectorAll('[data-instagram-review-field]'))n.disabled=!editable();for(const n of root.querySelectorAll('[data-instagram-review-action]')){const a=n.getAttribute('data-instagram-review-action');n.disabled=a==='reload'?!ctx||busy:a==='discard'?!draft||busy:!canWrite();}}
 function paint(){
  const body=node('div',{class:'panel-body'});body.append(node('p',{},'선택한 Instagram 배포 구성을 사람이 확인한 기록입니다. 최종 게시 승인이나 파일 공개 동의가 아니며, 저장해도 외부 게시·공개 업로드를 실행하지 않습니다.'));
  if(row&&draft){
   body.append(node('p',{},`원본 ${row.owner_account_id==='personal'?'개인':'학과'} → 대상 ${row.destination_account_id==='personal'?'개인':'학과'} · 버전 ${row.content_revision} · ${row.media_format}`),node('h4',{},'대상 계정의 캡션'),node('pre',{},row.caption),node('h4',{},'선택한 자산 순서'));
   const list=node('ol');row.assets.forEach((asset,i)=>{const item=node('li',{},`${i+1}. ${asset.media_type} · ${asset.id} · ${asset.size} bytes · SHA256 ${asset.sha256} `);const href='/api/v2/contents/'+encodeURIComponent(row.content_id)+'/revisions/'+row.content_revision+'/assets/'+encodeURIComponent(asset.id);item.append(node('a',{href,target:'_blank',rel:'noopener noreferrer'},'등록 자산 열기'));list.append(item);});body.append(list);
   for(const [key,label] of CHECKS){if(key==='audio_checked'&&!row.audio_required)continue;const checkbox=node('input',{type:'checkbox','data-instagram-review-field':key});checkbox.checked=draft.checks[key];checkbox.addEventListener('change',()=>{if(!editable())return;draft.checks[key]=checkbox.checked===true;onChange();});const field=node('label');field.append(checkbox,document.createTextNode(' '+label));body.append(field);}
   const notes=node('textarea',{maxlength:2000,'aria-label':'Instagram 최종 구성 검토 메모','data-instagram-review-field':'notes'});notes.value=draft.notes;notes.addEventListener('input',()=>{if(!editable())return;draft.notes=notes.value;onChange();});const label=node('label');label.append(document.createTextNode('검토 메모 '),notes);body.append(label);
   for(const [name,label,fn] of [['approve','검토 확인 저장',()=>save('approved')],['revoke','검토 철회',()=>save('revoked')],['discard','입력 버리기',discardChanges]]){const button=node('button',{type:'button',class:'btn btn-small','data-instagram-review-action':name},label);button.addEventListener('click',fn);body.append(button);}
   body.append(node('p',{class:'sub'},row.status==='approved'?'수동 구성 확인 기록 있음 · 게시 승인·실행과 별개':row.status==='revoked'?'수동 구성 확인이 철회됐습니다.':'수동 구성 확인 기록이 없습니다.'));
  }
  const reload=node('button',{type:'button',class:'btn btn-small','data-instagram-review-action':'reload'},'검토 기록 다시 조회');reload.addEventListener('click',reloadRecord);body.append(reload,node('p',{role:'status'},message));root.replaceChildren(node('summary',{},'Instagram 최종 구성 검토'),body);controls();
 }
 async function invoke(fn){let timer;const wait=Number.isFinite(requestTimeoutMs)&&requestTimeoutMs>0&&requestTimeoutMs<=120000?requestTimeoutMs:45000;try{return await Promise.race([Promise.resolve().then(fn),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Object.assign(new Error('timeout'),{kind:'timeout'})),wait);})]);}finally{clearTimeout(timer);}}
 const errorText=(e,write=false)=>e.kind==='invalid'?'검토 응답의 계획·계정·자산 구성을 확인할 수 없습니다. 입력은 보존했습니다. 다시 조회하세요.':e.status===401?'로그인 후 다시 조회하세요. 검토 입력은 보존했습니다.':e.status===409?'계획이나 검토 기록이 바뀌었습니다. 입력은 보존했습니다. 입력을 버린 뒤 검토 기록을 다시 조회하세요.':e.status===400||e.status===422?'게시 대상 또는 검토 입력을 확인하지 못했습니다. 대상 계정과 저장 계획을 다시 확인하세요.':e.kind==='timeout'||write?'검토 저장 결과를 확인하지 못했습니다. 입력은 보존했습니다. 자동 재요청하지 않으며, 기록을 다시 조회해 확인하세요.':'검토 기록을 조회하지 못했습니다. 잠시 뒤 직접 다시 조회하세요.';
 function apply(value){row=copy(value);baseline={checks:copy(value.checks),notes:value.notes};draft=copy(baseline);loaded=true;uncertain=uncertainIntent=false;}
 async function load(){if(!ctx||busy)return;const mine=ctx,token=++generation;busy=true;message='검토 구성 조회 중';paint();onChange();try{if(typeof api?.getInstagramReview!=='function')throw invalid();const value=await invoke(()=>api.getInstagramReview(mine.plan_id));if(token!==generation)return;if(!validRow(value,mine))throw invalid();apply(value);message='고정된 캡션과 자산 순서를 확인한 뒤 직접 기록하세요.';}catch(e){if(token===generation)message=errorText(e);}finally{if(token===generation){busy=false;paint();onChange();}}}
 async function save(decision){
  if(!canWrite())return;if(!text(draft.notes,2000)){message='검토 메모는 올바른 문자로 2000자 이하로 입력하세요.';paint();return;}
  if(decision==='approved'&&!CHECK_KEYS.filter(k=>k!=='audio_checked'||row.audio_required).every(k=>draft.checks[k])){message='필요한 항목을 모두 직접 확인해야 저장할 수 있습니다.';paint();return;}
  const mine=ctx,token=++generation,body={expected_review_revision:row.review_revision,subject_hash:row.subject_hash,decision,checks:copy(draft.checks),notes:draft.notes};busy=true;message='수동 검토 기록 저장 중';paint();onChange();
  try{if(typeof api?.recordInstagramReview!=='function')throw invalid();const value=await invoke(()=>api.recordInstagramReview(mine.plan_id,body));if(token!==generation)return;if(!validRow(value,mine)||value.subject_hash!==body.subject_hash||value.review_revision!==body.expected_review_revision+1||value.decision!==decision||value.notes!==body.notes||!CHECK_KEYS.every(k=>value.checks[k]===body.checks[k]))throw invalid();apply(value);message=decision==='approved'?'수동 구성 확인을 저장했습니다. 최종 게시 승인과 파일 공개는 별도입니다.':'수동 구성 확인을 철회했습니다.';}catch(e){if(token===generation){uncertain=uncertainIntent=true;message=errorText(e,true);}}finally{if(token===generation){busy=false;paint();onChange();}}
 }
 function discardChanges(){if(!baseline||busy)return;draft=copy(baseline);uncertainIntent=false;paint();onChange();}
 async function reloadRecord(){if(!ctx||busy)return;if(dirty()&&(typeof globalThis.confirm!=='function'||!globalThis.confirm('미저장 검토 입력을 버리고 저장된 기록을 다시 조회할까요?')))return;return load();}
 root.addEventListener('toggle',()=>{if(root.open&&ctx&&!loaded&&!busy)return load();});paint();
 return {element:root,isDirty:dirty,isBusy:()=>busy,discardChanges,refreshControls(options={}){if(options.writable!==undefined)writable=options.writable===true;controls();},open(plan,{writable:w=true}={}){const next=binding(plan),key=next?JSON.stringify(next):'';writable=w===true;if(next&&key===ctxKey){controls();return Promise.resolve();}generation++;ctx=next;ctxKey=key;row=baseline=draft=null;busy=loaded=uncertain=uncertainIntent=false;message=plan&&!next?'게시 대상 ID 또는 저장된 Instagram 계획을 확인할 수 없습니다. 대상 확인 후 계획을 다시 여세요.':'';root.open=false;paint();onChange();return Promise.resolve();}};
}
