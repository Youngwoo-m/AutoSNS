import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,all} from './helpers/execution_dom.mjs';
import {createVoiceSettingsPanel} from '../ax-console/app/web/voice_settings_panel.js';
const row=(account='personal',over={})=>({account_id:account,revision:2,enabled_preference:false,profile_id:null,applies_to:'next_startup',execution_enabled:false,...over});
const response=(body,status=200)=>({ok:status<400,status,json:async()=>body});
const action=(p,a)=>all(p.element).find(n=>n.getAttribute('data-voice-settings-action')===a);
const input=(p,a)=>all(p.element).find(n=>n.getAttribute('data-voice-settings-field')===a);
const setup=fetcher=>{const {document}=harness();const panel=createVoiceSettingsPanel({document,fetcher});return {panel,document};};
const expand=async p=>{p.element.open=true;await p.element.fire('toggle');};
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};

test('계정 설정은 펼칠 때만 조회하며 실행을 요청하지 않는다',async()=>{
 const calls=[];const {panel}=setup(async(u,o)=>{calls.push([u,o]);return response(row());});
 await panel.open('personal',{writable:true});assert.equal(calls.length,0);assert.equal(panel.isDirty(),false);
 await expand(panel);assert.equal(calls.length,1);assert.equal(calls[0][0],'/api/v2/accounts/personal/voice-settings');assert.equal(calls[0][1].method,'GET');
 assert.match(panel.element.textContent,/개인/);assert.match(panel.element.textContent,/다음.*기동/);
 await panel.element.fire('toggle');assert.equal(calls.length,1);
});
test('정확한 계정별 설정 payload와 CAS만 저장한다',async()=>{
 const calls=[];const {panel}=setup(async(u,o)=>{calls.push([u,o]);if(o.method==='GET')return response(row('dept'));return response(row('dept',{revision:3,...JSON.parse(o.body).settings}));});
 await panel.open('dept',{writable:true});await expand(panel);
 input(panel,'profile').value='voice_1';await input(panel,'profile').fire('input');input(panel,'enabled').checked=true;await input(panel,'enabled').fire('change');
 await action(panel,'save').fire('click');assert.equal(calls.length,2);assert.deepEqual(JSON.parse(calls[1][1].body),{expected_revision:2,settings:{enabled_preference:true,profile_id:'voice_1'}});assert.equal(panel.isDirty(),false);
});
test('입력 중 같은 계정 갱신과 refreshControls는 포커스와 초안을 보존한다',async()=>{
 const {panel,document}=setup(async()=>response(row()));await panel.open('personal',{writable:true});await expand(panel);
 const profile=input(panel,'profile');profile.focus();profile.value='keep';await profile.fire('input');
 panel.refreshControls({writable:true});await panel.open('personal',{writable:true});assert.equal(document.activeElement,profile);assert.equal(input(panel,'profile'),profile);assert.equal(panel.isDirty(),true);
});
test('잘못된 프로필은 저장하지 않고 409·네트워크 오류는 입력을 보존한다',async()=>{
 let mode=409,posts=0;const {panel}=setup(async(u,o)=>{if(o.method==='GET')return response(row());posts++;if(mode==='network')throw new Error('private');return response({},mode);});
 await panel.open('personal',{writable:true});await expand(panel);input(panel,'enabled').checked=true;await input(panel,'enabled').fire('change');await action(panel,'save').fire('click');assert.equal(posts,0);
 input(panel,'profile').value='keep-profile';await input(panel,'profile').fire('input');await action(panel,'save').fire('click');assert.equal(posts,1);assert.equal(input(panel,'profile').value,'keep-profile');assert.equal(panel.isDirty(),true);assert.match(panel.element.textContent,/보존/);
 mode='network';await action(panel,'save').fire('click');assert.equal(input(panel,'profile').value,'keep-profile');assert.doesNotMatch(panel.element.textContent,/private/);
 await action(panel,'discard').fire('click');assert.equal(panel.isDirty(),false);
});
test('읽기 전용·대기 중 중복 저장은 막고 비활성 설정은 빈 프로필 null 허용한다',async()=>{
 const gate=deferred();const calls=[];const {panel}=setup(async(u,o)=>{calls.push(o);return o.method==='GET'?response(row()):gate.promise;});
 await panel.open('personal',{writable:false});await expand(panel);assert.equal(input(panel,'profile').disabled,true);await action(panel,'save').fire('click');assert.equal(calls.length,1);
 panel.refreshControls({writable:true});const saving=action(panel,'save').fire('click');assert.equal(panel.isBusy(),true);await action(panel,'save').fire('click');assert.equal(calls.length,2);assert.deepEqual(JSON.parse(calls[1].body).settings,{enabled_preference:false,profile_id:null});gate.resolve(response(row(undefined,{revision:3})));await saving;
});
test('다른 계정·추가필드 응답은 거부하고 늦은 개인 응답이 학과를 침범하지 않는다',async()=>{
 for(const bad of [row('dept'),row('personal',{unexpected:true}),row('personal',{profile_id:'bad path'}),row('personal',{enabled_preference:true,profile_id:null})]){
  const {panel}=setup(async()=>response(bad));await panel.open('personal',{writable:true});await expand(panel);assert.equal(input(panel,'profile'),undefined);assert.match(panel.element.textContent,/확인할 수 없/);
 }
 const gate=deferred();const {panel}=setup(u=>u.includes('personal')?gate.promise:Promise.resolve(response(row('dept',{profile_id:'dept-voice'}))));
 await panel.open('personal',{writable:true});const old=expand(panel);await panel.open('dept',{writable:true});await expand(panel);gate.resolve(response(row('personal',{profile_id:'personal-voice'})));await old;assert.equal(input(panel,'profile').value,'dept-voice');
 await panel.open('invalid',{writable:true});await expand(panel);assert.equal(input(panel,'profile'),undefined);
});
test('다시 조회는 미저장 입력 확인 취소 시 요청하지 않는다',async()=>{
 let calls=0;const {panel}=setup(async()=>{calls++;return response(row());});await panel.open('personal',{writable:true});await expand(panel);
 input(panel,'profile').value='dirty';await input(panel,'profile').fire('input');const original=globalThis.confirm;globalThis.confirm=()=>false;
 try{await action(panel,'reload').fire('click');assert.equal(calls,1);assert.equal(input(panel,'profile').value,'dirty');}finally{globalThis.confirm=original;}
});

test('늦은 저장 응답은 전환한 계정의 초안을 바꾸지 않는다',async()=>{
 const gate=deferred();const calls=[];const {panel}=setup(async(u,o)=>{calls.push([u,o]);const account=u.includes('/dept/')?'dept':'personal';return o.method==='GET'?response(row(account)):gate.promise;});
 await panel.open('personal',{writable:true});await expand(panel);input(panel,'profile').value='personal-profile';await input(panel,'profile').fire('input');const old=action(panel,'save').fire('click');
 await panel.open('dept',{writable:true});await expand(panel);input(panel,'profile').value='dept-draft';await input(panel,'profile').fire('input');gate.resolve(response(row('personal',{revision:3,profile_id:'personal-profile'})));await old;
 assert.equal(input(panel,'profile').value,'dept-draft');assert.equal(panel.isDirty(),true);assert.equal(panel.isBusy(),false);assert.equal(calls.length,3);
});
