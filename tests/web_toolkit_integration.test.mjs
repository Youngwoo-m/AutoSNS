import test from 'node:test';
import assert from 'node:assert/strict';
import {loadWebModule,webSource} from './helpers/staged_web.mjs';
const app=webSource('app.js'),editor=webSource('content_editor.js');
test('four account workspaces preserve existing screens as publishing submenus',()=>{const html=webSource('index.html');assert.equal((html.match(/data-route=/g)||[]).length,4);assert.equal((html.match(/data-scope=/g)||[]).length,0);assert.match(app,/subNav/);assert.doesNotMatch(html,/data-view="toolkit"/);});
test('accounts planning analytics detail compose toolkit beside existing panels',()=>{assert.match(app,/createToolkitPanel/);for(const section of ['accounts','planning','analytics','schedule'])assert.match(app,new RegExp(`toolkitSurface\\('${section}'`));assert.match(app,/metrics\.render/);assert.match(app,/integrationSettings\.element/);});
test('editor stage uses clean hash context and existing full payload CAS',()=>{for(const text of ['inputHash','editorDirty','toolkit-stage','stageCandidate','toContentPayload','expected_revision'])assert.ok(editor.includes(text),text);assert.match(editor,/session\.draft\.variants\[patch\.variant\.index\]\.text=patch\.variant\.text/);assert.doesNotMatch(editor,/session\.draft\.original=patch/);});
import {harness,all,field} from './helpers/execution_dom.mjs';
const {createContentEditor}=await loadWebModule('content_editor.js');
const tick=async()=>{for(let n=0;n<12;n++)await Promise.resolve();};
const button=(root,label)=>all(root).find(n=>n.tagName==='button'&&n.textContent===label);
const doc={id:'managed_fixture',source:'managed',owner_account_id:'personal',revision:1,manifest_hash:'hash-one',title:'원제목',kind:'article',series:'시리즈',status:'drafting',original:'원문',variants:[{destination_account_id:'personal',platform:'youtube',text:'변환문'},{destination_account_id:'dept',platform:'youtube',text:'보존할 학과 변환문'}],sources:[{url:'https://example.com',note:'출처'}],assets:[],reviews:[]};
async function opened(fetcher){
 const {document}=harness();globalThis.document=document;
 globalThis.CustomEvent=class {constructor(type,{detail}){this.type=type;this.detail=detail;}};
 globalThis.fetch=fetcher;
 const writes=[];const api={getContent:async()=>structuredClone(doc),listRevisions:async()=>({items:[{revision:1}]}),listConnections:async()=>({items:[]}),listDeliveries:async()=>({items:[]}),updateContent:async(id,payload)=>{writes.push([id,payload]);return {...structuredClone(doc),...payload,revision:2,manifest_hash:'hash-two',reviews:[]};}};
 const editor=createContentEditor({api,writable:()=>true});await editor.open(doc);await tick();
 const panel=all(editor.element).find(n=>n.className==='toolkit-panel');panel.dispatchEvent=e=>{for(const fn of panel.listeners.get(e.type)||[])fn(e);return true;};
 const connection=field(editor.element,'toolkit_connection_id');connection.value='c';await connection.fire('change');
 return {editor,document,writes,panel};
}
test('actual service-shaped candidate stages tags in selected variant only and saves full CAS payload',async()=>{
 const h=await opened(async()=>({ok:true,json:async()=>({destination_account_id:'personal',platform:'youtube',candidates:[{id:'a',title:'후보 제목',hashtags:['#측량'],reasons:['입력 어휘']}]})}));
 await button(h.editor.element,'제목·태그 후보 미리보기').fire('click');
 assert.equal(h.writes.length,0);
 const selected=field(h.editor.element,'toolkit_variant_index');selected.value='0';await selected.fire('change');
 await button(h.editor.element,'후보 1 제목·태그를 선택 변환문에 반영').fire('click');
 assert.equal(h.editor.hasUnsavedChanges(),true);assert.equal(h.writes.length,0);
 await all(h.editor.element).find(n=>n.tagName==='form').fire('submit');
 const payload=h.writes[0][1];assert.equal(payload.expected_revision,1);assert.equal(payload.title,'후보 제목');assert.equal(payload.original,doc.original);assert.deepEqual(payload.variants,[{...doc.variants[0],text:'변환문\n\n#측량'},doc.variants[1]]);assert.deepEqual(payload.sources,doc.sources);assert.equal(payload.series,doc.series);assert.equal(payload.status,doc.status);
});
test('actual editor dirty typing retains focus and late preview cannot stage',async()=>{
 let resolve;const h=await opened(()=>new Promise(r=>resolve=r));
 const pending=button(h.editor.element,'제목·태그 후보 미리보기').fire('click');
 const title=all(h.editor.element).find(n=>n.tagName==='label'&&n.children[0]?.textContent==='제목').children[1];title.focus();title.value='사용자가 입력한 제목';await title.fire('input');
 assert.equal(h.document.activeElement,title);
 resolve({ok:true,json:async()=>({candidates:[{id:'old',title:'늦은 후보'}]})});await pending;
 assert.equal(h.document.activeElement,title);assert.equal(title.value,'사용자가 입력한 제목');assert.equal(button(h.editor.element,'후보 1 제목을 초안에 반영'),undefined);assert.equal(h.writes.length,0);
});
test('actual toolkit surfaces scope capabilities/research/CSV/schedule without automatic HTTP',async()=>{
 const {createToolkitController}=await loadWebModule('toolkit_controller.js'),{createToolkitPanel}=await loadWebModule('toolkit_panel.js');const {document}=harness();let calls=0;
 for(const section of ['accounts','planning','analytics','schedule']){
  const controller=createToolkitController({api:new Proxy({},{get:()=>()=>calls++})}),panel=createToolkitPanel({controller,document});panel.render({section,context:{account:'personal'}});
  assert.equal(Boolean(field(panel.element,'toolkit_csv_text')),section==='analytics');assert.equal(Boolean(field(panel.element,'toolkit_delivery_id')),section==='schedule');assert.equal(Boolean(button(panel.element,'저장 근거로 조사')),section==='planning');
 }assert.equal(calls,0);
});
test('320px layout rule and 1280px width contract preserve bounded inputs',()=>{const css=webSource('styles.css');assert.match(css,/@media \(max-width: 400px\)/);assert.match(css,/\.toolkit-panel input[\s\S]*max-width:100%/);assert.match(css,/\.toolkit-panel :focus-visible/);});
import {execFileSync} from 'node:child_process';
const realContracts=JSON.parse(execFileSync(process.env.TOOLKIT_TEST_PYTHON||'python3',['-m','tests.helpers.toolkit_contract_fixture'],{cwd:new URL('../',import.meta.url),env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}}));
test('actual local functions findings research evidence and connection labels are visible',async()=>{
 const {createToolkitController}=await loadWebModule('toolkit_controller.js'),{createToolkitPanel}=await loadWebModule('toolkit_panel.js');
 const {document}=harness();const api={capabilities:async()=>realContracts.capabilities,packagingPreview:async()=>realContracts.packaging,researchPreview:async()=>realContracts.research,thumbnailInspect:async()=>realContracts.image};
 const controller=createToolkitController({api}),panel=createToolkitPanel({controller,document});
 const context={account:'personal',contentId:'content',revision:2,inputHash:'h',connectionId:'c',editorDirty:false,variants:[{destination_account_id:'personal',platform:'youtube',text:'본문'}],assets:[{id:'image',filename:'손상 이미지',media_type:'image/png'}]};
 controller.setContext(context);
 for(const kind of ['capabilities','packaging','research','thumbnailInspect'])await controller.preview(kind,{asset_id:'image'});
 panel.render({section:'editor',context,writable:true});const text=panel.element.textContent;
 for(const value of ['#키워드','제목에 포함되지 않은','channel','youtube.views','표본 수: 3','동일 대상·정의·기준·기간','관측 근거: a','추가 비용 없음'])assert.ok(text.includes(value),value);
 assert.ok(text.includes(realContracts.image.status==='error'?'처리 상태: 오류':'처리 상태: 사용 불가'));
 // Python without Pillow truthfully reports decoder unavailable; Pillow environment reports damaged bytes.
 assert.ok(text.includes('이미지를 해석할 수 없습니다')||text.includes('이미지 해석 환경 미준비'));
 const connections=field(panel.element,'toolkit_connection_id');assert.ok(connections.children.some(option=>option.value==='d'&&option.textContent.includes('학과')&&option.textContent.includes('youtube')));
 assert.equal(field(panel.element,'toolkit_preset_id').value,'landscape.v1');
 api.researchPreview=async()=>realContracts.missing;await controller.preview('research');panel.render({section:'planning',context});assert.match(panel.element.textContent,/표본 3건 미만/);
});
test('CSV preview distinguishes equal values across publication time and interval',async()=>{
 const {createToolkitController}=await loadWebModule('toolkit_controller.js'),{createToolkitPanel}=await loadWebModule('toolkit_panel.js');const {document}=harness();
 const rows=['video-a','video-b'].map((remote_id,index)=>({remote_id,platform:'youtube',target_id:'target',owner_account_id:null,destination_account_id:'personal',status:'legacy_reported',definition_id:'manual.youtube.counts',basis:'interval',period:{start:`2026-10-${20+index}T00:00:00+09:00`,end:`2026-10-${21+index}T00:00:00+09:00`},observed_at:`2026-10-${22+index}T00:00:00+09:00`,values:{views:10}}));
 const controller=createToolkitController({api:{csvPreview:async()=>({status:'completed',rows})}}),panel=createToolkitPanel({controller,document});controller.setContext({account:'personal'});await controller.preview('csv');panel.render({section:'analytics',context:{account:'personal'}});
 for(const row of rows)for(const value of [row.remote_id,row.observed_at,row.period.start,row.definition_id])assert.ok(panel.element.textContent.includes(value),value);
 assert.match(panel.element.textContent,/수동 관측 · 게시 검증 아님/);
});
test('delivery selection snapshot cannot mutate the existing editor list',async()=>{
 const {createDeliveryEditor}=await loadWebModule('delivery_editor.js');const {document}=harness();globalThis.document=document;
 const existing={id:'immutable-delivery',state:'draft',context:{platform:'youtube',target_id:'target'}};
 const delivery=createDeliveryEditor({api:{listConnections:async()=>({items:[]}),listDeliveries:async()=>({items:[existing]})},writable:()=>false});
 await delivery.open(doc);const snapshot=delivery.getItems();snapshot[0].id='forged';snapshot[0].context.target_id='changed';snapshot.push({id:'extra'});
 assert.deepEqual(delivery.getItems(),[existing]);
});
