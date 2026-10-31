import test from 'node:test';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {mkdtempSync,cpSync,readFileSync,rmSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {harness,all,action,field} from './helpers/execution_dom.mjs';
const temporary=mkdtempSync(join(tmpdir(),'a9-web-'));
const staged=join(temporary,'web');cpSync(resolve('ax-console/app/web'),staged,{recursive:true});
const manifestPath='.superpowers/sdd/2026-10-30-web-phase6a/web-artifacts/manifest.json';
const manifest=existsSync(manifestPath)?JSON.parse(readFileSync(manifestPath)):{entries:[]};
for(const entry of manifest.entries)cpSync(entry.artifact,join(staged,entry.target.split('/').at(-1)));
process.on('exit',()=>rmSync(temporary,{recursive:true,force:true}));
const apiModule=await import(pathToFileURL(join(staged,'api.js')));
const controllerModule=await import(pathToFileURL(join(staged,'execution_controller.js'))).catch(error=>{if(error.code==='ERR_MODULE_NOT_FOUND')return {};throw error;});
const make=options=>{assert.equal(typeof controllerModule.createExecutionWorkspace,'function');return controllerModule.createExecutionWorkspace(options);};
const content={id:'content-1',revision:2,manifest_hash:'a'.repeat(64),owner_account_id:'personal',title:'저장 원고',original:'원고'};
const discovery={service_available:true,execution_enabled:true,blockers:[],capabilities:{request:true,observe:true,admit:true,approve:true},production_jobs:[{id:'produce',label:'제작 작업',owner_account_id:'personal',enabled:true,available:true,phases:['prepare']}],publication_jobs:[{id:'publish',label:'대상 게시 작업',owner_account_id:'personal',enabled:true,available:true,phases:['submit','verify'],connection_ids:['personal.youtube']}]};
const get=(root,name)=>all(root).find(n=>n.name===name);
const button=(root,label)=>all(root).find(n=>n.tagName==='button'&&n.textContent===label);

test('artifact API는 엄격한 실행 endpoint·동일출처 인증을 사용하며 오류 상태를 보존한다',async()=>{
 assert.equal(typeof apiModule.createExecutionApi,'function');const calls=[];const api=apiModule.createExecutionApi({fetcher:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>discovery};}});
 await api.status();await api.request({trigger:{}});await api.getRun('run-1');await api.observe('delivery-1',{run_id:'run-1',expected_version:2});await api.admit('delivery-1',{});await api.approve('delivery-1',{});
 assert.deepEqual(calls.map(c=>c.url),['/api/v2/execution/status','/api/v2/execution/requests','/api/v2/execution/runs/run-1','/api/v2/execution/deliveries/delivery-1/observe','/api/v2/execution/deliveries/delivery-1/admit','/api/v2/execution/deliveries/delivery-1/approve']);
 for(const call of calls){assert.equal(call.options.credentials,'same-origin');assert.equal(call.options.cache,'no-store');}
 for(const status of [401,409,503]){const bad=apiModule.createExecutionApi({fetcher:async()=>({ok:false,status,json:async()=>({code:'media_evidence_required',credential:'SECRET'})})});await assert.rejects(bad.status(),error=>error.status===status&&!error.message.includes('SECRET'));}
});

