import test from 'node:test';
import assert from 'node:assert/strict';
import {existsSync,readFileSync} from 'node:fs';
import vm from 'node:vm';
import {createSnapshotLoader} from '../ax-console/app/web/api.js';

import {webSource} from './helpers/staged_web.mjs';
const source=webSource('app.js');
const render=source.slice(source.indexOf('function render() {'),source.indexOf('\nfunction stats('));
const setView=source.slice(source.indexOf('function setView(id) {'),source.indexOf('\n',source.indexOf('function setView(id) {')));
const tick=async()=>{for(let n=0;n<5;n++)await Promise.resolve();};

function harness(){
  const document={body:{tagName:'BODY'},querySelectorAll:()=>[]};document.activeElement=document.body;
  const node=(id,children=[])=>({id,children,focus(){document.activeElement=this;},setAttribute(){}});
  const contains=(root,target)=>root===target||(root.children||[]).some(child=>contains(child,target));
  const root=node('screen-root');
  root.replaceChildren=(...children)=>{if(contains(root,document.activeElement))document.activeElement=document.body;root.children=children;};
  const find=(root,id)=>root.id===id?root:(root.children||[]).map(child=>find(child,id)).find(Boolean);
  const $=selector=>find(root,selector.slice(1));
  const pending=[];
  const request=()=>new Promise((resolve,reject)=>pending.push({resolve,reject}));
  const app=vm.runInNewContext(`
    let state={account:'all',snapshot:null,phase:'idle'},view='today';
    const views={today:[],planning:[]};
    const renderers={today:()=>({}),planning:()=>({})};
    ${render}
    ${setView}
    const loader=createSnapshotLoader(next=>{state=next;render();},{request});
    ({setView,select:loader.select,phase:()=>state.phase});
  `,{document,$,createSnapshotLoader,request,renderStatus(){},pageHead:()=>node('head',[node('page-title')]),empty:()=>({}),confirmLeave:()=>true});
  return {app,document,pending,title:()=>$(`#page-title`),outside:()=>node('outside-input')};
}
async function opened(){const h=harness();const first=h.app.select('all');h.pending.shift().resolve({});await first;return h;}

test('기획 탭의 실제 setView→loader loading/ready render는 제목 포커스를 새 제목에 유지한다',async()=>{
  const h=await opened();h.app.setView('planning');
  assert.equal(h.app.phase(),'loading');assert.equal(h.document.activeElement,h.title());
  const loadingTitle=h.title();h.pending.shift().resolve({});await tick();
  assert.equal(h.app.phase(),'ready');assert.notEqual(h.title(),loadingTitle);
  assert.equal(h.document.activeElement,h.title());
});
test('기획 갱신 대기 중 다른 입력으로 이동한 포커스는 ready 재도장이 제목으로 가져오지 않는다',async()=>{
  const h=await opened();h.app.setView('planning');const input=h.outside();input.focus();
  h.pending.shift().resolve({});await tick();
  assert.equal(h.app.phase(),'ready');assert.equal(h.document.activeElement,input);
});
test('기획 갱신의 인증만료 빈 화면도 기존 제목 포커스만 새 제목으로 보존한다',async()=>{
  const h=await opened();h.app.setView('planning');
  h.pending.shift().reject(Object.assign(new Error('인증만료'),{status:401}));await tick();
  assert.equal(h.app.phase(),'unauthorized');assert.equal(h.document.activeElement,h.title());
});

test('실제 app beforeunload는 성과 입력·진행 중·pending mutation을 보호한다',()=>{
  const line=source.split('\n').find(line=>line.startsWith("window.addEventListener('beforeunload'"));
  for(const [dirty,busy,want] of [[true,false,true],[false,true,true],[false,false,false]]){
    let listener;vm.runInNewContext(line,{toolkitDirty:()=>false,toolkitBusy:()=>false,window:{addEventListener:(_,fn)=>listener=fn},editorActive:false,integrationSettings:{hasUnsavedChanges:()=>false},operations:{isDirty:()=>false,isBusy:()=>false},metrics:{isDirty:()=>dirty,isBusy:()=>busy},execution:{isDirty:()=>false,isBusy:()=>false}});
    let prevented=false;const event={preventDefault(){prevented=true;}};listener(event);assert.equal(prevented,want);
  }
});
