import test from 'node:test';
import assert from 'node:assert/strict';
import {createContentEditor} from '../ax-console/app/web/content_editor.js';
import {harness,all} from './helpers/execution_dom.mjs';
const tick=async()=>{for(let i=0;i<40;i++)await Promise.resolve();};
const original={id:'managed_voice_fixture',source:'managed',revision:1,manifest_hash:'hash-one',owner_account_id:'personal',title:'음성 원고',kind:'short',series:'',status:'drafting',original:'보존할 원문',variants:[],sources:[],assets:[],reviews:[]};
const caps={provider_id:'voicebox-local',service_available:true,execution_enabled:true,readiness:'not_checked',external_fallback:false};
const task=(state='pending')=>({task_id:'voice1',state,reason_code:null,content_id:original.id,input_revision:1,output_revision:state==='completed'?2:null,asset_id:state==='completed'?'wav1':null,seconds:state==='completed'?3:null,review_status:'not_checked',voice_label:'AI 합성 음성',generation_id:'generation1'});
const button=(root,label)=>all(root).find(n=>n.tagName==='button'&&n.textContent===label);
const action=(root,name)=>all(root).find(n=>n.getAttribute('data-voice-action')===name);
const voiceField=(root,name)=>all(root).find(n=>n.getAttribute('data-voice-field')===name);
const input=(root,text)=>all(root).find(n=>n.tagName==='label'&&n.textContent.trim()===text)?.children.find(n=>n.tagName==='input'||n.tagName==='textarea');
async function setup({post}={}){
  const {document}=harness();globalThis.document=document;let latest=1;const calls=[],writes=[];
  globalThis.fetch=async(url,o)=>{
    calls.push([url,o]);
    let value;
    if(o.method==='POST'){
      if(post)return post(url,o);
      if(url.endsWith('/resume')){latest=2;value=task('completed');}else value=task();
    }else if(url.split('?')[0].endsWith('/capabilities'))value=caps;
    else if(url.includes('/voice-tasks'))value={items:[]};
    else value={content_id:original.id,content_revision:1,manifest_hash:original.manifest_hash,owner_account_id:'personal',plan_revision:0,plan:{exam:'',field:'',source:'',footer:'',disclosure:'',voice_asset_id:null,scenes:[]},inputs_ready:false,blockers:[],execution_enabled:false,review_status:'not_checked'};
    return {ok:true,status:200,json:async()=>structuredClone(value)};
  };
  const api={getContent:async(_id,revision)=>({...structuredClone(original),revision:revision||latest,manifest_hash:revision===1?'hash-one':latest===2?'hash-two':'hash-one',assets:!revision&&latest===2?[{id:'wav1',filename:'voice.wav',media_type:'audio/wav',size:44}]:[]}),listRevisions:async()=>({items:Array.from({length:latest},(_,i)=>({revision:i+1}))}),listConnections:async()=>({items:[]}),listDeliveries:async()=>({items:[]}),updateContent:async(...args)=>{writes.push(args);return original;}};
  const editor=createContentEditor({api,writable:()=>true});await editor.open(original);await tick();return {editor,document,calls,writes};
}
test('음성 대본 입력은 부모 저장과 다른 제작 계획을 잠그고 자기 입력 포커스를 보존한다',async()=>{
  const h=await setup();const field=voiceField(h.editor.element,'script');field.focus();field.value='보존할 음성 대본';await field.fire('input');
  assert.equal(h.editor.hasUnsavedChanges(),true);assert.equal(button(h.editor.element,'원본 저장').disabled,true);assert.equal(button(h.editor.element,'제작 계획 저장').disabled,true);
  assert.equal(action(h.editor.element,'create').disabled,false);assert.equal(h.document.activeElement,field);assert.equal(h.editor.element.contains(field),true);
  await action(h.editor.element,'create').fire('click');assert.equal(h.editor.hasUnsavedChanges(),false);assert.equal(h.writes.length,0);
  assert.equal(h.calls.filter(([,o])=>o.method==='POST').length,1);
});
test('부모 원문이나 숏츠 계획의 미저장 입력이 있으면 합성 요청을 막는다',async()=>{
  const h=await setup();const parent=input(h.editor.element,'원문');parent.value='편집 중';await parent.fire('input');assert.equal(action(h.editor.element,'create').disabled,true);
  const other=await setup();const plan=input(other.editor.element,'시험');plan.value='시험';await plan.fire('input');assert.equal(action(other.editor.element,'create').disabled,true);
  assert.equal(other.calls.filter(([,o])=>o.method==='POST').length,0);
});
test('음성 완료 후 원고를 자동 전환하지 않고 새 버전을 명시적으로 연다',async()=>{
  const h=await setup();const field=voiceField(h.editor.element,'script');field.value='대본';await field.fire('input');await action(h.editor.element,'create').fire('click');
  await action(h.editor.element,'resume').fire('click');await tick();
  assert.match(h.editor.element.textContent,/최신 버전을 열어 WAV를 확인/);assert.equal(button(h.editor.element,'원본 저장').disabled,true);
  assert.match(h.editor.element.textContent,/원본 소유: 개인 · 버전 1/);assert.equal(h.writes.length,0);
  await button(h.editor.element,'최신 버전 열기').fire('click');await tick();
  assert.match(h.editor.element.textContent,/원본 소유: 개인 · 버전 2/);assert.match(h.editor.element.textContent,/voice.wav/);
});
test('합성 실패 후 대본과 부모 이탈 보호를 유지한다',async()=>{
  const h=await setup({post:async()=>({ok:false,status:409})});const field=voiceField(h.editor.element,'script');field.value='대본 보존';await field.fire('input');await action(h.editor.element,'create').fire('click');
  assert.equal(voiceField(h.editor.element,'script').value,'대본 보존');assert.equal(h.editor.hasUnsavedChanges(),true);assert.equal(button(h.editor.element,'원본 저장').disabled,true);assert.equal(h.editor.isBusy(),false);
});
test('비활성·오류 상황에서도 명시적으로 입력을 버리면 부모 잠금을 해제한다',async()=>{
  const h=await setup();const field=voiceField(h.editor.element,'script');field.value='버릴 대본';await field.fire('input');
  globalThis.confirm=()=>false;await action(h.editor.element,'discard').fire('click');assert.equal(h.editor.hasUnsavedChanges(),true);
  globalThis.confirm=()=>true;await action(h.editor.element,'discard').fire('click');delete globalThis.confirm;
  assert.equal(h.editor.hasUnsavedChanges(),false);assert.equal(button(h.editor.element,'원본 저장').disabled,false);assert.equal(h.calls.filter(([,o])=>o.method==='POST').length,0);
});
