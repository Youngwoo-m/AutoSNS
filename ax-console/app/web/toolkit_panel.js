export function createToolkitPanel({controller,document}) {
 const element=document.createElement('section');
 let current={},fileSelection=0,fileReadError=null;

 function renderSchedule(report) {
  const scalar=value=>typeof value==='string'||typeof value==='number'?String(value):'미확인';
  for(const [key,label] of [['delivery_id','배포 ID'],['state','예약 상태'],['target_id','대상 ID'],['remote_id','원격 ID'],['scheduled_at','예약 시각']]) {
   element.append(node('p',`${label}: ${scalar(report[key])}`));
  }
  const enabled=report.execution_enabled;
  element.append(node('p',`실행: ${enabled===true?'활성':enabled===false?'비활성':'미확인'}`));
  const reasons=Array.isArray(report.reason_codes)?report.reason_codes.filter(reason=>typeof reason==='string'):[];
  element.append(node('p',`사유: ${reasons.length?reasons.join(', '):'제공된 사유 없음'}`));
 }

 async function readCsvFile(file) {
  const selection=++fileSelection;
  const chosen=file.files?.[0];
  if(!chosen)return;
  const before=controller.getState();
  const isCurrent=()=>selection===fileSelection
   &&controller.getState().context.account===before.context.account
   &&controller.getState().generation===before.generation;
  fileReadError=null;
  try {
   const text=await chosen.text();
   if(!isCurrent())return;
   controller.updateInput('csv_text',text);
  } catch {
   if(!isCurrent())return;
   fileReadError={generation:before.generation,message:'CSV 파일을 읽지 못했습니다. 기존 입력은 보존됩니다.'};
  }
  render(current);
 }
 function node(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
 function button(text,action,disabled=false){const n=node('button',text);n.type='button';n.disabled=disabled;n.addEventListener('click',async e=>{e.preventDefault();if(n.disabled||controller.isBusy())return;n.disabled=true;try{await action();}finally{render(current);}});return n;}
 function render(options={}){current=options;const {context,writable=false}=options;if(context)controller.setContext(context);const s=controller.getState();element.replaceChildren();element.append(node('h3','로컬 SNS 도구'),node('p','추가 유료 API·credit 자동 사용 없음 · 실행 정책은 서버에서 확인합니다.'));
 const capability=s.reports.capabilities;
 element.append(node('p',`기능: ${capability?.status||'미확인'} · 비용: ${capability?.cost_status||'미확인'} · 권한: ${capability?.permission_status||'미확인'}`));
 element.append(button('도구 상태 확인',()=>controller.preview('capabilities'),s.busy));
 if(s.error)element.append(node('p',`${s.error} 입력과 요청키는 보존됩니다.`));
 const keywords=node('input');keywords.name='toolkit_keywords';keywords.value=s.inputs.keywords;keywords.addEventListener('input',()=>controller.updateInput('keywords',keywords.value));element.append(node('label','검색어 (쉼표로 구분)'),keywords);
 element.append(button('제목·본문 후보 미리보기',()=>controller.preview('packaging'),s.busy||!context?.contentId),button('저장 근거로 조사',()=>controller.preview('research'),s.busy));
 for(const [name,label] of [['asset_id','첨부 자산 ID'],['preset_id','고정 템플릿 ID'],['title','썸네일 제목'],['delivery_id','배포 ID']]){const field=node('input');field.name=`toolkit_${name}`;field.value=s.inputs[name]||'';field.addEventListener('input',()=>controller.updateInput(name,field.value));element.append(node('label',label),field);}
 element.append(button('이미지 기술 검사',()=>controller.preview('thumbnailInspect',{asset_id:controller.getState().inputs.asset_id}),s.busy||!context?.contentId),button('고정 템플릿 PNG 미리보기',()=>{const i=controller.getState().inputs;return controller.preview('thumbnailRender',{asset_id:i.asset_id||null,preset_id:i.preset_id,title:i.title});},s.busy||!context?.contentId),button('예약 상태 확인',()=>controller.preview('schedule',{delivery_id:controller.getState().inputs.delivery_id}),s.busy));
 for(const kind of ['packaging','research','thumbnailInspect','thumbnailRender','schedule']){const report=s.reports[kind];if(!report)continue;if(kind==='schedule')renderSchedule(report);if(['unavailable','blocked'].includes(report.status))element.append(node('p',`사용 불가: ${report.reason||report.status}`));for(const candidate of report.candidates||[]){element.append(node('p',candidate.title||candidate.text||''));element.append(button('초안에 반영',()=>{const patch=controller.stageCandidate(candidate.id??candidate.candidate_id,context);element.dispatchEvent?.(new CustomEvent('toolkit-stage',{detail:patch}));return patch;},!writable||context?.editorDirty!==false||s.busy));for(const variant of candidate.variants||[]){if(typeof variant.text!=='string'||typeof variant.id!=='string')continue;element.append(node('p',variant.text),button('선택한 본문을 초안에 반영',()=>{const patch=controller.stageCandidate(candidate.id??candidate.candidate_id,{...context,variantId:variant.id});element.dispatchEvent?.(new CustomEvent('toolkit-stage',{detail:patch}));return patch;},!writable||context?.editorDirty!==false||s.busy));}}for(const item of report.items||[]){if(typeof item==='string')element.append(node('p',item));else if(typeof item.title==='string')element.append(node('p',item.title));}if(typeof report.png_base64==='string'&&/^[A-Za-z0-9+/=]+$/.test(report.png_base64)){const link=node('a','PNG 다운로드');link.href=`data:image/png;base64,${report.png_base64}`;link.download='toolkit-preview.png';element.append(link,node('p','원고 저장은 기존 첨부 기능을 사용하세요. 기술 검사는 독립 검토 통과와 별도입니다.'));}}
 element.append(node('p','검색량·경쟁도·예측 CTR: unavailable (공개·저장 근거 부족)'));
 const file=node('input');file.type='file';file.accept='.csv,text/csv';file.name='toolkit_csv_file';file.addEventListener('change',()=>readCsvFile(file));
 if(fileReadError?.generation===s.generation)element.append(node('p',fileReadError.message));
 const csv=node('textarea');csv.name='toolkit_csv_text';csv.value=s.inputs.csv_text;csv.addEventListener('input',()=>controller.updateInput('csv_text',csv.value));element.append(node('label','CSV 관측 가져오기 (승인·게시 검증과 별도)'),file,csv,button('CSV 미리보기',()=>controller.preview('csv'),s.busy),button('CSV 관측 가져오기',()=>controller.preview('csvImport'),s.busy||!writable||!s.reports.csv?.preview_digest));
 if(s.reports.csv)element.append(node('p',`CSV 미리보기: ${s.reports.csv.status||'확인 가능'}`));if(s.reports.csvImport)element.append(node('p',`CSV 응답: ${s.reports.csvImport.status||'관측 처리 응답 수신'}`));return element;
 }
 return {render,element,isBusy:()=>controller.isBusy(),isDirty:()=>controller.isDirty()};
}
