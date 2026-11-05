import test from 'node:test';
import assert from 'node:assert/strict';
import {createMetricsApi,createMetricsPanel} from '../ax-console/app/web/metrics_panel.js';

class Node {
  constructor(tag){this.tagName=tag;this.children=[];this.listeners={};this.value='';this.disabled=false;this.checked=false;this._text='';}
  set textContent(v){this._text=String(v);this.children=[];} get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
  contains(node){return this===node||this.children.some(child=>child.contains(node));}
  append(...nodes){for(const node of nodes){node.parentElement=this;this.children.push(node);}}
  replaceChildren(...nodes){if(this.ownerDocument?.activeElement!==this&&this.contains(this.ownerDocument?.activeElement))this.ownerDocument.activeElement=null;for(const child of this.children)child.parentElement=null;this._text='';this.children=[];this.append(...nodes);}
  setAttribute(k,v){this[k]=v;} addEventListener(type,fn){this.listeners[type]=fn;}
  focus(){if(!this.disabled)this.ownerDocument.activeElement=this;}
  setSelectionRange(start,end,direction='none'){this.selectionStart=start;this.selectionEnd=end;this.selectionDirection=direction;}
  async fire(type,event={}){if(!this.disabled)return this.listeners[type]?.({preventDefault(){},...event});}
}
const document={activeElement:null,createElement:tag=>Object.assign(new Node(tag),{ownerDocument:document})};
const all=n=>[n,...n.children.flatMap(all)];
const button=(n,text)=>all(n).find(x=>x.tagName==='button'&&x.textContent===text);
const field=(n,name)=>all(n).find(x=>x.name===name);
const observation=(id='zero',extra={})=>({id,source_kind:'verified_delivery',owner_account_id:'personal',destination_account_id:'dept',platform:'youtube',connection_id:'main',target_id:'target',remote_id:'remote',delivery_id:'delivery',content_id:'content',title:id,status:'ok',values:{views:0},observed_at:null,collected_at:'2026-10-30T00:00:00Z',file_mtime:null,definition_id:'views_v1',basis:'lifetime',period:null,source:{path:'reports/safe.json',token:'SECRET'},uncertainties:[],...extra});
const snapshot=(observations=[observation()])=>({account_id:'all',observations,proposals:[],support:[],summary:{verified_observations:1,legacy_reported:0,unassigned:0},collection_enabled:false,writable:true});
const preview=()=>({preview_digest:'digest-a',files:[{path:'reports/safe.json'}],counts:{rows:2,unassigned:1,errors:0},observations:[observation('past',{source_kind:'legacy_reported',status:'legacy_reported'})],warnings:[],writable:true});
const apiFor=extra=>({list:async()=>snapshot(),importPreview:async()=>preview(),...extra});
const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
async function opened(api=apiFor()){const panel=createMetricsPanel({api,document});panel.render({account:'all',writable:true});await tick();return panel;}
const root=panel=>panel.render({account:'all',writable:true});
async function fill(panel){let n=root(panel);const check=field(n,'observation-zero');check.checked=true;await check.fire('change');n=root(panel);field(n,'proposal-account').value='personal';await field(n,'proposal-account').fire('change');field(n,'proposal-title').value='次の企画 <img onerror=x>';await field(n,'proposal-title').fire('input');field(n,'proposal-note').value='관측 근거 검토';await field(n,'proposal-note').fire('input');}
const submit=panel=>all(root(panel)).find(n=>n.tagName==='form').fire('submit');

