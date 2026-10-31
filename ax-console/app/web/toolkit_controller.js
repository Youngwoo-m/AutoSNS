const methods={packaging:'packagingPreview',research:'researchPreview',thumbnailInspect:'thumbnailInspect',thumbnailRender:'thumbnailRender',csv:'csvPreview',csvImport:'csvImport',schedule:'scheduleInspect',capabilities:'capabilities'};
const copy=x=>JSON.parse(JSON.stringify(x));
export function createToolkitController({api,onChange=()=>{}}) {
 let context={},generation=0,serial=0;const accounts=new Map();
 function state() {
  const key=context.account||'all';
  if(!accounts.has(key))accounts.set(key,{
   inputs:{csv_text:'',keywords:'',preset_id:'landscape.v1'},reports:{},
   busy:false,dirty:false,error:null,requestKey:null,bindings:{}
  });
  return accounts.get(key);
 }
 const getState=()=>copy({...state(),context,generation});
 const emit=()=>onChange(getState());
 function setContext(next) {
  const normalized={...next};
  if(JSON.stringify(normalized)!==JSON.stringify(context)) {
   generation++;context=normalized;
   for(const value of accounts.values())value.busy=false;
  }
  return getState();
 }
 function updateInput(name,value) {
  const s=state();
  s.inputs[name]=value;s.dirty=true;s.error=null;generation++;s.busy=false;
  if(name==='keywords'){delete s.reports.packaging;delete s.bindings.packaging;}
  if(name==='csv_text'){delete s.reports.csv;delete s.reports.csvImport;s.requestKey=null;}
  emit();
 }
 function bodyFor(kind,payload,s) {
  const base={content_id:context.contentId,revision:context.revision};
  switch(kind) {
   case 'packaging':return {...base,connection_id:context.connectionId,
    keywords:payload.keywords??s.inputs.keywords.split(',').map(x=>x.trim()).filter(Boolean)};
   case 'research':return {account_id:context.account};
   case 'csv':return {account_id:context.account,csv_text:s.inputs.csv_text};
   case 'csvImport':
    if(!s.reports.csv?.preview_digest)throw new Error('CSV 미리보기가 필요합니다.');
    s.requestKey??=`toolkit-${Date.now()}-${++serial}`;
    return {account_id:context.account,csv_text:s.inputs.csv_text,
     preview_digest:s.reports.csv.preview_digest,request_key:s.requestKey};
   case 'thumbnailInspect':return {...base,asset_id:payload.asset_id};
   case 'thumbnailRender':return {...base,asset_id:payload.asset_id??null,preset_id:payload.preset_id,title:payload.title};
   case 'schedule':return {delivery_id:payload.delivery_id};
   default:throw new Error('지원하지 않는 도구입니다.');
  }
 }
 async function preview(kind,payload={}) {
  const s=state();
  if(s.busy)return null;
  if(!methods[kind])throw new Error('지원하지 않는 도구입니다.');
  const token=++generation;
  const binding={contentId:context.contentId,revision:context.revision,
   inputHash:context.inputHash,connectionId:context.connectionId};
  s.busy=true;s.error=null;emit();
  try {
   const result=await (kind==='capabilities'?api.capabilities(context.contentId?'all':context.account):
    api[methods[kind]](bodyFor(kind,payload,s)));
   if(token!==generation)return null;
   if(kind==='csv'&&s.reports.csv?.preview_digest!==result?.preview_digest)s.requestKey=null;
   s.reports[kind]=result;s.bindings[kind]=binding;
   if(kind==='csvImport')s.requestKey=null;
   return result;
  } catch(error) {
   if(token===generation)s.error=({401:'로그인이 필요합니다.',409:'대상이 변경되었습니다.',
    503:'도구를 사용할 수 없습니다.'})[error.status]||'요청을 처리하지 못했습니다.';
   return null;
  } finally {
   if(token===generation){s.busy=false;emit();}
  }
 }
 function stageCandidate(id,{contentId,revision,inputHash,variantIndex}={}) {
  const s=state(), binding=s.bindings.packaging;
  const sameContext=binding && binding.contentId===contentId && binding.revision===revision &&
   binding.inputHash===inputHash && context.contentId===contentId && context.revision===revision &&
   context.inputHash===inputHash && context.connectionId===binding.connectionId;
  if(s.busy || context.editorDirty!==false || !inputHash || !sameContext)
   throw new Error('원고 변경 또는 미리보기 대상이 다릅니다.');
  const report=s.reports.packaging;
  const candidate=report?.candidates?.find(c=>c.id===id);
  if(!candidate)throw new Error('후보가 없습니다.');
  const patch={title:candidate.title};
  if(variantIndex!==undefined) {
   const variant=context.variants?.[variantIndex];
   if(!Number.isInteger(variantIndex) || !variant || variant.destination_account_id!==report.destination_account_id ||
    variant.platform!==report.platform || typeof variant.text!=='string')
    throw new Error('대상 변환문을 명시적으로 선택하세요.');
   const tags=(candidate.hashtags||[]).filter(tag=>typeof tag==='string' && /^#[\p{L}\p{N}_]+$/u.test(tag));
   const existing=new Set(variant.text.split(/\s+/));
   const appended=tags.filter(tag=>!existing.has(tag)).join(' ');
   patch.variant={index:variantIndex,destination_account_id:variant.destination_account_id,
    platform:variant.platform,text:variant.text+(appended?(variant.text?'\n\n':'')+appended:'')};
  }
  return patch;
 }

 return {setContext,preview,stageCandidate,updateInput,getState,isBusy:()=>state().busy,isDirty:()=>state().dirty,discard(){generation++;accounts.delete(context.account||'all');emit();}};
}
