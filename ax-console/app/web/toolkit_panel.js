export function createToolkitPanel({controller,document}) {
 const element=document.createElement('section');
 element.className='toolkit-panel';
 let current={},fileSelection=0,fileReadError=null,actionError='';
 const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
 const scalar=value=>typeof value==='string'||typeof value==='number'?String(value):'미확인';
 function button(text,action,disabled=false){
  const n=node('button',text);n.type='button';n.disabled=disabled;
  n.addEventListener('click',async e=>{
   e.preventDefault();if(n.disabled||controller.isBusy())return;
   n.disabled=true;actionError='';
   try{await action();}catch{actionError='원고나 대상이 변경되었습니다. 입력을 확인하고 다시 미리보기하세요.';}finally{render(current);}
  });return n;
 }
 function field(name,label){
  const input=node('input');input.name=`toolkit_${name}`;input.value=controller.getState().inputs[name]||'';
  const id=`toolkit-${current.section||'all'}-${name}`;input.id=id;
  const caption=node('label',label);caption.htmlFor=id;
  input.addEventListener('input',()=>{
   controller.updateInput(name,input.value);
   if(name==='connection_id'){current={...current,context:{...controller.getState().context,connectionId:input.value||null}};controller.setContext(current.context);}
  });element.append(caption,input);return input;
 }
 function stageButton(label,id,variantId){
  const n=button(label,()=>{
   const context=controller.getState().context;
   const patch=controller.stageCandidate(id,{...context,variantId});
   element.dispatchEvent?.(new CustomEvent('toolkit-stage',{detail:patch}));
  },!current.writable||controller.getState().context.editorDirty!==false||controller.isBusy());
  n.setAttribute('data-toolkit-stage','');return n;
 }
 function renderSchedule(report) {
  for(const [key,label] of [['delivery_id','배포 ID'],['state','예약 상태'],['target_id','대상 ID'],['remote_id','원격 ID'],['scheduled_at','예약 시각']])element.append(node('p',`${label}: ${scalar(report[key])}`));
  element.append(node('p',`실행: ${report.execution_enabled===true?'활성':report.execution_enabled===false?'비활성':'미확인'}`));
  const reasons=Array.isArray(report.reason_codes)?report.reason_codes.filter(reason=>typeof reason==='string'):[];
  element.append(node('p',`사유: ${reasons.length?reasons.join(', '):'제공된 사유 없음'}`));
 }
 async function readCsvFile(file) {
  const selection=++fileSelection,chosen=file.files?.[0];if(!chosen)return;
  const before=controller.getState();
  const isCurrent=()=>selection===fileSelection&&controller.getState().context.account===before.context.account&&controller.getState().generation===before.generation;
  fileReadError=null;
  try{const text=await chosen.text();if(!isCurrent())return;controller.updateInput('csv_text',text);}
  catch{if(!isCurrent())return;fileReadError={generation:before.generation,message:'CSV 파일을 읽지 못했습니다. 기존 입력은 보존됩니다.'};}
  render(current);
 }
 function renderReport(kind,report){
  if(!report)return;
  if(kind==='schedule')renderSchedule(report);
  if(['unavailable','blocked'].includes(report.status))element.append(node('p',`사용 불가: ${report.reason||report.reason_code||(report.reason_codes||[]).join(', ')||report.status}`));
  for(const candidate of report.candidates||[]){
   const id=candidate.id??candidate.candidate_id;element.append(node('p',candidate.title||candidate.text||''),stageButton('초안에 반영',id));
   for(const variant of candidate.variants||[]){if(typeof variant.text!=='string'||typeof variant.id!=='string')continue;element.append(node('p',variant.text),stageButton('선택한 본문을 초안에 반영',id,variant.id));}
  }
  for(const item of report.items||[]){if(typeof item==='string')element.append(node('p',item));else if(typeof item.title==='string')element.append(node('p',item.title));}
  if(typeof report.png_base64==='string'&&/^[A-Za-z0-9+/=]+$/.test(report.png_base64)){
   const link=node('a','PNG 다운로드');link.href=`data:image/png;base64,${report.png_base64}`;link.download='toolkit-preview.png';
   element.append(link,node('p','원고 저장은 기존 첨부 기능을 사용하세요. 기술 검사는 독립 검토 통과와 별도입니다.'));
  }
 }
 function render(options={}){
  current=options;const {context,writable=false,section='all'}=options;if(context)controller.setContext(context);
  const s=controller.getState(),all=section==='all';element.replaceChildren();
  element.append(node('h3','로컬 SNS 도구'),node('p','추가 유료 API·credit 자동 사용 없음 · 실행 정책은 서버에서 확인합니다.'));
  const capability=s.reports.capabilities;
  element.append(node('p',`로컬 정책: ${capability?capability.toolkit_enabled?'활성':'비활성':'미확인'} · 외부 실행: 미지원 · 읽기·쓰기 권한: 미확인`));
  element.append(button('도구 상태 확인',()=>controller.preview('capabilities'),s.busy));
  for(const item of capability?.items||[])element.append(node('p',`${scalar(item.action_id)} · ${scalar(item.implementation_status)} · ${scalar(item.cost_kind)}`));
  for(const connection of capability?.connections||[])element.append(node('p',`등록 연결 ${scalar(connection.connection_id)} · 대상 ${scalar(connection.target_id)} · 인증 ${scalar(connection.auth_status)} · 읽기/쓰기 권한 미확인`));
  if(s.error)element.append(node('p',`${s.error} 입력과 요청키는 보존됩니다.`));if(actionError)element.append(node('p',actionError));
  if(all||section==='editor'||section==='planning'){
   field('keywords','검색어 (쉼표로 구분)');
   if(all||section==='editor'){
    field('connection_id','실제 등록 연결 ID (도구 상태 확인에서 조회)');
    element.append(button('제목·본문 후보 미리보기',()=>controller.preview('packaging'),s.busy||!context?.contentId));
   }
   element.append(button('저장 근거로 조사',()=>controller.preview('research'),s.busy));
   for(const kind of ['packaging','research'])renderReport(kind,s.reports[kind]);
   element.append(node('p','검색량·경쟁도·예측 CTR: unavailable (공개·저장 근거 부족)'));
  }
  if(all||section==='editor'){
   field('asset_id','첨부 자산 ID');field('preset_id','고정 템플릿 ID (landscape.v1 / portrait.v1)');field('title','썸네일 제목');
   element.append(node('p','고정 템플릿·서버 등록 한글 글꼴이 없으면 출력할 수 없습니다. 입력 경로나 글꼴 파일을 실행하지 않습니다.'));
   element.append(button('이미지 기술 검사',()=>controller.preview('thumbnailInspect',{asset_id:controller.getState().inputs.asset_id}),s.busy||!context?.contentId),button('고정 템플릿 PNG 미리보기',()=>{const i=controller.getState().inputs;return controller.preview('thumbnailRender',{asset_id:i.asset_id||null,preset_id:i.preset_id,title:i.title});},s.busy||!context?.contentId));
   for(const kind of ['thumbnailInspect','thumbnailRender'])renderReport(kind,s.reports[kind]);
  }
  if(all||section==='schedule'||section==='editor'){
   field('delivery_id','배포 ID');element.append(button('예약 상태 확인',()=>controller.preview('schedule',{delivery_id:controller.getState().inputs.delivery_id}),s.busy));renderReport('schedule',s.reports.schedule);
  }
  if(all||section==='analytics'){
   const file=node('input');file.type='file';file.accept='.csv,text/csv';file.name='toolkit_csv_file';file.setAttribute('aria-label','CSV 관측 파일');file.addEventListener('change',()=>readCsvFile(file));
   if(fileReadError?.generation===s.generation)element.append(node('p',fileReadError.message));
   const csv=node('textarea');csv.name='toolkit_csv_text';csv.value=s.inputs.csv_text;csv.setAttribute('aria-label','CSV 관측 텍스트');csv.addEventListener('input',()=>controller.updateInput('csv_text',csv.value));
   element.append(node('label','CSV 관측 가져오기 (승인·게시 검증과 별도)'),node('p','개인 또는 학과 조회 범위를 먼저 선택하세요. 값 0·오류·미지원·미배정은 구분해 보존합니다.'),file,csv,button('CSV 미리보기',()=>controller.preview('csv'),s.busy||context?.account==='all'),button('CSV 관측 가져오기',()=>controller.preview('csvImport'),s.busy||context?.account==='all'||!writable||s.reports.csv?.can_import===false||!s.reports.csv?.preview_digest));
   if(s.reports.csv){element.append(node('p',`CSV 미리보기: ${s.reports.csv.status||'확인 가능'}`));for(const row of s.reports.csv.rows||[]){const values=Object.entries(row.values||{}).map(([name,value])=>`${name}: ${scalar(value)}`).join(', ')||'값 미제공';element.append(node('p',`${scalar(row.status)} · ${values} · 대상 ${scalar(row.target_id)} · ${(row.uncertainties||[]).map(v=>({owner_unassigned:'소유 미배정',destination_unassigned:'대상 미배정',manual_source:'수동 CSV 근거'})[v]||v).join(', ')}`));}for(const warning of s.reports.csv.warnings||[])element.append(node('p',`행 ${scalar(warning.row)}: ${scalar(warning.reason)}`));for(const error of s.reports.csv.errors||[])element.append(node('p',typeof error==='string'?error:JSON.stringify(error)));}
   if(s.reports.csvImport)element.append(node('p',`CSV 응답: ${s.reports.csvImport.status||'관측 처리 응답 수신'} · 추가 ${scalar(s.reports.csvImport.imported)} · 중복 ${scalar(s.reports.csvImport.unchanged)}`));
  }
  return element;
 }
 function refreshControls(options={}){
  current={...current,...options};if(options.context)controller.setContext(options.context);
  element.querySelectorAll?.('[data-toolkit-stage]').forEach(n=>n.disabled=!current.writable||controller.getState().context.editorDirty!==false||controller.isBusy());
 }
 return {render,refreshControls,element,isBusy:()=>controller.isBusy(),isDirty:()=>controller.isDirty()};
}