test('API는 명시한 GET/POST와 same-origin을 사용하고 오류 code/status를 보존한다',async()=>{
  const calls=[];const api=createMetricsApi({fetcher:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>snapshot()};}});
  await api.list('dept');await api.importPreview();await api.importObservations({preview_digest:'d',request_key:'k'});await api.createProposal({account_id:'dept'});
  assert.deepEqual(calls.map(c=>c.url),['/api/v2/metrics?account=dept','/api/v2/metrics/import-preview','/api/v2/metrics/import','/api/v2/metrics/proposals']);
  assert.deepEqual(calls.map(c=>c.options.method),['GET','GET','POST','POST']);assert.ok(calls.every(c=>c.options.credentials==='same-origin'));assert.deepEqual(JSON.parse(calls[2].options.body),{preview_digest:'d',request_key:'k'});
  await assert.rejects(api.list('unknown'),/계정/);
  for(const status of [401,409,503]){const bad=createMetricsApi({fetcher:async()=>({ok:false,status,json:async()=>({code:'safe_error'})})});await assert.rejects(bad.list(),e=>e.status===status&&e.code==='safe_error');}
});
test('조회는 POST 없이 실제0·오류·미지원·미수집·과거보고를 구별하고 누적 기간 및 비용 결측을 표시한다',async()=>{
  let posts=0;const panel=await opened(apiFor({list:async()=>snapshot([observation(),observation('error',{status:'error',values:{views:900}}),observation('unsupported',{status:'unsupported',values:{}}),observation('missing',{values:{}}),observation('past',{source_kind:'legacy_reported',status:'legacy_reported',values:{views:5000},basis:'unknown'})]),importObservations:async()=>posts++,createProposal:async()=>posts++}));
  const n=root(panel);assert.equal(posts,0);for(const text of [/조회수: 0/,/조회 오류/,/미지원/,/미수집/,/과거 보고 자료/,/관측 시각: 미확인/,/누적값/,/기간 발생량/,/비용: 미확인/,/합산하지/])assert.match(n.textContent,text);
  assert.doesNotMatch(n.textContent,/조회수: 900|SECRET/);assert.equal(all(n).filter(x=>x.tagName==='article'&&x.textContent.includes('past')).length,1);
});
test('원본 소유와 실제 대상 필터를 독립 적용하고 동일 관측을 중복 합산하지 않는다',async()=>{
  const panel=await opened(apiFor({list:async()=>snapshot([observation(),observation(),observation('own-dept',{owner_account_id:'dept',destination_account_id:'personal'})])}));let n=root(panel);assert.equal(all(n).filter(x=>x.tagName==='article').length,2);assert.match(n.textContent,/원본 소유: 개인.*대상 계정: 학과/);
  field(n,'owner-filter').value='personal';await field(n,'owner-filter').fire('change');n=root(panel);assert.equal(all(n).filter(x=>x.tagName==='article').length,1);
  field(n,'destination-filter').value='personal';await field(n,'destination-filter').fire('change');assert.equal(all(root(panel)).filter(x=>x.tagName==='article').length,0);
});
test('모든 채널은 구현·권한·수집을 분리하여 가상 연결 없이 나타낸다',async()=>{
  const n=root(await opened());for(const label of ['인스타그램','스레드','엑스','티스토리','페이스북','유튜브','네이버 블로그','틱톡'])assert.match(n.textContent,new RegExp(label));
  assert.match(n.textContent,/구현: 미확인/);assert.match(n.textContent,/권한: 미확인/);assert.match(n.textContent,/수집: 미수집/);
});
test('과거 자료라도 오류와 미지원 수치는 보고 조회수로 표시하지 않는다',async()=>{
  const panel=await opened(apiFor({list:async()=>snapshot([observation('legacy-error',{source_kind:'legacy_reported',status:'error',values:{views:999}}),observation('legacy-unsupported',{source_kind:'legacy_reported',status:'unsupported',values:{views:888}})])}));
  assert.match(root(panel).textContent,/조회 오류/);assert.match(root(panel).textContent,/미지원/);assert.doesNotMatch(root(panel).textContent,/보고 조회수: 999|보고 조회수: 888/);
});
test('관측 상세는 누적과 기간을 구별하고 원본·배포·대상 식별자를 제공한다',async()=>{
  const panel=await opened(apiFor({list:async()=>snapshot([observation('interval',{basis:'interval',period:{start:'2026-10-29T00:00:00Z',end:'2026-10-30T00:00:00Z',timezone:'Asia/Seoul'},observed_at:'2026-10-30T00:00:00Z'})])}));
  const text=root(panel).textContent;assert.match(text,/명시된 기간/);assert.match(text,/원본 식별자: content/);assert.match(text,/배포 식별자: delivery/);assert.match(text,/대상 식별자: target/);assert.match(text,/관측 시각: .*09:00/);
});
for(const status of [401,409,503])test(`제안 ${status}는 제목·메모·선택·동일 요청키를 보존한다`,async()=>{
  const sent=[];const panel=await opened(apiFor({createProposal:async body=>{sent.push(structuredClone(body));throw Object.assign(new Error('SECRET'),{status});}}));await fill(panel);await submit(panel);assert.match(root(panel).textContent,/보존/);assert.doesNotMatch(root(panel).textContent,/SECRET/);assert.equal(field(root(panel),'proposal-note').value,'관측 근거 검토');assert.equal(field(root(panel),'observation-zero').checked,true);await submit(panel);assert.deepEqual(sent[1],sent[0]);assert.ok(sent[0].request_key);assert.deepEqual(sent[0].observation_ids,['zero']);assert.equal(sent[0].account_id,'personal');
});
test('기획제안은 별도 초안이며 성공 후 GET 실패에도 입력·요청키를 해제한다',async()=>{
  const sent=[];let reads=0;const panel=await opened(apiFor({list:async()=>{if(++reads===2)throw Object.assign(new Error(),{status:503});return snapshot();},createProposal:async body=>{sent.push(structuredClone(body));return {proposal:{id:'proposal',status:'draft'}};}}));await fill(panel);await submit(panel);let n=root(panel);assert.match(n.textContent,/초안.*저장.*후속 조회/);assert.equal(field(n,'proposal-title').value,'');assert.match(n.textContent,/원본.*자동.*생성.*승인/);await fill(panel);await submit(panel);assert.notEqual(sent[0].request_key,sent[1].request_key);assert.equal(sent[0].content_id,undefined);
});
for(const status of [401,409,503])test(`가져오기 ${status}는 미리보기·digest·동일 요청키를 보존한다`,async()=>{
  const sent=[];const panel=await opened(apiFor({importObservations:async body=>{sent.push({...body});throw Object.assign(new Error(),{status});}}));await button(root(panel),'가져오기 미리보기').fire('click');assert.equal(sent.length,0);assert.match(root(panel).textContent,/파일 행수: 2/);await button(root(panel),'미리보기 명시 저장').fire('click');await button(root(panel),'미리보기 명시 저장').fire('click');assert.deepEqual(sent[1],sent[0]);assert.equal(sent[0].preview_digest,'digest-a');assert.ok(sent[0].request_key);assert.match(root(panel).textContent,/보존/);
});
test('가져오기 성공 후 GET 실패에도 성공 키와 미리보기를 해제한다',async()=>{
  const sent=[];let reads=0;const panel=await opened(apiFor({list:async()=>{if(++reads===2)throw new Error();return snapshot();},importObservations:async body=>{sent.push({...body});return {imported:1,unchanged:0,preview_digest:'digest-a'};}}));await button(root(panel),'가져오기 미리보기').fire('click');await button(root(panel),'미리보기 명시 저장').fire('click');assert.match(root(panel).textContent,/가져오기.*저장.*후속 조회/);assert.equal(button(root(panel),'미리보기 명시 저장'),undefined);await button(root(panel),'가져오기 미리보기').fire('click');await button(root(panel),'미리보기 명시 저장').fire('click');assert.notEqual(sent[0].request_key,sent[1].request_key);
});
test('계정 전환은 미저장 제안을 보존하며 늦은 다른 계정 응답을 표시하지 않는다',async()=>{
  let resolve;const panel=await opened(apiFor({list:async account=>account==='dept'?new Promise(done=>resolve=done):snapshot()}));await fill(panel);panel.render({account:'dept',writable:true});panel.render({account:'all',writable:true});resolve(snapshot([observation('LATE')]));await tick();assert.equal(field(root(panel),'proposal-note').value,'관측 근거 검토');assert.doesNotMatch(root(panel).textContent,/LATE/);
});
test('비활성 쓰기·API 부재는 저장을 막고 안전한 안내를 표시한다',async()=>{
  const empty=createMetricsPanel({document});assert.match(empty.render({account:'all',writable:false}).textContent,/조회.*사용할 수 없/);
  const panel=await opened();const n=panel.render({account:'all',writable:false});assert.equal(button(n,'가져오기 미리보기').disabled,true);assert.equal(all(n).find(x=>x.type==='submit').disabled,true);
});
test('멸실된 패널은 진행 중 조회의 DOM 변경과 후속 알림을 무시한다',async()=>{
  let resolve,changes=0;const panel=createMetricsPanel({document,onChange:()=>changes++,api:apiFor({list:()=>new Promise(done=>resolve=done)})});const n=panel.render({account:'all',writable:true});panel.destroy();const before=changes;resolve(snapshot());await tick();assert.equal(changes,before);assert.doesNotMatch(n.textContent,/조회수: 0/);
});
test('키보드 필터 연속 변경과 공개 render는 같은 필터로 포커스를 복원한다',async()=>{
  const panel=await opened();const n=root(panel);let filter=field(n,'owner-filter');filter.focus();filter.value='personal';await filter.fire('change');
  assert.equal(document.activeElement,field(n,'owner-filter'));assert.notEqual(document.activeElement,filter);
  filter=document.activeElement;filter.value='dept';await filter.fire('change');assert.equal(document.activeElement,field(n,'owner-filter'));assert.equal(document.activeElement.value,'dept');
  panel.render({account:'all',writable:true});assert.equal(document.activeElement,field(n,'owner-filter'));
});
for(const name of ['proposal-title','proposal-note'])test(`비동기 GET 완료는 ${name}의 포커스·선택·방향을 보존한다`,async()=>{
  let finish,reads=0;const panel=await opened(apiFor({list:async()=>++reads===1?snapshot():new Promise(done=>finish=done)}));const n=root(panel);const pending=panel.load('all');
  const input=field(n,name);input.value='성과 근거 검토를 이어서 입력';await input.fire('input');input.focus();input.setSelectionRange(3,8,'backward');finish(snapshot());await pending;
  const current=field(n,name);assert.equal(document.activeElement,current);assert.equal(current.value,'성과 근거 검토를 이어서 입력');assert.deepEqual([current.selectionStart,current.selectionEnd,current.selectionDirection],[3,8,'backward']);
  panel.render({account:'all',writable:true});assert.equal(document.activeElement,field(n,name));assert.deepEqual([document.activeElement.selectionStart,document.activeElement.selectionEnd],[3,8]);
});
test('쓰기 비활성화는 활성 입력 대신 성과 제목으로 이동하고 외부 포커스는 보존한다',async()=>{
  const panel=await opened();const n=root(panel);field(n,'proposal-title').focus();panel.render({account:'all',writable:false});assert.equal(document.activeElement.tagName,'h2');assert.equal(document.activeElement.textContent,'성과');assert.equal(n.contains(document.activeElement),true);
  const external=document.createElement('button');external.focus();panel.render({account:'all',writable:true});assert.equal(document.activeElement,external);
});
test('계정 전환은 이전 계정 입력의 포커스를 새 계정 입력으로 옮기지 않고 제목으로 보낸다',async()=>{
  const panel=await opened();const n=root(panel);field(n,'proposal-note').focus();panel.render({account:'dept',writable:true});assert.equal(document.activeElement.tagName,'h2');assert.equal(n.contains(document.activeElement),true);await tick();assert.equal(document.activeElement.tagName,'h2');
});
test('재조회로 사라진 관측 체크박스는 제목으로 이동하고 상태 변경은 외부 포커스를 빼앗지 않는다',async()=>{
  let reads=0;const panel=await opened(apiFor({list:async()=>++reads===1?snapshot():snapshot([])}));const n=root(panel);field(n,'observation-zero').focus();await panel.load('all');assert.equal(document.activeElement.tagName,'h2');assert.equal(n.contains(document.activeElement),true);
  const external=document.createElement('input');external.focus();await panel.load('all');assert.equal(document.activeElement,external);
});