test('전체 workspace는 등록 작업만 선택하고 prepare와 publication을 별도 회차로 접수한다',async()=>{
 const {document}=harness();const sent=[];const api={status:async()=>discovery,request:async body=>{sent.push(structuredClone(body));return body.trigger.phase==='prepare'?{run_id:'prepare-run',binding_id:'binding-1',content_id:'content-1',content_revision:2,manifest_hash:'a'.repeat(64)}:{run_id:'publish-run',state:'queued'};},observe:async(id,body)=>{sent.push({id,...body});return {observation_id:'observation-1'};},admit:async(id,body)=>({id,version:1,context_hash:'b'.repeat(64)})};
 const workspace=make({api,document,contentApi:{listDeliveries:async()=>({items:[{id:'delivery-1',content_id:'content-1',revision:2,manifest_hash:'a'.repeat(64),connection_id:'personal.youtube',version:4,status:'approved'}]})},clock:()=>new Date('2026-10-31T00:00:00Z')});
 await workspace.load();const root=workspace.forContent(content);assert.equal(sent.length,0);
 get(root,'production_job').value='produce';await get(root,'production_job').fire('change');await action(all(root).find(n=>n.className==='execution-production'),'request').fire('click');
 await button(root,'배포 계획 다시 조회').fire('click');get(root,'planned_delivery').value='delivery-1';await get(root,'planned_delivery').fire('change');get(root,'publication_job').value='publish';await get(root,'publication_job').fire('change');
 const publication=all(root).find(n=>n.className==='execution-publication');await action(publication,'request').fire('click');await action(publication,'observe').fire('click');
 assert.equal(sent[0].trigger.job_id,'produce');assert.equal(sent[0].content_id,'content-1');assert.equal(sent[0].expected_revision,2);assert.equal(sent[1].trigger.job_id,'publish');assert.equal(sent[1].trigger.phase,'submit');assert.equal(sent[1].content_id,null);assert.equal(sent[1].expected_revision,null);assert.deepEqual(sent[2],{id:'delivery-1',run_id:'publish-run',expected_version:4});
});

test('원고 dirty·미등록 작업·다른 대상 계획을 거부하고 서비스 장애 후 입력을 유지한다',async()=>{
 const {document}=harness();let fail=false;const workspace=make({document,api:{status:async()=>{if(fail)throw Object.assign(new Error(),{status:401});return discovery;},request:async()=>{throw new Error('호출 금지');}},contentApi:{listDeliveries:async()=>({items:[]})}});
 await workspace.load();let root=workspace.forContent(content,{dirty:true});get(root,'production_job').value='produce';await get(root,'production_job').fire('change');assert.equal(action(all(root).find(n=>n.className==='execution-production'),'request').disabled,true);
 root=workspace.forContent(content);get(root,'production_job').value='invented';await get(root,'production_job').fire('change');assert.equal(action(all(root).find(n=>n.className==='execution-production'),'request').disabled,true);
 get(root,'production_job').value='produce';await get(root,'production_job').fire('change');fail=true;await workspace.load();assert.equal(get(root,'production_job').value,'produce');assert.match(workspace.renderStatus().textContent,/인증.*보존/);
});

test('실제 원고 편집기는 연 상세의 버전을 실행 workspace에 붙이고 dirty와 이탈 보호를 연결한다',async()=>{
 const {document}=harness();const previous=globalThis.document;globalThis.document=document;
 try {
  const {createContentEditor}=await import(pathToFileURL(join(staged,'content_editor.js')));
  const mounts=[];const execution={forContent:(c,options)=>{mounts.push({content:c,options});return document.createElement('section');},isDirty:()=>false,isBusy:()=>false};
  const api={getContent:async(id,revision)=>({...content,revision:revision||2}),listRevisions:async()=>({items:[{revision:2}]}),listConnections:async()=>({items:[]}),listDeliveries:async()=>({items:[]})};
  const editor=createContentEditor({api,writable:()=>true,execution});await editor.open({id:'content-1',revision:2,source:'managed'});
  assert.ok(mounts.length);assert.equal(mounts.at(-1).content.revision,2);assert.equal(mounts.at(-1).options.dirty,false);
  const title=all(editor.element).find(n=>n.tagName==='input'&&n.value==='저장 원고');title.value='아직 저장하지 않은 제목';await title.fire('input');assert.equal(mounts.at(-1).options.dirty,true);
  execution.isDirty=()=>true;assert.equal(editor.hasUnsavedChanges(),true);execution.isBusy=()=>true;assert.equal(editor.isBusy(),true);
 } finally{for(let i=0;i<10;i++)await Promise.resolve();globalThis.document=previous;}
});

