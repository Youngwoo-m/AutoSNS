import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const root=new URL('../',import.meta.url),artifact=new URL('.superpowers/sdd/2026-10-31-local-sns-toolkit/web-artifacts/',root);
const app=readFileSync(new URL('app.js',artifact),'utf8');
const editor=readFileSync(new URL('content_editor.js',artifact),'utf8');
test('existing nine navigation destinations preserved without toolkit top menu',()=>{const html=readFileSync(new URL('index.html',artifact),'utf8');assert.equal((html.match(/data-view=/g)||[]).length,9);assert.doesNotMatch(html,/data-view="toolkit"/);});
test('accounts planning analytics detail compose toolkit beside existing panels',()=>{assert.match(app,/createToolkitPanel/);for(const section of ['accounts','planning','analytics','schedule'])assert.match(app,new RegExp(`toolkitSurface\\('${section}'`));assert.match(app,/metrics\.render/);assert.match(app,/integrationSettings\.element/);});
test('editor stage uses clean hash context and existing full payload CAS',()=>{for(const text of ['inputHash','editorDirty','toolkit-stage','stageCandidate','toContentPayload','expected_revision'])assert.ok(editor.includes(text),text);assert.match(editor,/session\.draft\.original=patch\.body/);});
import {loadWebModule,webSource} from './helpers/staged_web.mjs';
import {harness,all,field} from './helpers/execution_dom.mjs';
const {createContentEditor}=await loadWebModule('content_editor.js');
const tick=async()=>{for(let n=0;n<12;n++)await Promise.resolve();};
const button=(root,label)=>all(root).find(n=>n.tagName==='button'&&n.textContent===label);
const doc={id:'managed_fixture',source:'managed',owner_account_id:'personal',revision:1,manifest_hash:'hash-one',title:'원제목',kind:'article',series:'시리즈',status:'drafting',original:'원문',variants:[{destination_account_id:'personal',platform:'youtube',text:'변환문'}],sources:[{url:'https://example.com',note:'출처'}],assets:[],reviews:[]};
async function opened(fetcher){
 const {document}=harness();globalThis.document=document;
 globalThis.CustomEvent=class {constructor(type,{detail}){this.type=type;this.detail=detail;}};
 globalThis.fetch=fetcher;
 const writes=[];const api={getContent:async()=>structuredClone(doc),listRevisions:async()=>({items:[{revision:1}]}),listConnections:async()=>({items:[]}),listDeliveries:async()=>({items:[]}),updateContent:async(id,payload)=>{writes.push([id,payload]);return {...structuredClone(doc),...payload,revision:2,manifest_hash:'hash-two',reviews:[]};}};
 const editor=createContentEditor({api,writable:()=>true});await editor.open(doc);await tick();
 const panel=all(editor.element).find(n=>n.className==='toolkit-panel');panel.dispatchEvent=e=>{for(const fn of panel.listeners.get(e.type)||[])fn(e);return true;};
 const connection=field(editor.element,'toolkit_connection_id');connection.value='c';await connection.fire('input');
 return {editor,document,writes,panel};
}
test('actual editor CustomEvent stages title/body only and saves full CAS payload',async()=>{
 const h=await opened(async()=>({ok:true,json:async()=>({candidates:[{id:'a',title:'후보 제목',variants:[{id:'v',text:'선택 본문'}]}]})}));
 await button(h.editor.element,'제목·본문 후보 미리보기').fire('click');
 assert.equal(h.writes.length,0);
 await button(h.editor.element,'선택한 본문을 초안에 반영').fire('click');
 assert.equal(h.editor.hasUnsavedChanges(),true);assert.equal(h.writes.length,0);
 await all(h.editor.element).find(n=>n.tagName==='form').fire('submit');
 const payload=h.writes[0][1];assert.equal(payload.expected_revision,1);assert.equal(payload.title,'후보 제목');assert.equal(payload.original,'선택 본문');assert.deepEqual(payload.variants,doc.variants);assert.deepEqual(payload.sources,doc.sources);assert.equal(payload.series,doc.series);assert.equal(payload.status,doc.status);
});
test('actual editor dirty typing retains focus and late preview cannot stage',async()=>{
 let resolve;const h=await opened(()=>new Promise(r=>resolve=r));
 const pending=button(h.editor.element,'제목·본문 후보 미리보기').fire('click');
 const title=all(h.editor.element).find(n=>n.tagName==='label'&&n.children[0]?.textContent==='제목').children[1];title.focus();title.value='사용자가 입력한 제목';await title.fire('input');
 assert.equal(h.document.activeElement,title);
 resolve({ok:true,json:async()=>({candidates:[{id:'old',title:'늦은 후보'}]})});await pending;
 assert.equal(h.document.activeElement,title);assert.equal(title.value,'사용자가 입력한 제목');assert.equal(button(h.editor.element,'초안에 반영'),undefined);assert.equal(h.writes.length,0);
});
test('actual toolkit surfaces scope capabilities/research/CSV/schedule without automatic HTTP',async()=>{
 const {createToolkitController}=await loadWebModule('toolkit_controller.js'),{createToolkitPanel}=await loadWebModule('toolkit_panel.js');const {document}=harness();let calls=0;
 for(const section of ['accounts','planning','analytics','schedule']){
  const controller=createToolkitController({api:new Proxy({},{get:()=>()=>calls++})}),panel=createToolkitPanel({controller,document});panel.render({section,context:{account:'personal'}});
  assert.equal(Boolean(field(panel.element,'toolkit_csv_text')),section==='analytics');assert.equal(Boolean(field(panel.element,'toolkit_delivery_id')),section==='schedule');assert.equal(Boolean(button(panel.element,'저장 근거로 조사')),section==='planning');
 }assert.equal(calls,0);
});
test('320px layout rule and 1280px width contract preserve bounded inputs',()=>{const css=webSource('styles.css');assert.match(css,/@media \(max-width: 400px\)/);assert.match(css,/\.toolkit-panel input[\s\S]*max-width:100%/);assert.match(css,/\.toolkit-panel :focus-visible/);});
