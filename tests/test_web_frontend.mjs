import test from 'node:test';
import assert from 'node:assert/strict';
import { relatedContents, filterContents, safeUrl, statusLabel, aggregate, dayKey, formatDateTime, weekDays } from '../ax-console/app/web/view_helpers.js';
import { fetchSnapshot, createSnapshotLoader } from '../ax-console/app/web/api.js';

const snapshot = () => ({schema_version:1,read_only:true,generated_at:'2026-10-30T09:00:00+09:00',scope:'all',warnings:[],accounts:[{id:'personal',label:'개인'},{id:'dept',label:'학과'}],contents:[
{id:'p',title:'공간 정보 숏츠',owner_account_id:'personal',kind:'short',series:'기술사',status:'scheduled',revision:1,summary:'공간정보 개념',created_at:null,updated_at:null,channels:['YouTube']},
{id:'d',title:'안전 카드',owner_account_id:'dept',kind:'card',series:'안전',status:'review',revision:null,summary:null,created_at:null,updated_at:null,channels:['Instagram']},
{id:'rule-source',title:'규칙 원본',owner_account_id:'personal',kind:'article',series:null,status:'idea',revision:null,summary:null,created_at:null,updated_at:null,channels:['Blogger']}
],deliveries:[
{id:'a',content_id:'p',owner_account_id:'personal',destination_account_id:'dept',channel:'TikTok',target_label:'학과 TikTok',status:'scheduled_recorded',schedule_kind:'remote_recorded',scheduled_at:'2026-10-30T19:00:00+09:00',url:null,checked_at:null,evidence:null},
{id:'b',content_id:'p',owner_account_id:'personal',destination_account_id:'personal',channel:'YouTube',target_label:null,status:'reported_published',schedule_kind:'unknown',scheduled_at:null,url:'https://example.org/post',checked_at:null,evidence:'local done'},
{id:'c',content_id:'d',owner_account_id:'dept',destination_account_id:'dept',channel:'Instagram',target_label:null,status:'verified',schedule_kind:'unknown',scheduled_at:null,url:'https://example.org/verified',checked_at:'2026-10-30T09:00:00+09:00',evidence:'explicit content verification'}
],channels:[],schedule:[],incidents:[{id:'i',title:'인증 확인',account_id:'dept',severity:'warning',status:'open',summary:null,last_at:null}],crossposts:[{id:'r',owner_account_id:'personal',destination_account_id:'dept',source_channel:'Blogger',destination_channel:'Threads',title:'규칙 원본',condition:null,enabled:false}],proposals:[],metrics:{status:'unavailable',items:[]}});

