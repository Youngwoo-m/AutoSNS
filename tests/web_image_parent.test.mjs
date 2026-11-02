import test from 'node:test';
import assert from 'node:assert/strict';
import {createContentEditor} from '../ax-console/app/web/content_editor.js';
import {harness,all} from './helpers/execution_dom.mjs';
const tick=async()=>{for(let i=0;i<80;i++)await Promise.resolve();};
const content={id:'managed_image_fixture',source:'managed',revision:1,manifest_hash:'a'.repeat(64),owner_account_id:'personal',title:'이미지 원고',kind:'card',series:'',status:'drafting',original:'원문',variants:[],sources:[],reviews:[],assets:[]};
const field=(root,name)=>all(root).find(n=>n.getAttribute('data-image-field')===name);
const action=(root,name)=>all(root).find(n=>n.getAttribute('data-image-action')===name);
const button=(root,name)=>all(root).find(n=>n.tagName==='button'&&n.textContent===name);
async function setup(post){
 const {document}=harness();globalThis.document=document;const calls=[];
 globalThis.fetch=async(url,options)=>{calls.push([url,options]);let value={items:[]};
  if(url.includes('image-production'))value={provider_id:'local-card',service_available:true,execution_enabled:true,review_status:'not_checked'};
  else if(url.includes('image-tasks')&&options.method==='POST')return post();
  else if(url.includes('/media-plan'))value={content_id:content.id,content_revision:1,manifest_hash:content.manifest_hash,owner_account_id:'personal',plan_revision:0,plan:{exam:'콘텐츠',field:'제목',source:'',footer:'',disclosure:'AI',voice_asset_id:null,scenes:[]},inputs_ready:false,blockers:[],execution_enabled:false,review_status:'not_checked'};
  return {ok:true,status:200,json:async()=>structuredClone(value)};
 };
 const api={getContent:async()=>structuredClone(content),listRevisions:async()=>({items:[{revision:1}]}),listConnections:async()=>({items:[]}),listDeliveries:async()=>({items:[]})};
 const editor=createContentEditor({api,writable:()=>true});await editor.open(content);await tick();
 const details=all(editor.element).find(n=>n.tagName==='details'&&n.className.includes('image-task'));assert.ok(details);details.open=true;await details.fire('toggle');await tick();
 return {editor,document,calls};
}
test('이미지 입력은 자기 제작 버튼과 포커스를 보존하고 원고·다른 제작을 잠근다',async()=>{
 const h=await setup();const body=field(h.editor.element,'body');body.focus();body.value='첫 단계\n둘째 단계';await body.fire('input');
 assert.equal(h.editor.hasUnsavedChanges(),true);assert.equal(button(h.editor.element,'원본 저장').disabled,true);assert.equal(button(h.editor.element,'제작 계획 저장').disabled,true);assert.equal(action(h.editor.element,'create').disabled,false);assert.equal(h.document.activeElement,body);
 await action(h.editor.element,'discard').fire('click');assert.equal(h.editor.hasUnsavedChanges(),false);assert.equal(button(h.editor.element,'원본 저장').disabled,false);
});
test('이미지 전송 중 버전 변경을 막고 충돌 뒤 입력을 유지한다',async()=>{
 let resolve;const h=await setup(()=>new Promise(r=>{resolve=r;}));const body=field(h.editor.element,'body');body.value='입력 보존';await body.fire('input');
 const request=action(h.editor.element,'create').fire('click');assert.equal(h.editor.isBusy(),true);assert.equal(button(h.editor.element,'원본 저장').disabled,true);
 resolve({ok:false,status:409});await request;assert.equal(h.editor.isBusy(),false);assert.equal(h.editor.hasUnsavedChanges(),true);assert.equal(field(h.editor.element,'body').value,'입력 보존');
});
