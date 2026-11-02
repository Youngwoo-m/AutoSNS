import {createVoiceSettingsPanel} from '../ax-console/app/web/voice_settings_panel.js';
import test from 'node:test';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {mkdtempSync,cpSync,readFileSync,rmSync,existsSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {harness,all,action,field} from './helpers/execution_dom.mjs';
import {stagedWebRoot as staged} from './helpers/staged_web.mjs';
import * as navigation from '../ax-console/app/web/account_navigation.js';
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
  execution.isDirty=()=>true;assert.equal(editor.hasUnsavedChanges(),true);await title.fire('input');assert.match(editor.element.textContent,/실행 요청·발행 확인 입력/);execution.isBusy=()=>true;assert.equal(editor.isBusy(),true);
 } finally{for(let i=0;i<10;i++)await Promise.resolve();globalThis.document=previous;}
});

test('실제 앱 artifact는 원고 실행 화면·문제/설정 서비스 상태·beforeunload를 연결한다',async()=>{
 const {document}=harness();const previous=globalThis.document;globalThis.document=document;const surfaces=new Map();const listeners={};let voicePanel;
 document.querySelector=selector=>{if(!surfaces.has(selector)){const n=document.createElement('div');n.classList={toggle(){}};n.showModal=()=>n.open=true;n.close=()=>n.open=false;surfaces.set(selector,n);}return surfaces.get(selector);};document.querySelectorAll=()=>[];document.body=document.createElement('body');
 try {
  const {createContentEditor}=await import(pathToFileURL(join(staged,'content_editor.js')));
  const api={getContent:async(id,revision)=>({...content,revision:revision||2}),listRevisions:async()=>({items:[{revision:2}]}),listConnections:async()=>({items:[]}),listDeliveries:async()=>({items:[]})};
  const fakePanel=()=>({load:async()=>{},render:()=>document.createElement('section'),isBusy:()=>false,isDirty:()=>false,discard(){}});
  const source=readFileSync(join(staged,'app.js'),'utf8').replace(/^import .*;\n/gm,'');
  const app=vm.runInNewContext(source+'\n;({openEditor,renderIssues,renderAccounts,editor,setSnapshot:value=>state={snapshot:value,phase:"ready",account:"all"}})',{...navigation,createVoiceSettingsPanel:options=>voicePanel=createVoiceSettingsPanel({...options,fetcher:async()=>({ok:true,status:200,json:async()=>({account_id:'personal',revision:0,enabled_preference:false,profile_id:null,applies_to:'next_startup',execution_enabled:false})})}),createProductionSettingsPanel:()=>({isBusy:()=>false,isDirty:()=>false}),createOAuthApi:()=>({}),createOAuthController:()=>({isBusy:()=>false,hasUnsavedChanges:()=>false}),createOAuthPanel:()=>({}),createToolkitApi:()=>({}),createToolkitController:()=>({}),createToolkitPanel:()=>({render:()=>document.createElement('section'),isBusy:()=>false,isDirty:()=>false}),document,Node:document.createElement('div').constructor,window:{addEventListener:(type,fn)=>listeners[type]=fn},setInterval(){},confirm:()=>true,createContentEditor,contentApi:api,createExecutionWorkspace:controllerModule.createExecutionWorkspace,createExecutionApi:()=>({status:async()=>discovery,request:async()=>{throw Object.assign(new Error(),{status:503});}}),createSnapshotLoader:()=>({select(){},refresh:async()=>{}}),createIntegrationSettings:()=>({element:document.createElement('section'),load(){},hasUnsavedChanges:()=>false}),confirmSettingsNavigation:()=>true,createMetricsPanel:fakePanel,createMetricsApi:()=>({}),createOperationsPanel:fakePanel,createOperationsApi:()=>({}),accountLabel:id=>id,formatDateTime:()=>'',integrationSummary:()=>({platforms:[]}),refreshWorkspace:async()=>{},kindLabel:x=>x,statusLabel:x=>x,scheduleLabel:x=>x,safeUrl:()=>null});
  app.setSnapshot({workspace_writable:true,generated_at:new Date().toISOString(),warnings:[],accounts:[],incidents:[],deliveries:[],channels:[],integrations:[],integration_catalog:[]});
  app.openEditor({id:'content-1',revision:2,source:'managed'});for(let i=0;i<20;i++)await Promise.resolve();
  assert.match(app.editor.element.textContent,/제작과 대상별 발행 실행/);assert.match(app.renderIssues().textContent,/실행 서비스와 접수 결과/);assert.match(app.renderAccounts().textContent,/실행 서비스와 접수 결과/);
  await voicePanel.open('personal',{writable:true});voicePanel.element.open=true;await voicePanel.element.fire('toggle');
  const profile=all(voicePanel.element).find(n=>n.tagName==='input'&&n.getAttribute('type')==='text');assert.ok(profile);profile.value='local-profile';await profile.fire('input');
  let voicePrevented=false;listeners.beforeunload({preventDefault(){voicePrevented=true;}});assert.equal(voicePrevented,true);voicePanel.discardChanges();
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

const publicationRoot=root=>all(root).find(n=>n.className==='execution-publication');
async function conflictable({admit,approve,request,getRun,getContent,getDelivery,listDeliveries}={}) {
 const {document}=harness();let version=4;const plan=()=>({id:'delivery-1',content_id:content.id,revision:content.revision,manifest_hash:content.manifest_hash,connection_id:'personal.youtube',owner_account_id:'personal',destination_account_id:'personal',version,status:'ready'});
 const api={status:async()=>discovery,request:request||(async()=>({run_id:'publish-run',state:'queued'})),observe:async()=>({observation_id:'observation-1'}),admit:admit||(async id=>({id,version:1,context_hash:'b'.repeat(64)})),approve:approve||(async id=>({id,version:2,state:'queued'})),getRun:getRun||(async()=>({run_id:'publish-run',state:'queued',deliveries:[]}))};
 const workspace=make({document,api,contentApi:{listDeliveries:listDeliveries||(async()=>({items:[plan()]})),getDelivery:getDelivery||(async()=>plan()),getContent:getContent||(async()=>content)}});await workspace.load();const root=workspace.forContent(content);
 await button(root,'배포 계획 다시 조회').fire('click');get(root,'planned_delivery').value='delivery-1';await get(root,'planned_delivery').fire('change');get(root,'publication_job').value='publish';await get(root,'publication_job').fire('change');await action(publicationRoot(root),'request').fire('click');
 return {workspace,root,document,setVersion:value=>version=value};
}

test('실제 plan4→5 admit409는 읽기 조회로 원요청을 보존한 뒤 명시 로컬 종료와 재관측으로 CAS5를 사용한다',async()=>{
 const sent=[];const fixture=await conflictable({admit:async(id,body)=>{sent.push(structuredClone(body));if(body.expected_version===4)throw Object.assign(new Error(),{status:409});return {id,version:1,context_hash:'c'.repeat(64)};}});const {root}=fixture;
 await action(publicationRoot(root),'observe').fire('click');fixture.setVersion(5);await action(publicationRoot(root),'admit').fire('click');
 await action(publicationRoot(root),'refresh').fire('click');await button(root,'배포 계획 다시 조회').fire('click');assert.match(root.textContent,/현재 선택 계획 버전: 4/);assert.match(root.textContent,/조회된 최신 계획 버전: 5/);
 await action(publicationRoot(root),'admit').fire('click');assert.equal(sent[1].expected_version,4);
 const inspect=button(root,'발행 의도 확인 처리 상태 조회');assert.ok(inspect);await inspect.fire('click');const close=button(root,'발행 의도 확인 충돌 요청 로컬 종료');assert.equal(close.disabled,true);
 const check=get(root,'close_publication_admit');check.checked=true;await check.fire('change');await button(root,'발행 의도 확인 충돌 요청 로컬 종료').fire('click');
 assert.match(root.textContent,/로컬 종료 이력/);assert.match(root.textContent,/원래 CAS: 4/);assert.equal(action(publicationRoot(root),'admit').disabled,true);
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');assert.equal(sent.at(-1).expected_version,5);assert.equal(sent.at(-1).observation_id,'observation-1');
});

test('승인 CAS 충돌은 원래 key를 이력에 보존하고 최신 문맥 재확인 뒤에만 새 key를 생성한다',async()=>{
 const sent=[];const fixture=await conflictable({approve:async(id,body)=>{sent.push(structuredClone(body));if(body.expected_version===1)throw Object.assign(new Error(),{status:409});return {id,version:4,state:'queued'};},getRun:async()=>({run_id:'publish-run',state:'waiting',deliveries:[{id:'delivery-1',version:3,state:'queued',context_hash:'c'.repeat(64)}]})});const {root}=fixture;
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');let check=field(publicationRoot(root),'publication_confirmed');check.checked=true;await check.fire('change');await action(publicationRoot(root),'approve').fire('click');const oldKey=sent[0].request_key;
 await action(publicationRoot(root),'refresh').fire('click');assert.match(publicationRoot(root).textContent,/배포: delivery-1 · 버전: 1/);await button(root,'별도 발행 승인 처리 상태 조회').fire('click');assert.equal(field(publicationRoot(root),'publication_confirmed').checked,true);await action(publicationRoot(root),'approve').fire('click');assert.equal(sent[1].request_key,oldKey);assert.equal(sent[1].expected_version,1);
 // A retry invalidates the previous read: another explicit read is required.
 assert.equal(button(root,'별도 발행 승인 충돌 요청 로컬 종료').disabled,true);await button(root,'별도 발행 승인 처리 상태 조회').fire('click');check=get(root,'close_publication_approve');check.checked=true;await check.fire('change');await button(root,'별도 발행 승인 충돌 요청 로컬 종료').fire('click');
 assert.match(root.textContent,new RegExp(oldKey));assert.equal(field(publicationRoot(root),'publication_confirmed').checked,false);assert.equal(action(publicationRoot(root),'approve').disabled,true);
 check=field(publicationRoot(root),'publication_confirmed');check.checked=true;await check.fire('change');await action(publicationRoot(root),'approve').fire('click');assert.equal(sent.at(-1).expected_version,3);assert.equal(sent.at(-1).context_hash,'c'.repeat(64));assert.notEqual(sent.at(-1).request_key,oldKey);
});

for(const status of [401,503])test(`${status} 불확실 요청은 상태를 조회해도 로컬 종료나 키 자동 변경을 허용하지 않는다`,async()=>{
 const sent=[];const {root}=await conflictable({approve:async(id,body)=>{sent.push(structuredClone(body));throw Object.assign(new Error(),{status});},getRun:async()=>({run_id:'publish-run',state:'queued',deliveries:[{id:'delivery-1',version:9,state:'queued',context_hash:'c'.repeat(64)}]})});
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');const check=field(publicationRoot(root),'publication_confirmed');check.checked=true;await check.fire('change');await action(publicationRoot(root),'approve').fire('click');await button(root,'별도 발행 승인 처리 상태 조회').fire('click');
 assert.equal(button(root,'별도 발행 승인 충돌 요청 로컬 종료'),undefined);await action(publicationRoot(root),'approve').fire('click');assert.deepEqual(sent[1],sent[0]);assert.equal(get(root,'publication_job').disabled,true);
});

test('unknown/원격 요청 시작 후 로컬 충돌 정리는 원격 취소나 새 게시 허가가 아니며 새 변이를 차단한다',async()=>{
 const {root}=await conflictable({approve:async()=>{throw Object.assign(new Error(),{status:409});},getRun:async()=>({run_id:'publish-run',state:'unknown',deliveries:[{id:'delivery-1',version:3,state:'unknown',remote_id:'remote-started',remote_uncertain:true,context_hash:'b'.repeat(64)}]})});
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');let check=field(publicationRoot(root),'publication_confirmed');check.checked=true;await check.fire('change');await action(publicationRoot(root),'approve').fire('click');await button(root,'별도 발행 승인 처리 상태 조회').fire('click');check=get(root,'close_publication_approve');check.checked=true;await check.fire('change');await button(root,'별도 발행 승인 충돌 요청 로컬 종료').fire('click');
 assert.match(root.textContent,/원격 취소.*새 게시 허가.*아닙니다/);assert.match(root.textContent,/게시 여부.*불확실/);for(const name of ['request','observe','admit','approve'])assert.equal(action(publicationRoot(root),name).disabled,true);
});

test('제작 원고 revision 충돌은 기존 요청을 이력에 남기고 명시적으로 최신 원고를 열어 선택한다',async()=>{
 const {document}=harness();const sent=[],opened=[];const latest={...content,revision:3,manifest_hash:'c'.repeat(64)};const workspace=make({document,api:{status:async()=>discovery,request:async body=>{sent.push(structuredClone(body));if(body.expected_revision===2)throw Object.assign(new Error(),{status:409});return {run_id:'new-production',binding_id:'binding-new',content_id:content.id,content_revision:3,manifest_hash:latest.manifest_hash};}},contentApi:{getContent:async()=>latest},onOpenOutput:(id,revision)=>opened.push({id,revision})});await workspace.load();const root=workspace.forContent(content);get(root,'production_job').value='produce';await get(root,'production_job').fire('change');await action(all(root).find(n=>n.className==='execution-production'),'request').fire('click');
 await button(root,'제작 요청 처리 상태 조회').fire('click');assert.equal(sent.length,1);const check=get(root,'close_production_request');check.checked=true;await check.fire('change');await button(root,'제작 요청 충돌 요청 로컬 종료').fire('click');assert.match(root.textContent,/원래 원고 버전: 2/);assert.equal(action(all(root).find(n=>n.className==='execution-production'),'request').disabled,true);
 await button(root,'최신 원고 버전 열어 재검토').fire('click');assert.deepEqual(opened,[{id:content.id,revision:3}]);const next=workspace.forContent(latest);get(next,'production_job').value='produce';await get(next,'production_job').fire('change');await action(all(next).find(n=>n.className==='execution-production'),'request').fire('click');assert.equal(sent.at(-1).expected_revision,3);
});

test('충돌 처리 상태 조회의 인증 만료도 새 창 로그인과 원래 요청 보존을 제공한다',async()=>{
 const {root}=await conflictable({approve:async()=>{throw Object.assign(new Error(),{status:409});},getRun:async()=>{throw Object.assign(new Error(),{status:401});}});
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');const check=field(publicationRoot(root),'publication_confirmed');check.checked=true;await check.fire('change');await action(publicationRoot(root),'approve').fire('click');await button(root,'별도 발행 승인 처리 상태 조회').fire('click');
 assert.equal(button(root,'별도 발행 승인 충돌 요청 로컬 종료').disabled,true);const login=all(root).find(n=>n.tagName==='a'&&n.getAttribute('href')==='/login');assert.ok(login);assert.equal(login.getAttribute('target'),'_blank');assert.equal(get(root,'publication_job').disabled,true);
});

test('R1 검토 queued3 뒤 일반 refresh unknown4는 이전 확인을 무효화하고 더 오래된 재검토로도 변이를 허용하지 않는다',async()=>{
 let reads=0;const sent=[];const {root}=await conflictable({approve:async(id,body)=>{sent.push(structuredClone(body));throw Object.assign(new Error(),{status:409});},getRun:async()=>{reads++;return reads===2?{run_id:'publish-run',state:'unknown',version:4,deliveries:[{id:'delivery-1',version:4,state:'unknown',remote_id:'remote-started',remote_uncertain:true,context_hash:'d'.repeat(64)}]}:{run_id:'publish-run',state:'waiting',version:3,deliveries:[{id:'delivery-1',version:3,state:'queued',context_hash:'c'.repeat(64)}]};}});
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');let check=field(publicationRoot(root),'publication_confirmed');check.checked=true;await check.fire('change');await action(publicationRoot(root),'approve').fire('click');const original=structuredClone(sent[0]);
 await button(root,'별도 발행 승인 처리 상태 조회').fire('click');check=get(root,'close_publication_approve');check.checked=true;await check.fire('change');assert.equal(button(root,'별도 발행 승인 충돌 요청 로컬 종료').disabled,false);
 await action(publicationRoot(root),'refresh').fire('click');assert.match(root.textContent,/remote-started/);assert.match(root.textContent,/게시 여부 불확실/);assert.equal(button(root,'별도 발행 승인 충돌 요청 로컬 종료').disabled,true);assert.equal(get(root,'close_publication_approve').checked,false);assert.equal(get(root,'close_publication_approve').disabled,true);
 await action(publicationRoot(root),'approve').fire('click');assert.deepEqual(sent[1],original);
 // Even if a subsequent read is older/queued, currently known unknown4 wins at close.
 await button(root,'별도 발행 승인 처리 상태 조회').fire('click');check=get(root,'close_publication_approve');check.checked=true;await check.fire('change');await button(root,'별도 발행 승인 충돌 요청 로컬 종료').fire('click');
 assert.match(root.textContent,new RegExp(original.request_key));assert.match(publicationRoot(root).textContent,/배포: delivery-1 · 버전: 4/);for(const name of ['request','observe','admit','approve'])assert.equal(action(publicationRoot(root),name).disabled,true);
});

test('R1 처리 상태 검토 뒤 계획 재조회도 이전 확인을 무효화하며 원래 승인 CAS와 키는 유지한다',async()=>{
 const sent=[];const fixture=await conflictable({approve:async(id,body)=>{sent.push(structuredClone(body));throw Object.assign(new Error(),{status:409});},getRun:async()=>({run_id:'publish-run',state:'waiting',deliveries:[{id:'delivery-1',version:3,state:'queued',context_hash:'c'.repeat(64)}]})});const {root}=fixture;
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');let check=field(publicationRoot(root),'publication_confirmed');check.checked=true;await check.fire('change');await action(publicationRoot(root),'approve').fire('click');await button(root,'별도 발행 승인 처리 상태 조회').fire('click');check=get(root,'close_publication_approve');check.checked=true;await check.fire('change');
 fixture.setVersion(5);await button(root,'배포 계획 다시 조회').fire('click');assert.equal(button(root,'별도 발행 승인 충돌 요청 로컬 종료').disabled,true);assert.equal(get(root,'close_publication_approve').checked,false);assert.match(root.textContent,/현재 선택 계획 버전: 4/);assert.match(root.textContent,/조회된 최신 계획 버전: 5/);
 await action(publicationRoot(root),'approve').fire('click');assert.deepEqual(sent[1],sent[0]);assert.equal(sent[1].expected_version,1);
});

test('R1 원격 ID 없이 remote_uncertain만 관측해도 오래된 검토로 새 변이를 허용하지 않는다',async()=>{
 let reads=0;const {root}=await conflictable({approve:async()=>{throw Object.assign(new Error(),{status:409});},getRun:async()=>++reads===2?{run_id:'publish-run',state:'waiting',deliveries:[{id:'delivery-1',version:4,state:'queued',remote_uncertain:true,context_hash:'d'.repeat(64)}]}:{run_id:'publish-run',state:'waiting',deliveries:[{id:'delivery-1',version:3,state:'queued',context_hash:'c'.repeat(64)}]}});
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');let check=field(publicationRoot(root),'publication_confirmed');check.checked=true;await check.fire('change');await action(publicationRoot(root),'approve').fire('click');await button(root,'별도 발행 승인 처리 상태 조회').fire('click');await action(publicationRoot(root),'refresh').fire('click');
 assert.match(root.textContent,/게시 여부 불확실/);assert.equal(button(root,'별도 발행 승인 충돌 요청 로컬 종료').disabled,true);await button(root,'별도 발행 승인 처리 상태 조회').fire('click');check=get(root,'close_publication_approve');check.checked=true;await check.fire('change');await button(root,'별도 발행 승인 충돌 요청 로컬 종료').fire('click');for(const name of ['request','observe','admit','approve'])assert.equal(action(publicationRoot(root),name).disabled,true);
});


for(const source of ['refresh','review'])test(`R1 highwater ${source} unknown4 뒤 연속 queued3 조회도 불확실 근거와 CAS4를 보존한다`,async()=>{
 let reads=0;const sent=[];const unknownAt=source==='refresh'?2:1;
 const {root}=await conflictable({approve:async(id,body)=>{sent.push(structuredClone(body));throw Object.assign(new Error(),{status:409});},getRun:async()=>++reads===unknownAt?{run_id:'publish-run',state:'unknown',deliveries:[{id:'delivery-1',version:4,state:'unknown',remote_id:'highwater-remote',remote_uncertain:true,context_hash:'d'.repeat(64)}]}:{run_id:'publish-run',state:'waiting',deliveries:[{id:'delivery-1',version:3,state:'queued',context_hash:'c'.repeat(64)}]}});
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');let check=field(publicationRoot(root),'publication_confirmed');check.checked=true;await check.fire('change');await action(publicationRoot(root),'approve').fire('click');const original=structuredClone(sent[0]);
 await button(root,'별도 발행 승인 처리 상태 조회').fire('click');if(source==='refresh')await action(publicationRoot(root),'refresh').fire('click');
 await action(publicationRoot(root),'refresh').fire('click');await action(publicationRoot(root),'refresh').fire('click');
 assert.match(root.textContent,/highwater-remote/);await action(publicationRoot(root),'approve').fire('click');assert.deepEqual(sent[1],original);
 await button(root,'별도 발행 승인 처리 상태 조회').fire('click');check=get(root,'close_publication_approve');check.checked=true;await check.fire('change');await button(root,'별도 발행 승인 충돌 요청 로컬 종료').fire('click');
 assert.match(publicationRoot(root).textContent,/배포: delivery-1 · 버전: 4/);assert.match(root.textContent,/highwater-remote/);for(const name of ['request','observe','admit','approve'])assert.equal(action(publicationRoot(root),name).disabled,true);
});

test('R1 highwater 동버전 runtime 문맥 불일치는 이후 일치 응답으로 해소하지 않고 변이를 차단한다',async()=>{
 let reads=0;const {root}=await conflictable({approve:async()=>{throw Object.assign(new Error(),{status:409});},getRun:async()=>({run_id:'publish-run',state:'waiting',deliveries:[{id:'delivery-1',version:3,state:'queued',context_hash:(++reads===2?'d':'c').repeat(64)}]})});
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');let check=field(publicationRoot(root),'publication_confirmed');check.checked=true;await check.fire('change');await action(publicationRoot(root),'approve').fire('click');await button(root,'별도 발행 승인 처리 상태 조회').fire('click');await action(publicationRoot(root),'refresh').fire('click');await action(publicationRoot(root),'refresh').fire('click');await button(root,'별도 발행 승인 처리 상태 조회').fire('click');check=get(root,'close_publication_approve');check.checked=true;await check.fire('change');await button(root,'별도 발행 승인 충돌 요청 로컬 종료').fire('click');
 assert.match(root.textContent,/불일치/);for(const name of ['request','observe','admit','approve'])assert.equal(action(publicationRoot(root),name).disabled,true);
});

test('R1 highwater 계획5 조회 뒤 계획4 목록과 검토는 새 요청 CAS를 하강시키지 않는다',async()=>{
 const sent=[];const fixture=await conflictable({admit:async(id,body)=>{sent.push(structuredClone(body));if(body.expected_version===4)throw Object.assign(new Error(),{status:409});return {id,version:1,context_hash:'c'.repeat(64)};}});const {root}=fixture;
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');fixture.setVersion(5);await button(root,'배포 계획 다시 조회').fire('click');fixture.setVersion(4);await button(root,'배포 계획 다시 조회').fire('click');assert.match(root.textContent,/조회된 최신 계획 버전: 5/);
 await button(root,'발행 의도 확인 처리 상태 조회').fire('click');let check=get(root,'close_publication_admit');check.checked=true;await check.fire('change');await button(root,'발행 의도 확인 충돌 요청 로컬 종료').fire('click');await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');assert.equal(sent.at(-1).expected_version,5);
});


test('R1 highwater 같은 계획 버전의 대상 불일치는 재조회로 해소되지 않는다',async()=>{
 let reads=0;const {root}=await conflictable({admit:async()=>{throw Object.assign(new Error(),{status:409});},getDelivery:async()=>({id:'delivery-1',content_id:content.id,revision:content.revision,manifest_hash:content.manifest_hash,connection_id:++reads===1?'personal.other':'personal.youtube',owner_account_id:'personal',destination_account_id:'personal',version:4,status:'ready'})});
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');await button(root,'발행 의도 확인 처리 상태 조회').fire('click');await button(root,'발행 의도 확인 처리 상태 조회').fire('click');const check=get(root,'close_publication_admit');check.checked=true;await check.fire('change');await button(root,'발행 의도 확인 충돌 요청 로컬 종료').fire('click');
 assert.match(root.textContent,/동일 버전 계획 조회 결과가 불일치/);for(const name of ['request','observe','admit','approve'])assert.equal(action(publicationRoot(root),name).disabled,true);
});

test('R1 highwater unknown 뒤 더 높은 queued 버전도 원격 불확실성을 자동 해소하지 않는다',async()=>{
 let reads=0;const {root}=await conflictable({approve:async()=>{throw Object.assign(new Error(),{status:409});},getRun:async()=>++reads===1?{run_id:'publish-run',state:'unknown',deliveries:[{id:'delivery-1',version:4,state:'unknown',remote_uncertain:true,context_hash:'d'.repeat(64)}]}:{run_id:'publish-run',state:'waiting',deliveries:[{id:'delivery-1',version:6,state:'queued',remote_uncertain:false,context_hash:'f'.repeat(64)}]}});
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');let check=field(publicationRoot(root),'publication_confirmed');check.checked=true;await check.fire('change');await action(publicationRoot(root),'approve').fire('click');await button(root,'별도 발행 승인 처리 상태 조회').fire('click');await action(publicationRoot(root),'refresh').fire('click');await button(root,'별도 발행 승인 처리 상태 조회').fire('click');check=get(root,'close_publication_approve');check.checked=true;await check.fire('change');await button(root,'별도 발행 승인 충돌 요청 로컬 종료').fire('click');
 assert.match(publicationRoot(root).textContent,/배포: delivery-1 · 버전: 6/);assert.match(root.textContent,/게시 여부 불확실/);for(const name of ['request','observe','admit','approve'])assert.equal(action(publicationRoot(root),name).disabled,true);
});


test('R1 highwater 이전 정상 snapshot은 새 검토 응답의 필수 context 누락을 채워 성공시키지 않는다',async()=>{
 let reads=0;const {root}=await conflictable({approve:async()=>{throw Object.assign(new Error(),{status:409});},getRun:async()=>({run_id:'publish-run',state:'waiting',deliveries:[{id:'delivery-1',version:3,state:'queued',...(++reads===1?{context_hash:'c'.repeat(64)}:{})}]})});
 await action(publicationRoot(root),'observe').fire('click');await action(publicationRoot(root),'admit').fire('click');const check=field(publicationRoot(root),'publication_confirmed');check.checked=true;await check.fire('change');await action(publicationRoot(root),'approve').fire('click');await button(root,'별도 발행 승인 처리 상태 조회').fire('click');await button(root,'별도 발행 승인 처리 상태 조회').fire('click');
 assert.match(root.textContent,/처리 상태 조회에 실패/);assert.equal(get(root,'close_publication_approve').disabled,true);assert.equal(button(root,'별도 발행 승인 충돌 요청 로컬 종료').disabled,true);
});


test('R1 highwater 불확실 읽기 근거는 pending 없는 새 요청에도 적용하고 조회는 계속 허용한다',async()=>{
 const {root}=await conflictable({getRun:async()=>({run_id:'publish-run',state:'unknown',deliveries:[{id:'delivery-1',version:4,state:'unknown',remote_uncertain:true,context_hash:'d'.repeat(64)}]})});await action(publicationRoot(root),'refresh').fire('click');
 for(const name of ['request','observe','admit','approve'])assert.equal(action(publicationRoot(root),name).disabled,true);assert.equal(action(publicationRoot(root),'refresh').disabled,false);
});

async function selectExecution(root,name,value) {
 const select=get(root,name);assert.ok(!select.disabled);select.value=value;await select.fire('change');
}

for(const signal of ['unknown','remote_id','conflict'])test(`R2 ${signal} 근거는 선택 해제·다른 계획·재선택 뒤에도 원래 실행에 남는다`,async()=>{
 let requests=0,reads=0;const readIds=[];
 const plans=['delivery-1','delivery-2'].map(id=>({id,content_id:content.id,revision:2,manifest_hash:content.manifest_hash,connection_id:'personal.youtube',version:4,status:'ready'}));
 const {root}=await conflictable({listDeliveries:async()=>({items:plans}),request:async()=>({run_id:`publish-run-${++requests}`,state:'queued'}),getRun:async id=>{
  readIds.push(id);reads++;
  return {run_id:id,state:signal==='unknown'&&reads===1?'unknown':'waiting',deliveries:[{id:'delivery-1',run_id:id,version:reads>2?3:4,state:'queued',context_hash:(signal==='conflict'&&reads===2?'b':'a').repeat(64),...(signal==='remote_id'&&reads===1?{remote_id:'kept-remote'}:{})}]};
 }});
 await action(publicationRoot(root),'refresh').fire('click');
 if(signal==='conflict')await action(publicationRoot(root),'refresh').fire('click');
 assert.equal(action(publicationRoot(root),'request').disabled,true);
 await selectExecution(root,'planned_delivery','');
 await selectExecution(root,'planned_delivery','delivery-2');await selectExecution(root,'publication_job','publish');
 assert.equal(action(publicationRoot(root),'request').disabled,false,'다른 계획은 불확실 근거를 상속하지 않는다');
 assert.equal(action(publicationRoot(root),'refresh').disabled,true,'다른 계획에 이전 run을 연결하지 않는다');
 assert.doesNotMatch(publicationRoot(root).textContent,/publish-run-1|kept-remote/);
 await selectExecution(root,'planned_delivery','delivery-1');await selectExecution(root,'publication_job','publish');
 assert.equal(action(publicationRoot(root),'request').disabled,true,'동일 계획 재선택은 미해소 근거를 버리지 않는다');
 assert.equal(action(publicationRoot(root),'refresh').disabled,false);
 await action(publicationRoot(root),'request').fire('click');assert.equal(requests,1);
 await action(publicationRoot(root),'refresh').fire('click');await action(publicationRoot(root),'refresh').fire('click');
 assert.ok(readIds.every(id=>id==='publish-run-1'));
 assert.match(publicationRoot(root).textContent,/배포: delivery-1 · 버전: 4/);
 for(const name of ['request','observe','admit','approve'])assert.equal(action(publicationRoot(root),name).disabled,true);
 if(signal==='remote_id')assert.match(publicationRoot(root).textContent,/kept-remote/);
 if(signal==='conflict')assert.match(publicationRoot(root).textContent,/동일 버전 조회 결과가 불일치/);
});

test('R2 실제 편집기의 다른 원고·과거 버전 왕복은 같은 원고 계획의 원격 근거를 지우지 않는다',async()=>{
 const readIds=[];let requests=0;
 const {root,workspace,document}=await conflictable({request:async()=>({run_id:`publish-run-${++requests}`,state:'queued'}),getRun:async id=>{
  readIds.push(id);return {run_id:id,state:'unknown',deliveries:[{id:'delivery-1',run_id:id,version:4,state:'unknown',remote_id:'navigation-remote'}]};
 }});
 await action(publicationRoot(root),'refresh').fire('click');await selectExecution(root,'planned_delivery','');
 const previous=globalThis.document;globalThis.document=document;
 try {
  const {createContentEditor}=await import(pathToFileURL(join(staged,'content_editor.js')));
  const api={getContent:async(id,revision=2)=>({...content,id,revision,manifest_hash:revision===2?content.manifest_hash:'b'.repeat(64)}),listRevisions:async()=>({items:[{revision:1},{revision:2}]}),listConnections:async()=>({items:[]}),listDeliveries:async()=>({items:[]})};
  const editor=createContentEditor({api,writable:()=>true,execution:workspace});
  await editor.open({id:content.id,revision:1,source:'managed'});
  assert.doesNotMatch(editor.element.textContent,/navigation-remote|publish-run-1/);
  await editor.open({id:'content-2',revision:2,source:'managed'});
  assert.doesNotMatch(editor.element.textContent,/navigation-remote|publish-run-1/);
  await editor.open({id:content.id,revision:2,source:'managed'});
  await selectExecution(editor.element,'planned_delivery','delivery-1');await selectExecution(editor.element,'publication_job','publish');
  assert.match(publicationRoot(editor.element).textContent,/navigation-remote/);
  assert.equal(action(publicationRoot(editor.element),'request').disabled,true);
  await action(publicationRoot(editor.element),'request').fire('click');assert.equal(requests,1);
  await action(publicationRoot(editor.element),'refresh').fire('click');assert.deepEqual(readIds,['publish-run-1','publish-run-1']);
 } finally {for(let i=0;i<10;i++)await Promise.resolve();globalThis.document=previous;}
});
