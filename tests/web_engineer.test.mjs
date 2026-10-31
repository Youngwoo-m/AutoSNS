import test from 'node:test';import assert from 'node:assert/strict';
import {mkdtempSync,copyFileSync,existsSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';import {join} from 'node:path';import {pathToFileURL} from 'node:url';
const fixture=mkdtempSync(join(tmpdir(),'engineer-label-'));
const artifact=new URL('../.superpowers/sdd/2026-10-30-web-phase6a/engineer-label-artifact.js',import.meta.url);
copyFileSync(existsSync(artifact)?artifact:new URL('../ax-console/app/web/engineer_panel.js',import.meta.url),join(fixture,'engineer_panel.mjs'));
copyFileSync(new URL('../ax-console/app/web/view_helpers.js',import.meta.url),join(fixture,'view_helpers.js'));
process.on('exit',()=>rmSync(fixture,{recursive:true,force:true}));
const {engineerRows,ENGINEER_EXAMS,renderEngineerPanel}=await import(pathToFileURL(join(fixture,'engineer_panel.mjs')));
test('four exams include building and preserve supplied account scope',()=>{assert.equal(ENGINEER_EXAMS.length,4);const row={id:'b',title:'[건축시공기술사] 콘크리트',owner_account_id:'personal',destination_account_id:'dept'};const s={contents:[row,{id:'n',title:'재난 뉴스'}],schedule:[{title:'claude.building-daily'}],crossposts:[{title:'측량 하루 한 문제'}]};assert.deepEqual(engineerRows(s,'building').contents,[row]);assert.equal(engineerRows(s,'building').schedule.length,1);assert.equal(engineerRows(s,'civil').contents.length,0);assert.equal(engineerRows(s).routes.length,1);assert.equal(row.destination_account_id,'dept');});
test('empty snapshots do not invent examples or jobs',()=>assert.deepEqual(engineerRows(),{contents:[],schedule:[],routes:[],legacyRoutes:[]}));
test('safety does not capture unrelated general safety content',()=>assert.equal(engineerRows({contents:[{title:'재난안전 뉴스'}]},'safety').contents.length,0));
test('registered catalog platform titles use subject conditions and delivery rule references',()=>{const catalog=[{id:'tistory.safeworking',title:'tistory → naver_blog',source:'registered_rule',condition:'조건: 주제 분야 중 하나 측량·토목·건축·안전·노르딕워킹',owner_account_id:'personal',destination_account_id:'personal'},{id:'geoai-short.tiktok',title:'youtube → tiktok',source:'registered_rule',condition:'호출 작업 = GeoAI 숏츠',owner_account_id:'personal',destination_account_id:'dept'},{id:'news.tiktok',title:'youtube → tiktok',source:'registered_rule',condition:'호출 작업 = 주간 뉴스'}];const s={contents:[{id:'b',title:'[건축시공기술사] 답안',deliveries:[{crosspost_rule_id:'geoai-short.tiktok'}]}],crossposts:catalog,legacy_crosspost_observations:[{title:'건축시공 하루 한 문제'}]};assert.deepEqual(engineerRows(s,'building').routes.map(r=>r.id),['tistory.safeworking','geoai-short.tiktok']);assert.equal(engineerRows(s,'building').legacyRoutes.length,1);});

test('rendered statuses use Korean labels without promoting legacy records to verified',()=>{
 const statuses=['reported_published','unknown','scheduled','scheduled_recorded','unrecognized'];
 const snapshot={contents:statuses.map((status,i)=>({id:String(i),title:'건축시공기술사',status})),schedule:statuses.map(status=>({title:'건축시공기술사 작업',status})),accounts:[]};
 const original=structuredClone(snapshot);
 const h=(tag,attrs,...children)=>({tag,children:children.flat(Infinity)});
 const text=node=>typeof node==='string'?node:(node?.children||[]).map(text).join(' ');
 const output=text(renderEngineerPanel({snapshot,h,accountLabel:()=> '개인',formatDateTime:()=> '시각 미확인',onSelect(){},onOpen(){}}));
 for(const label of ['게시 기록 · 공개 미확인','상태 미확인','예약·대기','예약 기록 · 현재 미확인'])assert.ok(output.includes(label),label);
 for(const status of statuses)assert.ok(!output.includes(status),status);
 assert.ok(!output.includes('공개·내용 확인 완료'));
 assert.deepEqual(snapshot,original);
});