test('관련 계정은 교차 배포와 규칙의 원본 소유권을 보존한다', () => {
  const s=snapshot();
  assert.deepEqual(relatedContents(s,'dept').map(c=>c.id),['p','d','rule-source']);
  assert.deepEqual(relatedContents(s,'personal').map(c=>c.id),['p','rule-source']);
  assert.equal(relatedContents(s,'dept')[0].owner_account_id,'personal');
  s.contents.push({...s.contents[2],id:'unrelated',channels:['Naver']});
  assert.equal(relatedContents(s,'dept').some(c=>c.id==='unrelated'),false);
});
test('검색, 형식, 시리즈, 소유자 및 대상별 상태 필터를 함께 적용한다',()=>{
  const s=snapshot();
  assert.deepEqual(filterContents(s,{account:'dept',query:'tiktok',kind:'short',series:'기술사',owner:'personal',status:'scheduled_recorded'}).map(c=>c.id),['p']);
  assert.deepEqual(filterContents(s,{query:'없는 제목'}),[]);
  assert.deepEqual(filterContents(s,{kind:'video'}),[]);
});
test('사용자 URL은 절대 http/https만 링크로 허용한다',()=>{
  for(const bad of ['javascript:alert(1)','data:text/html,test','file:///tmp/key','//evil.test','/relative','https://name:secret@example.org','https://example.org\n/path',null]) assert.equal(safeUrl(bad),null);
  assert.equal(safeUrl('https://example.org/post?a=1&b=2'),'https://example.org/post?a=1&b=2');
  assert.equal(safeUrl('http://127.0.0.1:8767/'),'http://127.0.0.1:8767/');
});
test('예약 및 로컬 게시 기록을 검증 완료로 집계하지 않는다',()=>{
  const s=snapshot();
  assert.deepEqual(aggregate(s),{contents:3,deliveries:3,verified:1,pending:1,review:1,incidents:1});
  s.deliveries.push({...s.deliveries[2],id:'unproven',evidence:null});
  assert.equal(aggregate(s).verified,1);
  assert.match(statusLabel('reported_published'),/미확인/);
  assert.match(statusLabel('scheduled_recorded'),/기록/);
  assert.match(statusLabel('unexpected'),/미확인/);
});
test('한국 날짜와 주간 범위는 UTC 자정 및 월 경계를 올바르게 처리한다',()=>{
  assert.equal(dayKey('2026-10-29T15:30:00Z'),'2026-10-30');
  assert.equal(dayKey('invalid'),null);
  assert.equal(dayKey(null),null);
  assert.match(formatDateTime(null),/미확인/);
  assert.deepEqual(weekDays('2026-11-01T10:00:00+09:00',0),['2026-10-26','2026-10-27','2026-10-28','2026-10-29','2026-10-30','2026-10-31','2026-11-01']);
  assert.equal(weekDays('2026-11-01T10:00:00+09:00',1)[0],'2026-11-02');
});
test('API는 같은 출처의 읽기 전용 GET과 계정 범위만 사용한다',async()=>{
  let captured;
  const value=await fetchSnapshot('dept',{fetcher:async(url,options)=>{captured={url,options};return {ok:true,status:200,json:async()=>({...snapshot(),scope:'dept'})};}});
  assert.equal(value.scope,'dept');
  assert.equal(captured.url,'/api/v2/snapshot?account=dept');
  assert.equal(captured.options.method,'GET');
  assert.equal(captured.options.credentials,'same-origin');
  await assert.rejects(fetchSnapshot('../bad'),/계정/);
});
test('401과 잘못된 스냅샷은 성공 데이터로 표시하지 않는다',async()=>{
  await assert.rejects(fetchSnapshot('all',{fetcher:async()=>({ok:false,status:401})}),e=>e.status===401);
  await assert.rejects(fetchSnapshot('all',{fetcher:async()=>({ok:true,status:200,json:async()=>({})})}),/형식/);
  await assert.rejects(fetchSnapshot('dept',{fetcher:async()=>({ok:true,status:200,json:async()=>snapshot()})}),/범위/);
});
test('늦은 응답은 최신 계정 조회를 덮어쓰지 않는다',async()=>{
  const pending=[];let latest;
  const loader=createSnapshotLoader(s=>latest=s,{request:(scope)=>new Promise(resolve=>pending.push({scope,resolve}))});
  const first=loader.select('dept');const second=loader.select('personal');
  pending[1].resolve({...snapshot(),scope:'personal'});await second;
  pending[0].resolve({...snapshot(),scope:'dept'});await first;
  assert.equal(latest.account,'personal');assert.equal(latest.snapshot.scope,'personal');assert.equal(latest.phase,'ready');
});
test('갱신 실패는 이전 데이터와 실패를 구분하고 계정 전환은 옛 데이터를 숨긴다',async()=>{
  let latest,fail=false;
  const loader=createSnapshotLoader(s=>latest=s,{request:async(scope)=>{if(fail) throw new Error('network');return {...snapshot(),scope};}});
  await loader.select('all');fail=true;await loader.refresh();
  assert.equal(latest.phase,'error');assert.equal(latest.snapshot.scope,'all');
  const switched=loader.select('dept');assert.equal(latest.snapshot,null);await switched;
  assert.equal(latest.phase,'error');assert.equal(latest.account,'dept');
});

test('연동 카탈로그의 후보와 제공 여부를 설치·계정 연결·실행 가능으로 승격하지 않는다',async()=>{
  const {integrationSummary}=await import('../ax-console/app/web/view_helpers.js');
  const candidate={id:'sns',label:'SNS 연동',kind:'external_plugin',platforms:[{id:'instagram',label:'Instagram'},{id:'threads',label:'Threads'},{id:'x',label:'X'},{id:'tistory',label:'Tistory'},{id:'facebook',label:'Facebook'}],availability:'unknown',connection_status:'unknown',execution_status:'not_connected',description:'도구 카탈로그 후보'};
  assert.deepEqual(integrationSummary(candidate),{kind:'외부 플러그인',platforms:['Instagram','Threads','X','Tistory','Facebook'],availability:'카탈로그 후보 · 제공 여부 미확인',connection:'계정 연결 미확인',execution:'웹 실행 미연결'});
  const provided=integrationSummary({...candidate,availability:'provided'});
  assert.equal(provided.availability,'도구 제공됨 · 설치·연결 미확인');
  assert.equal(provided.connection,'계정 연결 미확인');
  assert.equal(provided.execution,'웹 실행 미연결');
});
test('연동 자료의 누락·예상 밖 상태도 연결 성공이나 활성 실행으로 표시하지 않는다',async()=>{
  const {integrationSummary}=await import('../ax-console/app/web/view_helpers.js');
  assert.deepEqual(integrationSummary({kind:'local_adapter',platforms:null,availability:'installed',connection_status:'connected',execution_status:'enabled'}),{kind:'로컬 어댑터',platforms:[],availability:'카탈로그 후보 · 제공 여부 미확인',connection:'계정 연결 미확인',execution:'웹 실행 상태 미확인'});
});