test('실제 앱 artifact는 원고 실행 화면·문제/설정 서비스 상태·beforeunload를 연결한다',async()=>{
 const {document}=harness();const previous=globalThis.document;globalThis.document=document;const surfaces=new Map();const listeners={};
 document.querySelector=selector=>{if(!surfaces.has(selector)){const n=document.createElement('div');n.classList={toggle(){}};n.showModal=()=>n.open=true;n.close=()=>n.open=false;surfaces.set(selector,n);}return surfaces.get(selector);};document.querySelectorAll=()=>[];document.body=document.createElement('body');
 try {
  const {createContentEditor}=await import(pathToFileURL(join(staged,'content_editor.js')));
  const api={getContent:async(id,revision)=>({...content,revision:revision||2}),listRevisions:async()=>({items:[{revision:2}]}),listConnections:async()=>({items:[]}),listDeliveries:async()=>({items:[]})};
  const fakePanel=()=>({load:async()=>{},render:()=>document.createElement('section'),isBusy:()=>false,isDirty:()=>false,discard(){}});
  const source=readFileSync(join(staged,'app.js'),'utf8').replace(/^import .*;\n/gm,'');
  const app=vm.runInNewContext(source+'\n;({openEditor,renderIssues,renderAccounts,editor,setSnapshot:value=>state={snapshot:value,phase:"ready",account:"all"}})',{document,Node:document.createElement('div').constructor,window:{addEventListener:(type,fn)=>listeners[type]=fn},setInterval(){},confirm:()=>true,createContentEditor,contentApi:api,createExecutionWorkspace:controllerModule.createExecutionWorkspace,createExecutionApi:()=>({status:async()=>discovery,request:async()=>{throw Object.assign(new Error(),{status:503});}}),createSnapshotLoader:()=>({select(){},refresh:async()=>{}}),createIntegrationSettings:()=>({element:document.createElement('section'),load(){},hasUnsavedChanges:()=>false}),confirmSettingsNavigation:()=>true,createMetricsPanel:fakePanel,createMetricsApi:()=>({}),createOperationsPanel:fakePanel,createOperationsApi:()=>({}),accountLabel:id=>id,formatDateTime:()=>'',integrationSummary:()=>({platforms:[]}),refreshWorkspace:async()=>{},kindLabel:x=>x,statusLabel:x=>x,scheduleLabel:x=>x,safeUrl:()=>null});
  app.setSnapshot({workspace_writable:true,generated_at:new Date().toISOString(),warnings:[],accounts:[],incidents:[],deliveries:[],channels:[],integrations:[],integration_catalog:[]});
  app.openEditor({id:'content-1',revision:2,source:'managed'});for(let i=0;i<20;i++)await Promise.resolve();
  assert.match(app.editor.element.textContent,/제작과 대상별 발행 실행/);assert.match(app.renderIssues().textContent,/실행 서비스와 접수 결과/);assert.match(app.renderAccounts().textContent,/실행 서비스와 접수 결과/);
  const production=get(app.editor.element,'production_job');production.value='produce';await production.fire('change');const pendingRoot=all(app.editor.element).find(n=>n.className==='execution-production');
  // The actual app's unload listener observes execution-confirmation input held by the editor/workspace.
  await action(pendingRoot,'request').fire('click');let prevented=false;listeners.beforeunload({preventDefault(){prevented=true;}});assert.equal(prevented,true);
 } finally{for(let i=0;i<10;i++)await Promise.resolve();globalThis.document=previous;}
});

test('제작 전용 화면은 발행 승인 입력을 보이지 않고 pending 동안 작업 선택을 잠근다',async()=>{
 const {document}=harness();let fail;const workspace=make({document,api:{status:async()=>discovery,request:()=>new Promise((_,reject)=>fail=reject)},contentApi:{listDeliveries:async()=>({items:[]})}});await workspace.load();const root=workspace.forContent(content);get(root,'production_job').value='produce';await get(root,'production_job').fire('change');
 const production=all(root).find(n=>n.className==='execution-production');assert.equal(field(production,'publication_confirmed'),undefined);assert.equal(action(production,'approve'),undefined);
 const pending=action(production,'request').fire('click');assert.equal(get(root,'production_job').disabled,true);fail(Object.assign(new Error(),{status:503}));await pending;assert.equal(workspace.isDirty(),true);assert.equal(get(root,'production_job').value,'produce');
});
