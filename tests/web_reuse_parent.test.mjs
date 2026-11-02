import test from 'node:test';
import assert from 'node:assert/strict';
import {createContentEditor} from '../ax-console/app/web/content_editor.js';
import {harness,all} from './helpers/execution_dom.mjs';
const tick=async()=>{for(let i=0;i<70;i++)await Promise.resolve();};
const content={id:'managed_reuse_fixture',source:'managed',revision:1,manifest_hash:'h'.repeat(64),owner_account_id:'personal',title:'이미지 원고',kind:'short',series:'',status:'drafting',original:'보존할 원문',variants:[],sources:[],reviews:[],assets:[{id:'img1',filename:'one.png',media_type:'image/png',sha256:'a'.repeat(64),size:12},{id:'img2',filename:'two.png',media_type:'image/png',sha256:'b'.repeat(64),size:12}]};
const row=asset=>({content_id:content.id,content_revision:1,manifest_hash:content.manifest_hash,owner_account_id:'personal',asset_id:asset.id,sha256:asset.sha256,approval_revision:0,approved_revision:null,rights_confirmed:false,visual_checked:false,notes:'',status:'not_approved',review_method:'manual'});
const action=(root,name)=>all(root).find(n=>n.getAttribute('data-reuse-action')===name);
const field=(root,name)=>all(root).find(n=>n.getAttribute('data-reuse-field')===name&&n.getAttribute('data-reuse-for')==='img1');
const button=(root,label)=>all(root).find(n=>n.tagName==='button'&&n.textContent===label);
async function setup({post}={}){
  const {document}=harness();globalThis.document=document;const calls=[],writes=[];let records=content.assets.map(row);
  globalThis.fetch=async(url,options)=>{
    calls.push([url,options]);let value;
    if(url.includes('/reuse-approvals')){
      if(options.method==='POST'){
        if(post)return post(url,options);
        const body=JSON.parse(options.body),current=records.find(r=>r.asset_id===body.asset_id);
        value={...current,approval_revision:current.approval_revision+1,approved_revision:1,rights_confirmed:body.rights_confirmed,visual_checked:body.visual_checked,notes:body.notes,status:body.rights_confirmed&&body.visual_checked?'approved':'not_approved'};
        records=records.map(r=>r.asset_id===value.asset_id?value:r);
      }else value={items:records};
    }else if(url.endsWith('/video/capabilities'))value={provider_id:'remotion-local',service_available:true,execution_enabled:true,review_status:'not_checked'};
    else if(url.endsWith('/voicebox/capabilities'))value={provider_id:'voicebox-local',service_available:false,execution_enabled:false,readiness:'not_checked',external_fallback:false};
    else if(url.includes('/media-plan'))value={content_id:content.id,content_revision:1,manifest_hash:content.manifest_hash,owner_account_id:'personal',plan_revision:1,plan:{exam:'시험',field:'분야',source:'',footer:'',disclosure:'AI 합성 음성',voice_asset_id:null,scenes:[]},inputs_ready:true,blockers:[],execution_enabled:false,review_status:'not_checked'};
    else value={items:[]};
    return {ok:true,status:200,json:async()=>structuredClone(value)};
  };
  const api={getContent:async()=>structuredClone(content),listRevisions:async()=>({items:[{revision:1}]}),listConnections:async()=>({items:[]}),listDeliveries:async()=>({items:[]}),updateContent:async(...args)=>writes.push(args)};
  const editor=createContentEditor({api,writable:()=>true});await editor.open(content);await tick();return {editor,document,calls,writes};
}
async function checked(root,name){const input=field(root,name);input.checked=true;await input.fire('change');}

test('이미지 확인 입력은 부모·다른 제작을 잠그고 자기 저장과 메모 포커스는 유지한다',async()=>{
  const h=await setup();await checked(h.editor.element,'rights');await checked(h.editor.element,'visual');
  const notes=field(h.editor.element,'notes');notes.focus();notes.value='수동 확인';await notes.fire('input');
  assert.equal(h.editor.hasUnsavedChanges(),true);assert.equal(button(h.editor.element,'원본 저장').disabled,true);assert.equal(button(h.editor.element,'제작 계획 저장').disabled,true);assert.equal(button(h.editor.element,'영상 제작 요청').disabled,true);
  assert.equal(action(h.editor.element,'save').disabled,false);assert.equal(h.document.activeElement,notes);
  await action(h.editor.element,'save').fire('click');assert.equal(h.editor.hasUnsavedChanges(),false);assert.equal(button(h.editor.element,'원본 저장').disabled,false);
  const posts=h.calls.filter(([,o])=>o.method==='POST');assert.equal(posts.length,1);assert.match(posts[0][0],/reuse-approvals/);assert.equal(h.writes.length,0);
});
test('부모 원문이 미저장이면 확인 기록의 입력·저장을 막는다',async()=>{
  const h=await setup();const label=all(h.editor.element).find(n=>n.tagName==='label'&&n.textContent.trim()==='원문');const original=label.children.find(n=>n.tagName==='textarea');original.value='미저장';await original.fire('input');
  assert.equal(field(h.editor.element,'rights').disabled,true);assert.equal(action(h.editor.element,'save').disabled,true);assert.equal(h.calls.filter(([,o])=>o.method==='POST').length,0);
});
test('저장 중 원고 전환을 막고 충돌 뒤 확인 입력을 보존한다',async()=>{
  let resolve;const h=await setup({post:()=>new Promise(r=>{resolve=r;})});await checked(h.editor.element,'rights');
  const save=action(h.editor.element,'save').fire('click');assert.equal(h.editor.isBusy(),true);assert.equal(button(h.editor.element,'원본 저장').disabled,true);
  resolve({ok:false,status:409});await save;assert.equal(h.editor.isBusy(),false);assert.equal(h.editor.hasUnsavedChanges(),true);assert.equal(field(h.editor.element,'rights').checked,true);
});