test('실제 importer→MetricsStore→GET의 색인·IG·YT·검색 수치를 의미와 단위로 모두 표시한다',async()=>{
  const {execFileSync}=await import('node:child_process');
  const data=JSON.parse(execFileSync('python3',['-m','tests.operations.test_metrics_final_fix','--emit-fixture'],{cwd:new URL('..',import.meta.url),encoding:'utf8'}));
  const panel=await opened(apiFor({list:async()=>data}));const text=root(panel).textContent;
  for(const label of [/색인 총수: 321/,/검사 수: 15/,/색인 확인 수: 12/,/미색인 수: 3/,/팔로워: 123/,/게시물 수: 4/,/저장 수: 7/,/구독자: 55/,/누적 조회수: 678/,/클릭률: 0.75/,/평균 게재순위: 2.5/,/검색어 수: 9/])assert.match(text,label);
  assert.match(text,/비율 단위 미확인/);assert.doesNotMatch(text,/SECRET|75%|보고 조회수: 미수집/);
});
test('이름표 미정 수치는 안전한 상세에 원래 숫자로 남긴다',async()=>{
  const panel=await opened(apiFor({list:async()=>snapshot([observation('other',{values:{'<img onerror=x>':1.25}})])}));
  const detail=all(root(panel)).find(n=>n.tagName==='article').children.find(n=>n.tagName==='details');
  assert.match(detail.textContent,/<img onerror=x>: 1.25/);assert.match(detail.textContent,/의미·단위 미확인/);assert.equal(all(detail).some(n=>n.tagName==='img'),false);
});
test('401→새 창 로그인→재조회→동일 제안 재시도는 기존 문서 입력과 키를 유지한다',async()=>{
  let authenticated=false;const sent=[];
  const panel=await opened(apiFor({list:async()=>{if(sent.length&&!authenticated)throw Object.assign(new Error(),{status:401});return snapshot();},createProposal:async body=>{sent.push(structuredClone(body));if(!authenticated)throw Object.assign(new Error(),{status:401});return {proposal:{id:'saved'}};}}));
  await fill(panel);await submit(panel);const n=root(panel);
  const link=all(n).find(n=>n.tagName==='a'&&n.href==='/login');assert.ok(link);assert.equal(link.target,'_blank');assert.match(link.rel,/noopener/);
  assert.equal(panel.isDirty(),true);assert.equal(field(n,'proposal-note').value,'관측 근거 검토');
  authenticated=true;await button(n,'로그인 완료 후 재조회').fire('click');
  assert.equal(field(root(panel),'proposal-account').value,'personal');assert.equal(field(root(panel),'observation-zero').checked,true);assert.equal(field(root(panel),'proposal-title').value,'次の企画 <img onerror=x>');
  await submit(panel);assert.deepEqual(sent[1],sent[0]);assert.equal(panel.isDirty(),false);
});
test('401 가져오기 복구와 다른 계정의 dirty·pending·busy 상태를 모두 보고한다',async()=>{
  let authenticated=false,finish;const sent=[];
  const panel=await opened(apiFor({importObservations:async body=>{sent.push({...body});if(!authenticated)throw Object.assign(new Error(),{status:401});await new Promise(done=>finish=done);return {};}}));
  assert.equal(panel.isDirty(),false);await button(root(panel),'가져오기 미리보기').fire('click');assert.equal(panel.isDirty(),true);
  await button(root(panel),'미리보기 명시 저장').fire('click');authenticated=true;await button(root(panel),'로그인 완료 후 재조회').fire('click');
  const pending=button(root(panel),'미리보기 명시 저장').fire('click');assert.equal(panel.isBusy(),true);
  panel.render({account:'dept',writable:true});assert.equal(panel.isDirty(),true);assert.equal(panel.isBusy(),true);
  finish();await pending;assert.deepEqual(sent[1],sent[0]);assert.equal(panel.isBusy(),false);assert.equal(panel.isDirty(),false);
});
test('아주 작은 유효 수치는 실제 0으로 반올림하지 않고 모든 원래 숫자를 보존한다',async()=>{
  const panel=await opened(apiFor({list:async()=>snapshot([observation('tiny',{values:{ctr:1e-25,unknown_value:1e-30}})])}));
  const article=all(root(panel)).find(n=>n.tagName==='article');assert.match(article.textContent,/1e-25/);assert.match(article.textContent,/1e-30/);
});
test('미정 수치 상세도 Escape가 요약 버튼으로 포커스를 복귀시킨다',async()=>{
  const panel=await opened(apiFor({list:async()=>snapshot([observation('unknown',{values:{custom:12}})])}));
  const article=all(root(panel)).find(n=>n.tagName==='article');const detail=article.children.find(n=>n.tagName==='details');
  detail.open=true;await detail.fire('keydown',{key:'Escape'});assert.equal(detail.open,false);assert.equal(document.activeElement.tagName,'summary');
});
