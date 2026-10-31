import {createExecutionWorkspace} from './execution_controller.js';
import {createMetricsApi,createMetricsPanel} from './metrics_panel.js';
import {createOperationsApi,createOperationsPanel} from './operations_panel.js';
import {createContentEditor} from './content_editor.js';
import {createIntegrationSettings,confirmSettingsNavigation} from './integration_settings.js';
import {createSnapshotLoader,contentApi,refreshWorkspace,createExecutionApi} from './api.js';
import {accountLabel,kindLabel,statusLabel,scheduleLabel,safeUrl,filterContents,aggregate,dayKey,formatDateTime,weekDays,integrationSummary} from './view_helpers.js';

const $=selector=>document.querySelector(selector);
const h=(tag,attrs={},...children)=>{
  const element=document.createElement(tag);
  for(const [key,value] of Object.entries(attrs)) {
    if(value===undefined||value===null) continue;
    if(key.startsWith('on')) element.addEventListener(key.slice(2),value);
    else if(key==='class') element.className=value;
    else if(key==='disabled') element.disabled=Boolean(value);
    else element.setAttribute(key,String(value));
  }
  for(const child of children.flat(Infinity)) if(child!==null&&child!==undefined) element.append(child instanceof Node?child:document.createTextNode(String(child)));
  return element;
};
const text=value=>value===null||value===undefined||value===''?'미확인':String(value);
const muted=value=>h('p',{class:'sub'},value);
const empty=(title,reason)=>h('div',{class:'empty'},h('strong',{},title),h('p',{},reason));
const unsupported='읽기 전용 단계에서 이 기능은 아직 지원하지 않습니다.';
const disabled=label=>h('button',{class:'btn btn-small',disabled:true,title:unsupported},label);
const account=id=>h('span',{class:`label ${['personal','dept'].includes(id)?id:'neutral'}`},accountLabel(id,state.snapshot?.accounts));
const badge=status=>h('span',{class:`state ${['failed','review','verified','scheduled','paused','drafting'].includes(status)?status:''}`},statusLabel(status));
const panel=(title,...children)=>h('section',{class:'panel'},h('div',{class:'panel-head'},h('h2',{},title)),...children);
const table=(headers,rows)=>h('div',{class:'table-scroll'},h('table',{},h('thead',{},h('tr',{},headers.map(label=>h('th',{scope:'col'},label)))),h('tbody',{},rows)));
const td=(...children)=>h('td',{},...children);
const tabs=(label,items,selected,onSelect)=>h('div',{class:'tabs','aria-label':label,role:'group'},items.map(([id,title])=>h('button',{class:id===selected?'active':'','aria-pressed':id===selected,onclick:()=>onSelect(id)},title)));
const contentButton=(content,label)=>h('button',{class:'title-button','data-content':content.id,onclick:()=>openContent(content.id)},label||text(content.title));
const titleFor=id=>state.snapshot?.contents.find(c=>c.id===id);
let state={account:'all',snapshot:null,phase:'idle',error:null};
let view='today',weekOffset=0,calendarMode='week',crosspostTab='rules',issueTab='actions',detailTab='overview',detailId=null,lastFocus=null;
const filters={query:'',kind:'all',series:'all',status:'all',owner:'all'};
const views={
  today:['운영 개요','오늘 운영','오늘 일정과 기록을 확인하고 필요한 조치를 찾습니다.'],
  planning:['기획에서 제작까지','콘텐츠 기획','기획 원본과 대상별 변환본을 저장하고 단계별로 확인합니다.'],
  library:['원본과 배포 기록','콘텐츠 보관함','원본의 소유 계정과 채널별 게시 대상을 나누어 확인합니다.'],
  calendar:['채널별 예정 시각','예약 캘린더','로컬 계획과 원격 예약 기록을 구분합니다. 현재 플랫폼 예약 재조회는 지원하지 않습니다.'],
  crosspost:['원본을 채널에 맞게','교차 발행','기존 원본 소유 계정·게시 대상·운영 조건의 조회 결과입니다.'],
  accounts:['계정과 게시 대상','채널·계정','설정 등록, 인증 확인, 운영 활성 여부를 별도로 표시합니다.'],
  analytics:['관측과 출처 기준','성과','검증 배포 관측과 과거 보고 자료를 구분하고 근거를 별도 기획제안으로 저장합니다.'],
  issues:['필요한 예외에 집중','문제·복구','조치 필요 기록과 대상별 배포 기록을 확인합니다.']
};
const writable=()=>state.snapshot?.workspace_writable===true;
let editorActive=false,integrationAccount=null;
const execution=createExecutionWorkspace({api:createExecutionApi(),contentApi,onChange:()=>renderStatus(),onOpenOutput:(id,revision)=>openEditor({id,revision,source:'managed'})});
const editor=createContentEditor({api:contentApi,writable,execution,onSaved:()=>loader.refresh()});
const integrationSettings=createIntegrationSettings({api:contentApi,onSaved:()=>{}});
const metrics=createMetricsPanel({api:createMetricsApi(),onChange:()=>{renderStatus();}});
const operations=createOperationsPanel({api:createOperationsApi(),execution,onChange:()=>{renderStatus();}});
function confirmLeave(){
  if(execution.isBusy()||operations.isBusy()||(editorActive&&editor.isBusy()))return false;
  const accepted=confirmSettingsNavigation(integrationSettings,message=>globalThis.confirm(message),(editorActive&&editor.hasUnsavedChanges())||operations.isDirty()||execution.isDirty());
  if(accepted&&operations.isDirty())operations.discard();return accepted;
}
function pageHead() {
  const [eyebrow,title,description]=views[view];
  return h('div',{class:'page-head'},h('div',{},h('div',{class:'eyebrow'},eyebrow),h('h1',{id:'page-title',tabindex:'-1'},title),muted(description)),h('div',{class:'actions'},(['today','planning','library'].includes(view)&&writable())?h('button',{class:'btn btn-primary',onclick:()=>openEditor()},'새 기획'):disabled(view==='issues'?'비상 정지 미지원':view==='calendar'?'일정 변경 미지원':view==='crosspost'?'경로 수정 미지원':view==='accounts'?'연결 변경 미지원':'새 기획 미지원')));
}
function renderStatus() {
  const box=$('#load-status');box.classList.toggle('error',['error','unauthorized'].includes(state.phase));
  const stale=state.snapshot&&(!Number.isFinite(Date.parse(state.snapshot.generated_at))||Date.now()-Date.parse(state.snapshot.generated_at)>5*60*1000);
  let message=state.phase==='loading'?(state.snapshot?'갱신 중 · 이전 조회 자료를 표시합니다.':'자료를 불러오는 중입니다.'):
    state.phase==='unauthorized'?'로그인이 필요합니다. 인증 설정이 없는 환경에서는 기존 인증 설정 후 이용할 수 있습니다.':
    state.phase==='error'?(state.snapshot?'최신 조회 실패 · 이전 자료입니다.':'자료 조회 실패 · 표시할 자료가 없습니다.'):
    stale?'오래된 조회 자료입니다. 새로고침으로 현재 기록을 확인해 주세요.':writable()?'운영 자료 읽기 전용 · 새 관리 원본 저장 가능':'실제 자료 조회 완료 · 읽기 전용';
  $('.readonly-bar').textContent=writable()?'6A · 제작 접수·별도 발행 승인 · 실제 실행 기본 비활성 · 기존 STOP 읽기 전용':'6A · 실제 자료·성과 조회 · 기존 STOP 읽기 전용';
  const line=h('div',{class:'status-line'},h('span',{},message),state.snapshot?h('span',{},`마지막 갱신 ${formatDateTime(state.snapshot.generated_at)} · 한국시간`):null);
  if(state.phase==='unauthorized') line.append(h('a',{href:'/login',target:'_blank',rel:'noopener noreferrer'},'새 창에서 로그인'));
  box.replaceChildren(line);
  if(state.snapshot?.warnings.length) box.append(h('details',{},h('summary',{},`자료 누락·확인 안내 ${state.snapshot.warnings.length}건`),h('ul',{class:'warnings'},state.snapshot.warnings.map(w=>h('li',{},text(w))))));
  $('#refresh').textContent=state.phase==='loading'?'다시 갱신':'새로고침';
}
function render() {
  const preserveTitleFocus=document.activeElement?.id==='page-title';
  renderStatus();
  document.querySelectorAll('[data-scope]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.scope===state.account)));
  document.querySelectorAll('[data-view]').forEach(b=>{if(b.dataset.view===view)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');});
  $('#screen-root').setAttribute('aria-busy',String(state.phase==='loading'));
  const head=pageHead();
  if(!state.snapshot) {
    $('#screen-root').replaceChildren(head,empty(state.phase==='loading'?'조회 중':state.phase==='unauthorized'?'로그인 후 조회할 수 있습니다':'조회 자료가 없습니다',state.phase==='loading'?'선택한 관련 계정의 실제 기록을 불러옵니다.':state.phase==='unauthorized'?'상단 로그인 링크에서 인증 후 새로고침해 주세요.':'데이터를 불러오지 못했습니다. 새로고침으로 다시 시도해 주세요.'));
    if(preserveTitleFocus)$('#page-title')?.focus({preventScroll:true});
    return;
  }
  $('#screen-root').replaceChildren(head,renderers[view]());
  if(preserveTitleFocus)$('#page-title')?.focus({preventScroll:true});
}
function stats(items) {
  return h('div',{class:'stats'},items.map(([title,value,note])=>h('div',{class:'stat'},h('div',{class:'stat-top'},title),h('strong',{},value),h('p',{class:'stat-note'},note))));
}
function deliveryTable(deliveries) {
  if(!deliveries.length)return empty('배포 기록이 없습니다','선택한 계정과 관련된 채널별 배포 기록이 수집되지 않았습니다.');
  return table(['원본 콘텐츠','원본 소유','게시 대상','기록 상태','시각·확인'],deliveries.map(d=>{
    const c=titleFor(d.content_id);
    return h('tr',{},td(c?contentButton(c):'원본 미확인'),td(account(d.owner_account_id)),td(account(d.destination_account_id),h('div',{class:'cell-sub'},text(d.platform||d.channel)),h('div',{class:'cell-sub'},text(d.target_label))),td(badge(d.status)),td(h('div',{},scheduleLabel(d.schedule_kind)),h('div',{class:'cell-sub'},`예정 ${formatDateTime(d.scheduled_at)}`),h('div',{class:'cell-sub'},`확인 ${formatDateTime(d.checked_at)}`)));
  }));
}
function scheduleList(events) {
  if(!events.length)return empty('표시할 일정이 없습니다','정확한 예정 시각이 수집되지 않았거나, 선택한 기간에 해당하는 일정이 없습니다.');
  return table(['예정 시각 · 한국시간','원본 콘텐츠','원본 소유','게시 대상','예약 근거·상태'],events.map(e=>{
    const c=titleFor(e.content_id);
    return h('tr',{},td(formatDateTime(e.scheduled_at)),td(c?contentButton(c):text(e.title)),td(account(e.owner_account_id)),td(account(e.destination_account_id),h('div',{class:'cell-sub'},text(e.platform||e.channel))),td(badge(e.status),h('div',{class:'cell-sub'},scheduleLabel(e.schedule_kind||e.kind))));
  }));
}
function incidentRows(incidents) {
  return incidents.length?h('div',{class:'entry-list'},incidents.map(i=>h('article',{class:'record-row'},h('div',{class:'pill-row'},account(i.account_id),badge(i.status),h('span',{class:'cell-sub'},`심각도 ${text(i.severity)}`)),h('h3',{},text(i.title)),h('p',{},text(i.summary)),h('p',{},`마지막 기록 ${formatDateTime(i.last_at)}`),disabled('조치·재시도 미지원')))):empty('조치 기록이 없습니다','수집된 장애 기록이 없습니다. 자료 누락 안내가 있으면 함께 확인해 주세요.');
}
function renderToday() {
  const s=state.snapshot,a=aggregate(s),today=dayKey(new Date().toISOString());
  const events=s.schedule.filter(e=>dayKey(e.scheduled_at)===today).sort((a,b)=>String(a.scheduled_at).localeCompare(String(b.scheduled_at)));
  return h('div',{},operations.render('today'),stats([['관련 원본 콘텐츠',`${a.contents}건`,'콘텐츠 단위 · 오늘 생성 수와 다름'],['채널별 배포 기록',`${a.deliveries}건`,`${a.pending}건 예약·대기 · 전체 수집 기록`],['공개·내용 확인 완료',`${a.verified}건`,'명시적 검증 근거가 있는 배포만'],['검토·조치 필요',`${a.review} / ${a.incidents}건`,'원본 검토 / 열린 조치 기록']]),h('div',{class:'two-col'},panel(`오늘 일정 · ${today}`,scheduleList(events),h('div',{class:'mini-note'},'정확한 시각이 없는 자동 실행은 캘린더에서 별도로 표시합니다.')),h('div',{},panel('필요한 조치',incidentRows(s.incidents.filter(i=>!['closed','resolved'].includes(i.status)).slice(0,4))),panel('교차 발행 경로',h('div',{class:'panel-body'},muted(s.crosspost_catalog_status==='available'?`등록부 규칙 ${s.crossposts.length}개 · 자동 작업 관측 ${(s.legacy_crosspost_observations||[]).length}개 · 출처별 조회`:`자동 작업 관측 ${(s.crossposts||[]).length}개 · 등록부 조회 상태 미확인`),h('button',{class:'btn btn-small',onclick:()=>setView('crosspost')},'교차 발행 보기'))))));
}
function filterControls() {
  const s=state.snapshot;
  function selectField(title,key,options) {
    const id=`filter-${key}`;const input=h('select',{id,onchange:e=>{filters[key]=e.target.value;renderContentResults();}},options.map(([value,label])=>h('option',{value},label)));input.value=filters[key];
    return h('label',{class:'filter-field',for:id},title,input);
  }
  const input=h('input',{id:'content-search',type:'search',placeholder:'제목·요약·채널 검색',value:filters.query,oninput:e=>{filters.query=e.target.value;renderContentResults();}});
  const series=[...new Set(s.contents.map(c=>c.series).filter(Boolean))].sort();
  if(filters.series!=='all'&&filters.series!=='__none'&&!series.includes(filters.series))filters.series='all';
  return h('div',{class:'filters'},h('label',{class:'filter-field search-field',for:'content-search'},'콘텐츠 검색',input),selectField('원본 소유 계정','owner',[['all','모든 소유 계정'],['dept','학과'],['personal','개인']]),selectField('형식','kind',[['all','모든 형식'],['article','글'],['card','카드뉴스'],['short','숏츠'],['video','영상'],['unknown','미확인']]),selectField('시리즈','series',[['all','모든 시리즈'],...series.map(v=>[v,v]),['__none','시리즈 미확인']]),selectField('원본 또는 배포 상태','status',[['all','모든 상태'],...['idea','drafting','production','review','archived','scheduled','scheduled_recorded','queued','reported_published','verified','failed','paused','unknown'].map(v=>[v,statusLabel(v)])]));
}
function renderContentResults() {
  const target=$('#content-results');if(!target)return;
  const contents=filterContents(state.snapshot,{...filters,account:state.account});
  if(view==='library') {
    target.replaceChildren(panel(`원본 ${contents.length}건`,contents.length?table(['원본 콘텐츠','소유 계정','형식·시리즈','게시 대상','원본 상태','버전·최근 활동'],contents.map(c=>{
      const deliveries=state.snapshot.deliveries.filter(d=>d.content_id===c.id);
      return h('tr',{},td(contentButton(c),h('div',{class:'cell-sub'},c.source==='managed'?'새 관리 원본':'기존 자료 · 읽기 전용'),h('div',{class:'cell-sub'},c.summary?String(c.summary).slice(0,100):'요약 미수집')),td(account(c.owner_account_id)),td(kindLabel(c.kind),h('div',{class:'cell-sub'},c.series||'시리즈 미확인')),td(deliveries.length?deliveries.map(d=>h('div',{class:'pill-row'},account(d.destination_account_id),text(d.platform||d.channel))):h('div',{},(c.target_accounts||[]).map(id=>account(id)),h('div',{class:'cell-sub'},c.source==='managed'?`목표 채널: ${(c.channels||[]).join(', ')||'미지정'} · 배포 기록 없음`:'배포 기록 없음'))),td(badge(c.status)),td(h('div',{},`버전 ${text(c.revision)}`),h('div',{class:'cell-sub'},formatDateTime(c.updated_at))));
    })):empty('조건에 맞는 콘텐츠가 없습니다','검색어·소유 계정·형식·시리즈·상태 조건을 확인해 주세요.')));
  } else {
    const stages=[['idea','아이디어'],['drafting','조사·원고'],['production','제작'],['review','검토']];
    target.replaceChildren(h('div',{class:'kanban'},stages.map(([id,title])=>{
      const items=contents.filter(c=>c.status===id);
      return h('section',{class:'kanban-col'},h('div',{class:'kanban-title'},title,h('span',{},items.length)),items.length?items.map(c=>h('button',{class:'content-card','data-content':c.id,onclick:()=>openContent(c.id)},account(c.owner_account_id),h('h3',{},text(c.title)),h('p',{class:'summary-line'},`${kindLabel(c.kind)} · ${c.series||'시리즈 미확인'}`),h('div',{class:'card-foot'},`원본 버전 ${text(c.revision)}`))):empty('표시할 원본 없음',id==='production'?'조회 자료에 별도 제작 단계가 없어 추정하지 않습니다.':'현재 조건에서 이 단계의 원본이 없습니다.'));
    })),muted(`검색 결과 ${contents.length}건 중 기획·원고·제작·검토 단계만 보드에 표시합니다. 보관·예약·게시 기록 등 ${contents.filter(c=>!['idea','drafting','production','review'].includes(c.status)).length}건은 보관함에서 확인할 수 있습니다.`));
  }
}
function renderContents() {
  const root=h('div',{},filterControls(),muted('관련 계정 기준으로 조회합니다. 위의 원본 소유 계정 필터는 게시 대상 계정과 별개입니다.'),h('div',{id:'content-results'}));
  if(view==='planning') root.append(panel('AI 기획 제안 기록',state.snapshot.proposals.length?h('div',{class:'entry-list'},state.snapshot.proposals.map(p=>h('article',{class:'record-row'},h('div',{class:'pill-row'},account(p.owner_account_id),badge(p.status)),h('h3',{},text(p.title)),h('p',{},text(p.summary)),disabled('채택·반려 미지원')))):empty('수집된 제안이 없습니다','기획 제안 자료가 없으면 예시 제안을 만들지 않습니다.')));
  if(view==='planning') {
    const proposals=state.snapshot.metric_proposals||[];
    root.append(panel('성과 근거 기획제안 초안',muted('선택한 관측으로 직접 저장한 별도 제안입니다. 원고 작성은 상단 새 기획에서 시작합니다.'),proposals.length?h('div',{class:'entry-list'},proposals.map(p=>h('article',{class:'record-row'},h('div',{class:'pill-row'},account(p.account_id),h('span',{class:'state'},'초안')),h('h3',{},text(p.title)),h('p',{},text(p.note)),h('p',{},`근거 관측: ${(p.observation_ids||[]).join(', ')||'미확인'}`)))):empty('저장된 성과 근거 제안이 없습니다','성과 화면에서 관측을 선택해 기획제안을 저장할 수 있습니다.')));
  }
  queueMicrotask(renderContentResults);return root;
}
function renderCalendar() {
  const days=weekDays(new Date().toISOString(),weekOffset),s=state.snapshot;
  const inWeek=s.schedule.filter(e=>days.includes(dayKey(e.scheduled_at))).sort((a,b)=>String(a.scheduled_at).localeCompare(String(b.scheduled_at)));
  const unknown=s.schedule.filter(e=>!dayKey(e.scheduled_at));
  const button=(label,offset,aria)=>h('button',{class:'btn btn-small','aria-label':aria||label,onclick:()=>{weekOffset=offset;render();}},label);
  const controls=h('div',{class:'toolbar'},h('div',{class:'calendar-tools'},button('‹',weekOffset-1,'이전 주'),h('strong',{},`${days[0]} – ${days[6]}`),button('›',weekOffset+1,'다음 주'),button('이번 주',0)),tabs('일정 표시 방식',[['week','주간'],['list','목록']],calendarMode,id=>{calendarMode=id;render();}));
  const week=h('div',{class:'calendar-week'},days.map((day,i)=>h('section',{class:`calendar-day ${day===dayKey(new Date().toISOString())?'is-today':''}`},h('h3',{},`${['월','화','수','목','금','토','일'][i]} · ${day.slice(5)}`),inWeek.filter(e=>dayKey(e.scheduled_at)===day).map(e=>{
    const c=titleFor(e.content_id);
    return h('article',{class:`calendar-event ${e.destination_account_id==='personal'?'personal-event':''}`},h('b',{},formatDateTime(e.scheduled_at)),h('p',{},c?contentButton(c):text(e.title)),h('p',{},`원본 ${accountLabel(e.owner_account_id,s.accounts)} → 대상 ${accountLabel(e.destination_account_id,s.accounts)} · ${text(e.platform||e.channel)}`),h('p',{},statusLabel(e.status)),h('p',{},scheduleLabel(e.schedule_kind||e.kind)));
  }))));
  return h('div',{},controls,panel('배포별 예정 기록',calendarMode==='list'?scheduleList(inWeek):week,!inWeek.length?empty('이 주의 예정 기록이 없습니다','다른 주를 선택하거나 아래 시각 미확인 기록을 확인해 주세요.'):null,h('div',{class:'legend'},'한국시간 · 로컬 계획은 실행하지 않습니다. 원격 예약 기록은 현재 플랫폼 재조회 결과가 아닙니다. 일정 변경은 관리 원본 상세에서 미리보기 후 저장합니다.')),panel(`시각 미확인 기록 ${unknown.length}건`,unknown.length?scheduleList(unknown):empty('시각 미확인 기록 없음','수집된 일정 중 정확한 시각이 없는 기록은 없습니다.')));
}
function renderCrosspost() {
  const s=state.snapshot,deliveries=s.deliveries.filter(d=>d.owner_account_id!==d.destination_account_id);
  const available=s.crosspost_catalog_status==='available';
  const observations=Array.isArray(s.legacy_crosspost_observations)?s.legacy_crosspost_observations:(s.crossposts||[]);
  const rules=available?(s.crossposts||[]):[];
  const rows=crosspostTab==='observations'?observations:rules;
  const routeTable=rows.length?table(['원본 소유 계정·채널 → 게시 대상','시점·조건','설정·가동 상태','확인 근거'],rows.map(r=>h('tr',{},
    td(h('div',{class:'rule-route'},h('div',{},account(r.owner_account_id),h('div',{class:'cell-sub'},text(r.source_channel))),h('span',{'aria-hidden':'true'},'→'),h('div',{},account(r.destination_account_id),h('div',{class:'cell-sub'},text(r.destination_channel)))),h('div',{class:'cell-sub'},text(r.title))),
    td(r.condition||'조건 미수집'),
    td(h('div',{},r.enabled===true?'설정상 활성':r.enabled===false?'설정상 중지':'설정 활성 여부 미확인'),h('div',{class:'cell-sub'},r.activation_summary||'가동 상태 미확인')),
    td(r.evidence_summary||'자동 작업 관측 자료 · 등록 규칙과 별도 집계')))):empty(crosspostTab==='observations'?'자동 작업 관측 자료가 없습니다':available?'관련 등록 규칙이 없습니다':'등록 규칙을 조회할 수 없습니다',available?'현재 선택 계정의 조회 결과입니다.':'등록부 미수집·오류가 기존 경로의 해제를 뜻하지 않습니다. 자동 작업 관측 탭에서 기존 자료를 확인할 수 있습니다.');
  return h('div',{},tabs('교차 발행 보기',[['rules','등록 규칙'],['observations','자동 작업 관측'],['deliveries','배포 계획·기록']],crosspostTab,id=>{crosspostTab=id;render();}),
    h('div',{class:'inline-note'},`등록부 규칙 ${available?rules.length+'개':'조회 불가'} · 자동 작업 관측 ${observations.length}개 · 계정 간 배포 계획·기록 ${deliveries.length}건. 출처가 달라 합산하지 않습니다. 원본 또는 게시 대상이 선택 계정에 속한 경로입니다. 설정 활성은 실제 가동·인증 확인을 뜻하지 않습니다.`),
    crosspostTab==='deliveries'?panel('계정 간 배포 계획·기록',deliveryTable(deliveries)):panel(crosspostTab==='observations'?'자동 작업에서 관측한 경로':'등록부의 교차 발행 규칙',routeTable));
}
function renderIntegrations() {
  const integrations=Array.isArray(state.snapshot.integrations)?state.snapshot.integrations.filter(item=>item&&typeof item==='object'):[];
  return panel('연동·플러그인',
    h('div',{class:'panel-body'},
      muted('계정 조회 필터와 독립적인 도구 카탈로그입니다. Instagram·Threads·X·Tistory·Facebook 연동 후보와 지원 정보를 확인합니다.'),
      h('p',{class:'unsupported'},'카탈로그 등록·도구 제공은 설치나 로그인 확인, 웹 실행 가능을 뜻하지 않습니다. 별도 저장 공간을 설정하면 계정별 도구 선호만 저장할 수 있습니다.')),
    integrations.length?integrations.map(item=>{
      const summary=integrationSummary(item);
      return h('article',{class:'record-row'},
        h('div',{class:'pill-row'},h('span',{class:'label neutral'},summary.kind),h('strong',{},text(item.label))),
        h('div',{class:'pill-row integration-platforms'},summary.platforms.length?summary.platforms.map(label=>h('span',{class:'channel-chip'},label)):h('span',{class:'sub'},'플랫폼 정보 미수집')),
        h('p',{},item.description||'연동 설명 미수집'),
        h('dl',{class:'detail-kv'},
          h('dt',{},'도구 제공 여부'),h('dd',{},summary.availability),
          h('dt',{},'계정 연결'),h('dd',{},summary.connection),
          h('dt',{},'웹 실행'),h('dd',{},summary.execution)),
        disabled('외부 연결 실행 미지원'));
    }):empty('연동 카탈로그 미수집','플러그인·로컬 어댑터 목록이 아직 조회되지 않았습니다. 도구 미설치나 사용 불가로 단정하지 않습니다.'));
}
function renderAccounts() {
  const s=state.snapshot;
  const channels=s.channels.length?h('div',{class:'channel-card-grid'},['dept','personal'].filter(id=>state.account==='all'||state.account===id).map(id=>{
    const items=s.channels.filter(c=>c.account_id===id);
    return panel(`${accountLabel(id,s.accounts)} 채널`,items.length?items.map(c=>h('article',{class:'record-row'},h('div',{class:'pill-row'},account(c.account_id),h('strong',{},text(c.label))),h('dl',{class:'detail-kv'},h('dt',{},'플랫폼'),h('dd',{},text(c.platform)),h('dt',{},'실제 게시 대상'),h('dd',{},text(c.target_label)),h('dt',{},'설정 상태'),h('dd',{},text(c.configured_status)),h('dt',{},'인증 확인'),h('dd',{},'미확인 · 로그인 검사 미실행'),h('dt',{},'운영 활성'),h('dd',{},c.enabled===true?'설정상 활성':c.enabled===false?'설정상 중지':'미확인'),h('dt',{},'최근 게시 성공'),h('dd',{},'미수집'),h('dt',{},'기능 지원'),h('dd',{},'조회만 지원 · 연결·재인증 미지원')),disabled('로그인·연결 변경 미지원'))):empty('채널 자료 없음','이 계정의 채널 설정이 수집되지 않았습니다.'));
  })):panel('채널 설정',empty('수집된 채널 설정이 없습니다','설정 누락 안내를 확인해 주세요. 로그인 성공이나 채널 미등록으로 단정하지 않습니다.'));
  if(writable()){if(integrationAccount!==state.account){integrationAccount=state.account;integrationSettings.load(state.account);}}
  return h('div',{},execution.renderStatus(),operations.render('accounts'),writable()?integrationSettings.element:null,h('div',{class:'inline-note'},'인증 상태는 이번 단계에서 미확인입니다. 설정 등록과 최근 로그인·게시 성공은 서로 다른 정보입니다.'),renderIntegrations(),h('div',{class:'integration-channel-section'},channels));
}
function renderAnalytics() {
  return metrics.render({account:state.account,writable:writable()});
}
function renderIssues() {
  const s=state.snapshot;let content;
  if(issueTab==='actions') content=panel('확인이 필요한 기록',incidentRows(s.incidents));
  if(issueTab==='runs') content=panel('대상별 배포 기록',h('div',{class:'mini-note'},'위 서비스 패널에서 접수한 회차의 제작 결과·대상별 실행·미시작 후처리를 확인합니다. 아래는 수집된 배포 기록입니다.'),deliveryTable(s.deliveries));
  if(issueTab==='policy')content=panel('운영 정책',empty('관리 실행 정책은 위 운영 패널에서 확인','위 패널은 실행 정책과 원본 STOP 관측을 제공합니다. 예산·발행 한도의 상세 편집은 지원하지 않습니다.'),h('div',{class:'panel-body'},disabled('정책 저장 미지원')));
  if(issueTab==='settings')content=panel('시스템 설정',h('div',{class:'panel-body'},muted('실행 서비스 등록과 운영 정책은 위 패널에서 확인합니다. 활성화·정책 변경은 이 화면에서 지원하지 않습니다. 원격 인증은 명시적 대상 읽기 점검으로만 확인합니다.'),h('div',{class:'actions'},h('button',{class:'btn btn-small',onclick:()=>setView('accounts')},'채널 설정 기록 보기'),disabled('설정 변경 미지원'))));
  return h('div',{},execution.renderStatus(),operations.render('issues'),tabs('장애 및 설정 하위 메뉴',[['actions','조치 필요'],['runs','실행 기록'],['policy','운영 정책'],['settings','설정']],issueTab,id=>{issueTab=id;render();}),h('div',{class:'tab-content'},content));
}
const renderers={today:renderToday,planning:renderContents,library:renderContents,calendar:renderCalendar,crosspost:renderCrosspost,accounts:renderAccounts,analytics:renderAnalytics,issues:renderIssues};
function setView(id) {if(!views[id]||!confirmLeave())return;view=id;render();$('#page-title')?.focus({preventScroll:true});if(id==='planning')loader.refresh();}

function deliveryDetail(d) {
  const url=safeUrl(d.url);
  return h('article',{class:'detail-target'},h('div',{class:'pill-row'},account(d.destination_account_id),h('b',{},text(d.platform||d.channel)),badge(d.status)),h('dl',{class:'detail-kv'},h('dt',{},'원본 소유'),h('dd',{},account(d.owner_account_id)),h('dt',{},'게시 대상'),h('dd',{},text(d.target_label)),h('dt',{},'예정 시각'),h('dd',{},formatDateTime(d.scheduled_at)),h('dt',{},'예약 출처'),h('dd',{},scheduleLabel(d.schedule_kind)),h('dt',{},'마지막 확인'),h('dd',{},formatDateTime(d.checked_at)),h('dt',{},'확인 근거'),h('dd',{},d.evidence||'미수집 · 공개/내용 확인을 추정하지 않습니다.'),h('dt',{},'공개 주소'),h('dd',{},url?h('a',{class:'safe-link',href:url,target:'_blank',rel:'noopener noreferrer'},url):d.url?'표시할 수 없는 주소 · http/https만 지원':'주소 미수집')),h('p',{},d.owner_account_id!==d.destination_account_id?'계정 간 교차 발행 · 원본 소유권 유지':'원본 소유 계정의 채널 배포'),disabled('대상별 재시도 미지원'));
}
function renderDetail() {
  const c=titleFor(detailId);if(!c)return;
  const s=state.snapshot,deliveries=s.deliveries.filter(d=>d.content_id===c.id);
  $('#drawer-heading').replaceChildren(h('div',{class:'pill-row'},account(c.owner_account_id),badge(c.status)),h('h2',{id:'drawer-title'},text(c.title)),muted(`원본 소유 계정 ${accountLabel(c.owner_account_id,s.accounts)} · 버전 ${text(c.revision)}`));
  const tabbar=tabs('콘텐츠 상세 보기',[['overview','개요'],['manuscript','원고·변환본'],['media','이미지·영상'],['review','검토·출처'],['deliveries','채널별 배포'],['history','실행 이력']],detailTab,id=>{detailTab=id;renderDetail();$('#drawer-content button[aria-pressed="true"]')?.focus();});
  let body;
  if(detailTab==='overview')body=h('div',{},h('section',{class:'detail-section'},h('h3',{},'원본 개요'),h('p',{class:'article-preview'},c.summary||'요약이 수집되지 않았습니다.'),h('dl',{class:'detail-kv'},h('dt',{},'형식'),h('dd',{},kindLabel(c.kind)),h('dt',{},'시리즈'),h('dd',{},c.series||'미확인'),h('dt',{},'생성 시각'),h('dd',{},formatDateTime(c.created_at)),h('dt',{},'갱신 시각'),h('dd',{},formatDateTime(c.updated_at)))),h('section',{class:'detail-section'},h('h3',{},'채널별 게시 대상과 상태'),deliveries.length?deliveries.map(deliveryDetail):empty('배포 기록 없음','원본의 채널별 배포 기록이 수집되지 않았습니다.')));
  if(detailTab==='deliveries')body=h('section',{class:'detail-section'},h('h3',{},'채널별 배포'),muted('게시 대상은 원본 소유 계정과 별도입니다. 조회 계정과 관련된 배포만 표시할 수 있습니다.'),deliveries.length?deliveries.map(deliveryDetail):empty('배포 기록 없음','현재 조회 범위에서 연결된 배포 기록이 없습니다.'));
  if(detailTab==='manuscript')body=empty('전체 원문·채널 변환본 조회 미지원','현재 스냅샷은 요약과 원본 버전만 제공합니다. 원문 편집과 승인 버전 비교는 아직 지원하지 않습니다.');
  if(detailTab==='media')body=empty('미디어 자산 조회 미지원','이미지·영상 자산 정보가 조회 계약에 없습니다. 썸네일이나 파일의 존재를 추정하지 않습니다.');
  if(detailTab==='review')body=empty('검토·출처 자료 미수집','출처와 승인 이력을 조회 계약에서 제공하지 않습니다. 배포 확인 근거는 채널별 배포에서 확인할 수 있습니다.');
  if(detailTab==='history')body=h('section',{class:'detail-section'},h('h3',{},'배포 결과 기록'),muted('전체 실행 이력은 미지원입니다. 현재 스냅샷의 대상별 결과만 표시합니다.'),deliveries.length?deliveries.map(deliveryDetail):empty('실행 기록 미수집','이 원본에 연결된 배포 결과가 없습니다.'));
  $('#drawer-content').replaceChildren(tabbar,body,...(writable()?[h('div',{class:'detail-section'},muted('기존 자료는 직접 편집할 수 없습니다. 새 초안에는 수집 요약만 복사합니다.'),h('button',{class:'btn btn-small',onclick:()=>openEditor(c)},'수집 요약을 새 관리 초안으로 복사'))]:[]));
}
function openEditor(content=null){
  if(!writable()&&content?.source!=='managed')return;
  if(!confirmLeave())return;
  editorActive=true;lastFocus=document.activeElement;
  $('#drawer-heading').replaceChildren(h('h2',{id:'drawer-title'},content?.source==='managed'?'관리 원본 편집':'새 기획 저장'));
  $('#drawer-content').replaceChildren(editor.element);
  $('.drawer-foot span').textContent='관리 원본 · 계획 승인과 별도 발행 승인 구분 · 실행은 서버 정책에 따름';
  editor.open(content);if(!$('#detail-dialog').open)$('#detail-dialog').showModal();document.body.style.overflow='hidden';$('#drawer-close').focus();
}
function openContent(id) {
  if(!titleFor(id))return;
  if(titleFor(id).source==='managed'){openEditor(titleFor(id));return;}
  editorActive=false;$('.drawer-foot span').textContent='기존 자료 읽기 전용 · 원문 편집 및 배포 변경 미지원';
  detailId=id;detailTab='overview';lastFocus=document.activeElement;renderDetail();
  $('#detail-dialog').showModal();document.body.style.overflow='hidden';$('#drawer-close').focus();
}
function closeDetail(confirmed=false) {if(editorActive&&editor.isBusy())return false;if(confirmed!==true&&editorActive&&editor.hasUnsavedChanges()&&!globalThis.confirm('저장하지 않은 변경을 버리고 닫을까요?'))return false;if($('#detail-dialog').open)$('#detail-dialog').close();editorActive=false;return true;}
$('#drawer-close').addEventListener('click',closeDetail);
$('#detail-dialog').addEventListener('click',e=>{if(e.target===$('#detail-dialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeDetail();}});
$('#detail-dialog').addEventListener('cancel',e=>{e.preventDefault();closeDetail();});
$('#detail-dialog').addEventListener('close',()=>{document.body.style.overflow='';if(lastFocus?.isConnected)lastFocus.focus();else $('[data-view][aria-current="page"]')?.focus();detailId=null;});
$('#detail-dialog').addEventListener('keydown',e=>{
  if(e.key!=='Tab')return;
  const nodes=[...$('#detail-dialog').querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),[tabindex="0"]')].filter(el=>el.getClientRects().length);
  const first=nodes[0],last=nodes[nodes.length-1];
  if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}
  else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}
});
const loader=createSnapshotLoader(next=>{state=next;render();});
document.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>setView(button.dataset.view)));
document.querySelectorAll('[data-scope]').forEach(button=>button.addEventListener('click',()=>{if(!confirmLeave())return;if($('#detail-dialog').open&&!closeDetail(true))return;operations.load(button.dataset.scope);metrics.load(button.dataset.scope);loader.select(button.dataset.scope);}));
$('#refresh').addEventListener('click',()=>{if(execution.isBusy()||operations.isBusy()||(editorActive&&editor.isBusy()))return;execution.load();operations.load(state.account);metrics.load(state.account);refreshWorkspace({loader,integrationSettings,account:state.account,writable:writable(),editorDirty:false,confirm:message=>globalThis.confirm(message)});});
window.addEventListener('beforeunload',event=>{if((editorActive&&editor.hasUnsavedChanges())||integrationSettings.hasUnsavedChanges()||operations.isDirty()||operations.isBusy()||metrics.isDirty()||metrics.isBusy()||execution.isDirty()||execution.isBusy()){event.preventDefault();event.returnValue='';}});
execution.load();
operations.load('all');
loader.select('all');
setInterval(renderStatus,60000);
