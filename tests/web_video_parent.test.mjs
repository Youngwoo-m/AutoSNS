import test from 'node:test';
import assert from 'node:assert/strict';
import {createContentEditor} from '../ax-console/app/web/content_editor.js';
import {harness,all} from './helpers/execution_dom.mjs';
const tick=async()=>{for(let i=0;i<60;i++)await Promise.resolve();};
const original={id:'managed_video_fixture',source:'managed',revision:1,manifest_hash:'hash-one',owner_account_id:'dept',title:'학과 영상 원고',kind:'short',series:'',status:'drafting',original:'보존할 원문',variants:[],sources:[],assets:[],reviews:[]};
const body={exam:'시험',field:'분야',source:'',footer:'',disclosure:'AI 합성 음성',voice_asset_id:'wav',scenes:[{asset_id:'img1',kind:'diorama',seconds:3,title:'1',caption:'1'},{asset_id:'img2',kind:'diorama',seconds:3,title:'2',caption:'2'}]};
const response=(value,status=200)=>({ok:status<400,status,json:async()=>structuredClone(value)});
const button=(root,label)=>all(root).find(n=>n.tagName==='button'&&n.textContent===label);
const action=(root,name)=>all(root).find(n=>n.getAttribute('data-video-action')===name);
const input=(root,text)=>all(root).find(n=>n.tagName==='label'&&n.textContent.trim()===text)?.children.find(n=>n.tagName==='input'||n.tagName==='textarea');
async function setup({post}={}){
  const {document}=harness();globalThis.document=document;let latest=1,planVersion=2,task=null;const calls=[],writes=[];
  const plan=(revision=1)=>({content_id:original.id,content_revision:revision,manifest_hash:revision===1?'hash-one':'hash-two',owner_account_id:'dept',plan_revision:planVersion,plan:body,inputs_ready:true,blockers:[],execution_enabled:false,review_status:'not_checked'});
  globalThis.fetch=async(url,o)=>{
    calls.push([url,o]);
    if(o.method==='POST'&&url.includes('/media-plan')){planVersion++;return response({...plan(),plan:JSON.parse(o.body).plan});}
    if(o.method==='POST'){
      if(post)return post(url,o);
      task={task_id:'video1',state:'queued',reason_code:null,content_id:original.id,input_revision:1,plan_revision:planVersion,output_revision:null,asset_id:null,review_status:'not_checked'};return response(task);
    }
    if(url==='/api/v2/video/capabilities')return response({provider_id:'remotion-local',service_available:true,execution_enabled:true,review_status:'not_checked'});
    if(url.split('?')[0]==='/api/v2/voicebox/capabilities')return response({provider_id:'voicebox-local',service_available:false,execution_enabled:false,readiness:'not_checked',external_fallback:false});
    if(url.includes('/media-plan'))return response(plan(Number(new URL('http://fixture'+url).searchParams.get('revision'))));
    if(url.includes('/video-tasks'))return response({items:task?[task]:[]});
    return response({items:[]});
  };
  const api={getContent:async(_id,revision)=>({...structuredClone(original),revision:revision||latest,manifest_hash:(revision||latest)===1?'hash-one':'hash-two',assets:!revision&&latest===2?[{id:'mp4',filename:'short.mp4',media_type:'video/mp4',size:100}]:[]}),listRevisions:async()=>({items:Array.from({length:latest},(_,i)=>({revision:i+1}))}),listConnections:async()=>({items:[]}),listDeliveries:async()=>({items:[]}),updateContent:async(...args)=>{writes.push(args);return original;}};
  const editor=createContentEditor({api,writable:()=>true});await editor.open(original);await tick();
  return {editor,document,calls,writes,complete(){latest=2;task={...task,state:'completed',output_revision:2,asset_id:'mp4'};}};
}

test('원문·음성 대본의 미저장 변경은 영상 접수를 잠그고 입력 포커스를 보존한다',async()=>{
  const h=await setup();assert.equal(action(h.editor.element,'enqueue').disabled,false);
  const field=input(h.editor.element,'원문');field.focus();field.value='미저장 원문';await field.fire('input');
  assert.equal(action(h.editor.element,'enqueue').disabled,true);assert.equal(h.document.activeElement,field);
  const other=await setup();const voice=all(other.editor.element).find(n=>n.getAttribute('data-voice-field')==='script');voice.value='음성 초안';await voice.fire('input');
  assert.equal(action(other.editor.element,'enqueue').disabled,true);assert.equal(other.calls.filter(([,o])=>o.method==='POST').length,0);
});

test('계획을 저장한 뒤 명시 재조회한 계획 버전으로만 영상 접수한다',async()=>{
  const h=await setup();const exam=input(h.editor.element,'시험');exam.value='수정 시험';await exam.fire('input');
  assert.equal(action(h.editor.element,'enqueue').disabled,true);
  await button(h.editor.element,'제작 계획 저장').fire('click');await action(h.editor.element,'reload').fire('click');
  await action(h.editor.element,'enqueue').fire('click');
  const post=h.calls.find(([url,o])=>o.method==='POST'&&url.includes('/video-tasks'));
  assert.deepEqual(JSON.parse(post[1].body),{expected_revision:1,expected_plan_revision:3});assert.equal(h.writes.length,0);
});

test('영상 요청 중 부모 버전 변경을 막고 충돌 후 저장된 원고와 계획을 유지한다',async()=>{
  let resolve;const h=await setup({post:()=>new Promise(r=>{resolve=r;})});
  const pending=action(h.editor.element,'enqueue').fire('click');assert.equal(h.editor.isBusy(),true);assert.equal(button(h.editor.element,'원본 저장').disabled,true);
  resolve(response({},409));await pending;assert.equal(h.editor.isBusy(),false);assert.equal(input(h.editor.element,'원문').value,'보존할 원문');assert.equal(input(h.editor.element,'시험').value,'시험');assert.equal(h.writes.length,0);
});

test('영상 완료는 원고 자동 전환 없이 최신 MP4 버전을 명시적으로 열게 한다',async()=>{
  const h=await setup();await action(h.editor.element,'enqueue').fire('click');h.complete();await action(h.editor.element,'reload').fire('click');await tick();
  assert.match(h.editor.element.textContent,/최신 버전을 열어 MP4를 확인/);assert.match(h.editor.element.textContent,/원본 소유: 학과 .*버전 1/);
  assert.equal(button(h.editor.element,'원본 저장').disabled,true);assert.equal(h.writes.length,0);
  await button(h.editor.element,'최신 버전 열기').fire('click');await tick();
  assert.match(h.editor.element.textContent,/원본 소유: 학과 .*버전 2/);assert.match(h.editor.element.textContent,/short.mp4/);
});
