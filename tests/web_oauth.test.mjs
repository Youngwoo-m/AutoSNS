import test from 'node:test';
import assert from 'node:assert/strict';
import {createOAuthApi, safeAuthorizeUrl} from '../ax-console/app/web/oauth_api.js';
import {createOAuthController} from '../ax-console/app/web/oauth_controller.js';
import {createOAuthPanel} from '../ax-console/app/web/oauth_panel.js';
import {harness, all} from './helpers/execution_dom.mjs';
const provider={provider_id:'naver',platform:'naver_blog',login_method:'naver_profile',registration_status:'ready',cost_gate:'no_additional_cost',policy_gate:'allowed',read_scopes:['profile'],publication_scopes:[],blockers:[]};
function fixture(overrides={}) {
 const calls=[];
 const api={catalog:async()=>({items:[provider],live_enabled:true}),connections:async()=>({items:[{connection_id:'c1',account_id:'personal',provider_id:'naver',revision:2}],base_revision:'b1'}),result:async()=>({items:[]}),attempt:async id=>({attempt_id:id,account_id:'personal',provider_id:'naver',state:'callback_staged',revision:3}),...overrides};
 for(const name of ['start','continue','inspect','confirmTarget','refresh','disconnect','revoke'])if(!api[name])api[name]=async(...args)=>{calls.push([name,...args]);return {attempt_id:'a1',account_id:'personal',provider_id:'naver',state:'consent_pending',revision:1};};
 const controller=createOAuthController({api});
 return {api,calls,controller};
}
const click=(root,name)=>all(root).find(n=>n.getAttribute('data-oauth-action')===name);
const field=(root,name)=>all(root).find(n=>n.name===name);
async function ready(overrides={}) {const f=fixture(overrides);f.controller.setContext({account_id:'personal'});await f.controller.load();f.controller.selectProvider('naver');f.controller.selectConnection('c1');return f;}
test('API uses cookie and fresh CSRF, strict POST fields and never internal key',async()=>{
 const calls=[];
 const api=createOAuthApi(async(url,options)=>{calls.push([url,options]);return {ok:true,json:async()=>url.endsWith('/csrf')?{csrf_token:'csrf'}:{items:[]}};});
 await api.catalog('dept');await api.disconnect('c1',{request_key:'r',expected_base_revision:'b',expected_connection_revision:2});
 assert.equal(calls.length,3);assert.equal(calls[0][0],'/api/v2/oauth/catalog?account=dept');
 assert.equal(calls[2][1].credentials,'same-origin');assert.equal(calls[2][1].headers['X-CSRF-Token'],'csrf');
 await assert.rejects(()=>api.start({client_secret:'bad'}));assert.equal(calls.length,3);
});
test('response secrets and unsafe authorize redirects are rejected before exposure',async()=>{
 for(const payload of [{access_token:'bad'},{nested:{code:'bad'}},{credential_ref:'bad'},{verifier:'bad'}]) {
  const api=createOAuthApi(async()=>({ok:true,json:async()=>payload}));await assert.rejects(()=>api.result(),/응답/);
 }
 assert.ok(safeAuthorizeUrl('naver','https://nid.naver.com/oauth2.0/authorize?state=protocol&code_challenge=x'));
 for(const url of ['https://evil.test/oauth2.0/authorize','javascript:alert(1)','https://nid.naver.com.evil/authorize','https://u@nid.naver.com/oauth2.0/authorize','https://nid.naver.com/oauth2.0/authorize?access_token=bad'])assert.equal(safeAuthorizeUrl('naver',url),null);
});
test('render performs zero requests; selection clearing and account switch discard late responses',async()=>{
 let resolve;let count=0;const f=fixture({catalog:()=>{count++;return new Promise(r=>resolve=r);}});
 const {document}=harness();const panel=createOAuthPanel({controller:f.controller,document});panel.render();assert.equal(count,0);
 f.controller.setContext({account_id:'personal'});const pending=f.controller.load();f.controller.setContext({account_id:'dept'});resolve({items:[provider],live_enabled:true});await pending;
 assert.equal(f.controller.getState().account_id,'dept');assert.equal(f.controller.getState().catalog.length,0);
 f.controller.selectProvider('naver');f.controller.selectProvider('');assert.equal(f.controller.getState().provider_id,'');assert.equal(f.controller.hasUnsavedChanges(),false);
});
test('all and unknown or blocked providers never start authentication',async()=>{
 const f=await ready();f.controller.selectProvider('unknown');await f.controller.start();assert.equal(f.calls.length,0);
 f.controller.setContext({account_id:'all'});await f.controller.load();f.controller.selectProvider('naver');await f.controller.start();assert.equal(f.calls.length,0);
 const blocked=await ready({catalog:async()=>({items:[{...provider,cost_gate:'unknown'}],live_enabled:true})});await blocked.controller.start();assert.equal(blocked.calls.length,0);
});
for(const status of [401,409,503])test(`${status} preserves selection and pending request key until explicit retry`,async()=>{
 const bodies=[];const f=await ready({start:async body=>{bodies.push(body);throw Object.assign(new Error('unsafe secret'),{status});}});
 await f.controller.start();const key=f.controller.getState().pending.request_key;
 assert.equal(f.controller.getState().provider_id,'naver');assert.equal(f.controller.getState().connection_id,'c1');assert.equal(f.controller.hasUnsavedChanges(),true);
 await f.controller.start();assert.equal(bodies[1].request_key,key);assert.doesNotMatch(f.controller.getState().message,/unsafe secret/);
});
test('multi-tab results require explicit selection, same-account binding and explicit continue',async()=>{
 const f=await ready({result:async()=>({items:[{attempt_id:'a1',account_id:'personal',provider_id:'naver',state:'callback_staged',revision:3},{attempt_id:'a2',account_id:'dept',provider_id:'naver',state:'callback_staged',revision:2}]})});
 await f.controller.reloadOwnedResult();assert.equal(f.controller.getState().attempt,null);assert.equal(f.calls.length,0);
 await f.controller.selectOwnedAttempt('a2');assert.equal(f.controller.getState().attempt,null);
 await f.controller.selectOwnedAttempt('a1');assert.equal(f.calls.length,0);await f.controller.continue();assert.equal(f.calls[0][0],'continue');assert.equal(f.calls[0][2].expected_revision,3);
});
test('actual DOM controls select, clear, start and Escape closes with focus restoration',async()=>{
 const f=await ready();const {document}=harness();const opener=document.createElement('button');opener.focus();let closed=0;
 const panel=createOAuthPanel({controller:f.controller,document,onClose:()=>closed++});panel.open();let root=panel.render();
 assert.equal(root.getAttribute('role'),'dialog');assert.match(root.textContent,/읽기|권한/);assert.match(root.textContent,/발행.*비활성/);
 const selector=field(root,'provider_id');selector.value='';await selector.fire('change');assert.equal(f.controller.getState().provider_id,'');
 field(root,'provider_id').value='naver';await field(root,'provider_id').fire('change');await click(root,'start').fire('click');assert.equal(f.calls[0][0],'start');
 await root.fire('keydown',{key:'Escape'});assert.equal(closed,1);assert.equal(document.activeElement,opener);
});
test('target confirmation uses frozen proposal CAS; local disconnect is distinct from revoke',async()=>{
 const attempt={attempt_id:'a1',account_id:'personal',provider_id:'naver',state:'target_confirmation',revision:4,target_proposal:{proposal_id:'p1',expected_base_revision:'frozen',expected_connection_revision:7,target_id:'remote',target_label:'대상'}};
 const f=await ready({result:async()=>({items:[attempt]}),attempt:async()=>attempt});await f.controller.reloadOwnedResult();await f.controller.selectOwnedAttempt('a1');await f.controller.confirmTarget();
 assert.equal(f.calls[0][0],'confirmTarget');assert.equal(f.calls[0][2].expected_base_revision,'frozen');assert.equal(f.calls[0][2].expected_connection_revision,7);
 await f.controller.disconnect();assert.equal(f.calls[1][0],'disconnect');await f.controller.revoke();assert.equal(f.calls.length,2);
});
test('late mutation after account change cannot restore previous account attempt or clear new busy state',async()=>{
 let resolve;const f=await ready({start:()=>new Promise(r=>resolve=r)});const work=f.controller.start();assert.equal(f.controller.isBusy(),true);
 f.controller.setContext({account_id:'dept'});resolve({attempt_id:'old',account_id:'personal',provider_id:'naver',state:'connected'});await work;
 assert.equal(f.controller.getState().attempt,null);assert.equal(f.controller.getState().account_id,'dept');assert.equal(f.controller.isBusy(),false);
});
test('forged provider, secret and foreign-account attempt responses never become visible state',async()=>{
 for(const response of [{attempt_id:'a1',account_id:'dept',provider_id:'naver',state:'connected'}, {attempt_id:'a1',account_id:'personal',provider_id:'unknown',state:'connected'}, {attempt_id:'a1',account_id:'personal',provider_id:'naver',state:'connected',refresh_token:'secret'}]) {
  const f=await ready({result:async()=>({items:[{attempt_id:'a1',account_id:'personal',provider_id:'naver',state:'callback_staged'}]}),attempt:async()=>response});
  await f.controller.reloadOwnedResult();await f.controller.selectOwnedAttempt('a1');assert.equal(f.controller.getState().attempt,null);
  assert.doesNotMatch(JSON.stringify(f.controller.getState()),/refresh_token|secret/);
 }
});
test('Tab and Shift-Tab wrap focus; render does not steal outside focus',async()=>{
 const f=await ready();const {document}=harness();const panel=createOAuthPanel({controller:f.controller,document});panel.open();const root=panel.root;
 const controls=all(root).filter(n=>['button','select'].includes(n.tagName)&&!n.disabled);const first=controls[0],last=controls.at(-1);
 last.focus();await root.fire('keydown',{key:'Tab'});assert.equal(document.activeElement,first);
 first.focus();await root.fire('keydown',{key:'Tab',shiftKey:true});assert.equal(document.activeElement,last);
 const outside=document.createElement('input');outside.focus();f.controller.clearSelection();assert.equal(document.activeElement,outside);
});
test('DOM owned-result choice and continue are separate explicit events',async()=>{
 const f=await ready({result:async()=>({items:[{attempt_id:'a1',account_id:'personal',provider_id:'naver',state:'callback_staged',revision:3}]})});
 const {document}=harness();const panel=createOAuthPanel({controller:f.controller,document});const root=panel.render();
 await click(root,'owned-results').fire('click');assert.equal(f.calls.length,0);
 field(root,'attempt_id').value='a1';await field(root,'attempt_id').fire('change');assert.equal(f.calls.length,0);
 await click(root,'continue').fire('click');assert.equal(f.calls[0][0],'continue');
});
test('POST bodies reject nested secret and non-string scopes before obtaining CSRF',async()=>{
 let calls=0;const api=createOAuthApi(async()=>{calls++;return {ok:true,json:async()=>({csrf_token:'csrf'})};});
 const body={account_id:'personal',provider_id:'naver',connection_id:null,expected_base_revision:'b',expected_connection_revision:0,request_key:'r',requested_scopes:[{access_token:'bad'}]};
 await assert.rejects(()=>api.start(body));assert.equal(calls,0);
 await assert.rejects(()=>api.start({...body,requested_scopes:['profile'],provider_id:'unknown'}));assert.equal(calls,0);
});
test('malformed proposal cannot confirm a guessed or missing target revision',async()=>{
 const attempt={attempt_id:'a1',account_id:'personal',provider_id:'naver',state:'target_confirmation',revision:4,target_proposal:{proposal_id:'p1',target_id:'remote',target_label:'대상'}};
 const f=await ready({result:async()=>({items:[attempt]}),attempt:async()=>attempt});await f.controller.reloadOwnedResult();await f.controller.selectOwnedAttempt('a1');await f.controller.confirmTarget();assert.equal(f.calls.length,0);
 const {document}=harness();const panel=createOAuthPanel({controller:f.controller,document});assert.equal(click(panel.root,'confirm-target').disabled,true);
});
test('catalog blocked reason arrays are independent gates and cost allowed is not zero-cost evidence',async()=>{
 for(const fields of [{cost_gate:'allowed'}, {blockers:[],policy_reasons:['unverified']}, {blockers:['unverified'],policy_reasons:[]}]) {
  const f=await ready({catalog:async()=>({items:[{...provider,...fields}],live_enabled:true})});await f.controller.start();assert.equal(f.calls.length,0);
 }
});
test('attempt mutations reject a different attempt or selected connection in the same account',async()=>{
 for(const extra of [{attempt_id:'a2'},{connection_id:'other'}]) {
  const staged={attempt_id:'a1',account_id:'personal',provider_id:'naver',connection_id:'c1',state:'callback_staged',revision:3};
  const f=await ready({result:async()=>({items:[staged]}),attempt:async()=>staged,continue:async()=>({...staged,state:'token_exchanged',...extra})});
  await f.controller.reloadOwnedResult();await f.controller.selectOwnedAttempt('a1');await f.controller.continue();assert.equal(f.controller.getState().attempt.state,'callback_staged');assert.ok(f.controller.getState().pending);
 }
});
test('private credential references are blocked recursively',async()=>{
 for(const name of ['code_ref','ticket_ref','client_ref','token_ref']) {
  const api=createOAuthApi(async()=>({ok:true,json:async()=>({details:{[name]:{namespace:'private'}}})}));await assert.rejects(()=>api.result());
 }
});
