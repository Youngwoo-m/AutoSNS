export function createToolkitPanel({controller,document}) {
 const element=document.createElement('section');
 element.className='toolkit-panel';
 let current={},fileSelection=0,fileReadError=null,actionError='';
 const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
 const labels={personal:'개인',dept:'학과',implemented:'구현됨',candidate:'연결 후보',no_additional_cost:'추가 비용 없음',paid:'유료',credits:'크레딧 사용',unknown:'미확인',unavailable:'사용 불가',blocked:'차단',completed:'완료',ok:'정상',error:'오류',available:'근거 있음',legacy_reported:'수동 관측 · 게시 검증 아님',lifetime:'누적',interval:'기간',views:'조회수',likes:'좋아요',comments:'댓글',shares:'공유',saves:'저장',clicks:'클릭',impressions:'노출',owner_unassigned:'소유 미배정',destination_unassigned:'대상 미배정',manual_source:'수동 CSV 근거',decode_failed:'이미지를 해석할 수 없습니다',keyword_missing:'제목에 없는 검색어가 있습니다',connection_target_unconfirmed:'연결 대상 미확인',execution_disabled:'실제 실행 비활성',needs_manual_review:'사람 확인 필요',renderer_unavailable:'이미지 출력 환경 미준비',font_validation_failed:'등록 글꼴 확인 불가',asset_reuse_unauthorized:'이미지 재사용 승인 없음',sample_below_three:'표본 3건 미만',incompatible_metric_definition:'지표 정의가 다름'};
 Object.assign(labels,{decoder_unavailable:'이미지 해석 환경 미준비',invalid_bytes:'이미지 데이터 오류',byte_limit:'이미지 용량 한도 초과',unsupported_media_type:'지원하지 않는 이미지 형식',hash_mismatch:'파일 해시 불일치',media_type_mismatch:'이미지 형식 불일치',dimension_limit:'이미지 크기 한도 초과',animated_image_unsupported:'움직이는 이미지 미지원',text_overflow:'문구가 안전 영역을 넘습니다',toolkit_disabled:'로컬 도구 비활성',account_mismatch:'계정 간 등록 경로 확인 필요',destination_variant_missing:'대상 변환문 없음',connection_context_mismatch:'등록 연결과 배포 대상 불일치',cost_not_zero:'추가 비용 없는 실행으로 확인되지 않음',invalid_render_output:'이미지 출력 검증 실패',render_failed:'이미지 출력 실패'});
 const actions={'local.packaging.preview':'제목·태그 후보','local.research.preview':'저장 근거 조사','local.thumbnail.inspect':'이미지 기술 검사','local.thumbnail.render':'고정 썸네일 출력','local.metrics.csv.preview':'성과 CSV 미리보기','local.metrics.csv.import':'성과 CSV 가져오기','local.schedule.inspect':'예약 상태 조회','metricool.publish':'Metricool 발행','vidiq.credit.analyze':'vidIQ 분석','mcp.read.assist':'연결 도구 조회 보조'};
 const label=value=>labels[value]||scalar(value);
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
 function selectField(name,caption,options,{empty='선택하세요',defaultValue=''}={}) {
  const input=node('select');input.name=`toolkit_${name}`;input.id=`toolkit-${current.section||'all'}-${name}`;
  const title=node('label',caption);title.htmlFor=input.id;
  if(empty!==null){const option=node('option',empty);option.value='';input.append(option);}
  for(const [value,text] of options){const option=node('option',text);option.value=String(value);input.append(option);}
  const stored=controller.getState().inputs[name];input.value=stored??defaultValue;

  input.addEventListener('change',()=>{
   controller.updateInput(name,input.value);
   if(name==='variant_index'){render(current);return;}
   if(name==='connection_id') {
    current={...current,context:{...controller.getState().context,connectionId:input.value||null}};
    controller.setContext(current.context);render(current);
   }else refreshControls();
  });
  element.append(title,input);return input;
 }
 function selectedVariantIndex() {
  const s=controller.getState(),selected=s.inputs.variant_index,report=s.reports.packaging;
  if(selected===undefined||selected===null||selected==='')return null;
  const index=Number(selected),variant=s.context.variants?.[index];
  return Number.isInteger(index)&&index>=0&&variant&&variant.destination_account_id===report?.destination_account_id&&variant.platform===report?.platform?index:null;
 }
 function canStage(withTags=false) {
  return current.writable&&controller.getState().context.editorDirty===false&&!controller.isBusy()&&(!withTags||selectedVariantIndex()!==null);
 }
 function canInspectImage() {
  const s=controller.getState();
  return !s.busy&&!!s.context.contentId&&(s.context.assets||[]).some(a=>a.id===s.inputs.asset_id&&['image/png','image/jpeg','image/webp'].includes(a.media_type));
 }
 function stageButton(label,id,withTags=false){
  const n=button(label,()=>{
   const context=controller.getState().context;
   if(!canStage(withTags))return;
   const variantIndex=withTags?selectedVariantIndex():undefined;
   const patch=controller.stageCandidate(id,{...context,variantIndex});
   element.dispatchEvent?.(new CustomEvent('toolkit-stage',{detail:patch}));
  },!canStage(withTags));
  n.setAttribute('data-toolkit-stage',withTags?'tags':'title');return n;
 }
 function renderSchedule(report) {
  for(const [key,caption] of [['delivery_id','배포 ID'],['state','예약 상태'],['target_id','대상 ID'],['remote_id','원격 ID'],['scheduled_at','예약 시각']])element.append(node('p',`${caption}: ${key==='state'?label(report[key]):scalar(report[key])}`));
  element.append(node('p',`실행: ${report.execution_enabled===true?'활성':report.execution_enabled===false?'비활성':'미확인'}`));
  const reasons=Array.isArray(report.reason_codes)?report.reason_codes.filter(reason=>typeof reason==='string'):[];
  element.append(node('p',`사유: ${reasons.length?reasons.map(label).join(', '):'제공된 사유 없음'}`));
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
 function detail(caption,value){element.append(node('p',`${caption}: ${scalar(value)}`));}
 function findings(items=[]) {
  for(const item of items)element.append(node('p',typeof item==='string'?label(item):item.message||label(item.code)||'확인 필요'));
 }
 function evidence(refs=[]) {
  for(const ref of refs) {
   if(ref.url)detail('출처',ref.url);
   if(ref.observation_id)detail('관측 근거',ref.observation_id);
   if(ref.content_id)detail('원본 근거',`${ref.content_id} · 버전 ${scalar(ref.content_revision)}`);
  }
 }
 function metricDetails(row) {
  detail('대상',`${label(row.destination_account_id)} · ${scalar(row.platform)} · ${scalar(row.target_id)}`);
  detail('지표 정의',row.definition_id);
  detail('집계 기준',label(row.basis));
  detail('기간',typeof row.period==='object'?JSON.stringify(row.period):row.period);
  detail('지표 값 (단위는 정의 기준)',Object.entries(row.values||{}).map(([key,value])=>`${label(key)}: ${scalar(value)}`).join(', ')||'미수집');
 }
 function renderReport(kind,report){
  if(!report)return;
  detail('처리 상태',label(report.status));
  findings(report.reason_codes||[report.reason_code||report.reason].filter(Boolean));
  if(kind==='schedule')renderSchedule(report);
  if(kind==='packaging') {
   detail('배포 대상',`${label(report.destination_account_id)} · ${scalar(report.platform)} · ${scalar(report.target_id)}`);
   findings(report.uncertainties);findings(report.findings);evidence(report.evidence_refs);
   const context=controller.getState().context;
   const variants=(context.variants||[]).map((variant,index)=>({variant,index})).filter(({variant})=>variant.destination_account_id===report.destination_account_id&&variant.platform===report.platform);
   selectField('variant_index','태그를 붙일 대상 변환문',variants.map(({variant,index})=>[index,`${label(variant.destination_account_id)} · ${variant.platform} · 변환문 ${index+1}: ${variant.text.slice(0,60)}`]));
   for(const [index,candidate] of (report.candidates||[]).entries()) {
    element.append(node('h4',`후보 ${index+1}`),node('p',candidate.title||''),node('p',(candidate.hashtags||[]).join(' ')));
    findings(candidate.reasons);
    element.append(stageButton(`후보 ${index+1} 제목을 초안에 반영`,candidate.id));
    element.append(stageButton(`후보 ${index+1} 제목·태그를 선택 변환문에 반영`,candidate.id,true));
   }
  }
  if(kind==='research') {
   for(const group of report.groups||[]) {
    detail('원본 소유',group.owner_account_ids?.map(label).join(', ')||'미확인');metricDetails(group);detail('표본 수',group.sample_count);detail('추천 근거',label(group.recommendation_status));
    for(const recommendation of group.recommendations||[])detail('검토 방향',recommendation.reason);
   }
   if(!(report.groups||[]).length)detail('저장 근거','조회 가능한 검증 성과가 없습니다.');
   for(const missing of report.missing||[]){detail('미수집·누락',label(missing.status));findings(missing.uncertainties);}
   evidence(report.evidence_refs);
  }
  if(kind==='thumbnailInspect'||kind==='thumbnailRender') {
   if(report.width!==undefined||report.height!==undefined)detail('이미지 크기',`${scalar(report.width)} × ${scalar(report.height)} px`);
   if(report.sha256)detail('파일 해시',report.sha256);
   findings(report.findings);
  }
  if(typeof report.png_base64==='string'&&/^[A-Za-z0-9+/=]+$/.test(report.png_base64)){
   const link=node('a','PNG 다운로드');link.href=`data:image/png;base64,${report.png_base64}`;link.download='toolkit-preview.png';
   element.append(link,node('p','원고 저장은 기존 첨부 기능을 사용하세요. 기술 검사는 독립 검토 통과와 별도입니다.'));
  }
 }
 function renderCsv(report) {
  detail('CSV 미리보기',label(report.status));
  for(const [index,row] of (report.rows||[]).entries()) {
   element.append(node('h4',`CSV 데이터 행 ${index+1}`));detail('출처 상태',label(row.status));
   detail('원본 소유',label(row.owner_account_id));detail('게시 ID',row.remote_id);detail('제목',row.title);
   metricDetails(row);detail('관측 시각 (시간대 포함)',row.observed_at);detail('수집 시각',row.collected_at);
   findings(row.uncertainties);
  }
  for(const warning of report.warnings||[])detail(`CSV 행 ${scalar(warning.row)}`,label(warning.reason));
  findings(report.errors);
 }

 function render(options={}){
  current=options;const {context,writable=false,section='all'}=options;if(context)controller.setContext(context);
  const s=controller.getState(),all=section==='all';element.replaceChildren();
  element.append(node('h3','로컬 SNS 도구'),node('p','추가 유료 API·크레딧 자동 사용 없음 · 실행 정책은 서버에서 확인합니다.'));
  const capability=s.reports.capabilities;
  element.append(node('p',`로컬 정책: ${capability?capability.toolkit_enabled?'활성':'비활성':'미확인'} · 외부 실행: 미지원 · 읽기·쓰기 권한: 미확인`));
  element.append(button('도구 상태 확인',()=>controller.preview('capabilities'),s.busy));
  for(const item of capability?.items||[])element.append(node('p',`${actions[item.action_id]||'연결 도구'} · ${label(item.implementation_status)} · ${label(item.cost_kind)}`));
  for(const connection of capability?.connections||[])element.append(node('p',`${label(connection.account_id)} · ${scalar(connection.platform)} · ${connection.target_label||scalar(connection.target_id)} · 인증 ${label(connection.auth_status)} · 읽기/쓰기 권한 미확인`));
  if(s.error)element.append(node('p',`${s.error} 입력과 요청키는 보존됩니다.`));if(actionError)element.append(node('p',actionError));
  if(all||section==='editor'||section==='planning'){
   field('keywords','검색어 (쉼표로 구분)');
   if(all||section==='editor'){
    selectField('connection_id','제목·태그 적용 채널',(capability?.connections||[]).map(c=>[c.connection_id,`${label(c.account_id)} · ${scalar(c.platform)} · ${c.target_label||scalar(c.target_id)}`]));
    element.append(button('제목·태그 후보 미리보기',()=>controller.preview('packaging'),s.busy||!context?.contentId||!controller.getState().context.connectionId));
   }
   element.append(button('저장 근거로 조사',()=>controller.preview('research'),s.busy));
   for(const kind of ['packaging','research'])renderReport(kind,s.reports[kind]);
   element.append(node('p','검색량·경쟁도·예측 CTR: 제공 불가 (공개·저장 근거 부족)'));
  }
  if(all||section==='editor'){
   selectField('asset_id','첨부 이미지',(context?.assets||[]).filter(a=>['image/png','image/jpeg','image/webp'].includes(a.media_type)).map(a=>[a.id,a.filename||'첨부 이미지']),{empty:'배경 이미지 없이 만들기'});
   selectField('preset_id','썸네일 형태',[['landscape.v1','가로 1280 × 720'],['portrait.v1','세로 1080 × 1920']],{empty:null,defaultValue:'landscape.v1'});field('title','썸네일 제목');
   element.append(node('p','고정 템플릿·서버 등록 한글 글꼴이 없으면 출력할 수 없습니다. 입력 경로나 글꼴 파일을 실행하지 않습니다.'));
   const inspectButton=button('이미지 기술 검사',()=>canInspectImage()?controller.preview('thumbnailInspect',{asset_id:controller.getState().inputs.asset_id}):null,!canInspectImage());
   inspectButton.setAttribute('data-toolkit-inspect','');
   element.append(inspectButton,button('고정 템플릿 PNG 미리보기',()=>{const i=controller.getState().inputs;return controller.preview('thumbnailRender',{asset_id:i.asset_id||null,preset_id:i.preset_id,title:i.title});},s.busy||!context?.contentId));
   for(const kind of ['thumbnailInspect','thumbnailRender'])renderReport(kind,s.reports[kind]);
  }
  if(all||section==='schedule'||section==='editor'){
   selectField('delivery_id','조회할 배포',(context?.deliveries||[]).map(d=>[d.id||d.delivery_id,`${d.platform||'채널'} · ${d.target_label||d.target_id||'대상 미확인'} · ${label(d.state||d.status)}`]));element.append(button('예약 상태 확인',()=>controller.preview('schedule',{delivery_id:controller.getState().inputs.delivery_id}),s.busy));renderReport('schedule',s.reports.schedule);
  }
  if(all||section==='analytics'){
   const file=node('input');file.type='file';file.accept='.csv,text/csv';file.name='toolkit_csv_file';file.setAttribute('aria-label','CSV 관측 파일');file.addEventListener('change',()=>readCsvFile(file));
   if(fileReadError?.generation===s.generation)element.append(node('p',fileReadError.message));
   const csv=node('textarea');csv.name='toolkit_csv_text';csv.value=s.inputs.csv_text;csv.setAttribute('aria-label','CSV 관측 텍스트');csv.addEventListener('input',()=>controller.updateInput('csv_text',csv.value));
   element.append(node('label','CSV 관측 가져오기 (승인·게시 검증과 별도)'),node('p','개인 또는 학과 조회 범위를 먼저 선택하세요. 값 0·오류·미지원·미배정은 구분해 보존합니다.'),file,csv,button('CSV 미리보기',()=>controller.preview('csv'),s.busy||context?.account==='all'),button('CSV 관측 가져오기',()=>controller.preview('csvImport'),s.busy||context?.account==='all'||!writable||s.reports.csv?.can_import===false||!s.reports.csv?.preview_digest));
   if(s.reports.csv)renderCsv(s.reports.csv);
   if(s.reports.csvImport)element.append(node('p',`CSV 응답: ${label(s.reports.csvImport.status)||'관측 처리 응답 수신'} · 추가 ${scalar(s.reports.csvImport.imported)} · 중복 ${scalar(s.reports.csvImport.unchanged)}`));
  }
  return element;
 }
 function refreshControls(options={}){
  const previousDeliveries=JSON.stringify(controller.getState().context.deliveries||[]);
  current={...current,...options};if(options.context)controller.setContext(options.context);
  if(previousDeliveries!==JSON.stringify(options.context?.deliveries||[])){render(current);return;}
  element.querySelectorAll?.('[data-toolkit-stage]').forEach(n=>n.disabled=!canStage(n.getAttribute('data-toolkit-stage')==='tags'));
  element.querySelectorAll?.('[data-toolkit-inspect]').forEach(n=>n.disabled=!canInspectImage());
 }
 return {render,refreshControls,element,isBusy:()=>controller.isBusy(),isDirty:()=>controller.isDirty()};
}
