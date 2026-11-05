import test from 'node:test';
import assert from 'node:assert/strict';
import {createOAuthApi,assertPublicationGrantResponse} from '../ax-console/app/web/oauth_api.js';
import {createOAuthController} from '../ax-console/app/web/oauth_controller.js';
import {createOAuthPanel} from '../ax-console/app/web/oauth_panel.js';
import {harness,all} from './helpers/execution_dom.mjs';
const provider={provider_id:'youtube',platform:'youtube',login_method:'google_web',registration_status:'ready',cost_gate:'no_additional_cost',policy_gate:'allowed',read_scopes:['read'],publication_scopes:['write'],blockers:[]};
const grant=(account='personal',connection='personal.youtube',over={})=>({connection_id:connection,account_id:account,platform:'youtube',provider_id:'youtube',target_id:account==='personal'?'channel-personal':'channel-dept',revision:0,status:'blocked',approved_at:null,expires_at:null,policy_revision:'grant-policy',...over});
const response=(account='personal',connection=account+'.youtube',over={})=>({publication_grant:grant(account,connection),available_actions:['approve'],reason_codes:[],base_revision:'base-current',connection_revision:7,...over});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const button=(panel,name)=>all(panel.root).find(n=>n.getAttribute('data-oauth-action')===name);
const details=panel=>all(panel.root).find(n=>n.getAttribute('data-oauth-publication-grant')!==null);
async function setup(overrides={}){
 const calls=[];
 const api={catalog:async()=>({items:[provider],live_enabled:true}),connections:async(account)=>({items:[{id:account+'.youtube',account_id:account,provider_id:'youtube',platform:'youtube',target_id:account==='personal'?'channel-personal':'channel-dept',revision:2},{id:account+'.second',account_id:account,provider_id:'youtube',platform:'youtube',target_id:account==='personal'?'channel-personal':'channel-dept',revision:3}],base_revision:'old-base'}),grant:async id=>{calls.push(['grant',id]);return response(id.split('.')[0],id);},approveGrant:async(id,body)=>{calls.push(['approve',id,body]);return response('personal',id,{publication_grant:grant('personal',id,{revision:1,status:'granted',approved_at:'2026-11-04T00:00:00Z',expires_at:'2026-11-04T01:00:00Z'}),available_actions:['revoke']});},revokeGrant:async(id,body)=>{calls.push(['revoke',id,body]);return response('personal',id,{publication_grant:grant('personal',id,{revision:2,status:'revoked'}),available_actions:['approve']});},...overrides};
 const c=createOAuthController({api});c.setContext({account_id:'personal'});await c.load();c.selectProvider('youtube');c.selectConnection('personal.youtube');
 const panel=createOAuthPanel({controller:c,document:harness().document});
 return {api,c,calls,panel};
}
async function expand(panel){const d=details(panel);d.open=true;await d.fire('toggle');}

test('접힌 승인 영역은 렌더·펼치기·일반 조회에서 새 API를 자동 호출하지 않는다',async()=>{
 const {c,calls,panel}=await setup();assert.equal(details(panel).open,false);assert.equal(calls.length,0);
 await expand(panel);assert.equal(calls.length,0);await c.load();assert.equal(calls.length,0);
 assert.match(panel.root.textContent,/실제 콘텐츠 발행 승인은 별도/);assert.match(panel.root.textContent,/콘텐츠를 게시하지 않습니다/);
 await button(panel,'publication-grant-load').fire('click');assert.deepEqual(calls,[['grant','personal.youtube']]);
});
test('명시 클릭은 서버가 반환한 CAS만 전송하고 만료·scope·증거 입력은 없다',async()=>{
 const {c,calls,panel}=await setup();await expand(panel);
 assert.equal(button(panel,'publication-grant-approve').disabled,true);
 await button(panel,'publication-grant-load').fire('click');assert.equal(button(panel,'publication-grant-approve').disabled,false);
 assert.equal(button(panel,'publication-grant-revoke').disabled,true);
 await button(panel,'publication-grant-approve').fire('click');const approved=calls[1];
 assert.equal(approved[0],'approve');assert.equal(approved[1],'personal.youtube');
 assert.deepEqual(Object.keys(approved[2]).sort(),['expected_base_revision','expected_connection_revision','expected_grant_revision','request_key']);
 assert.equal(approved[2].expected_base_revision,'base-current');assert.equal(approved[2].expected_connection_revision,7);assert.equal(approved[2].expected_grant_revision,0);
 assert.equal(typeof approved[2].request_key,'string');assert.match(panel.root.textContent,/발행 사용 승인됨/);
 assert.equal(button(panel,'publication-grant-approve').disabled,true);assert.equal(button(panel,'publication-grant-revoke').disabled,false);
 await button(panel,'publication-grant-revoke').fire('click');assert.equal(calls[2][2].expected_grant_revision,1);assert.match(panel.root.textContent,/승인 회수됨/);
 assert.equal(all(panel.root).filter(n=>n.tagName==='input').length,0);
});
test('API exact grant 요청은 cookie·CSRF를 사용하고 추가 body는 요청 전 거부한다',async()=>{
 const calls=[];const api=createOAuthApi(async(url,options)=>{calls.push([url,options]);return {ok:true,json:async()=>url.endsWith('/csrf')?{csrf_token:'csrf'}:response()};});
 await api.grant('personal.youtube');
 const body={request_key:'request',expected_base_revision:'base',expected_connection_revision:7,expected_grant_revision:0};
 await api.approveGrant('personal.youtube',body);await api.revokeGrant('personal.youtube',body);
 assert.equal(calls[0][0],'/api/v2/oauth/connections/personal.youtube/publication-grant');
 assert.equal(calls[2][0],'/api/v2/oauth/connections/personal.youtube/publication-grant/approve');
 assert.equal(calls[4][0],'/api/v2/oauth/connections/personal.youtube/publication-grant/revoke');
 assert.equal(calls[2][1].credentials,'same-origin');assert.equal(calls[2][1].headers['X-CSRF-Token'],'csrf');assert.deepEqual(JSON.parse(calls[2][1].body),body);
 const count=calls.length;
 for(const change of [{target_id:'other'},{expires_at:'2099-01-01'},{evidence:{}},{expected_grant_revision:-1},{expected_grant_revision:true},{expected_base_revision:null}])await assert.rejects(()=>api.approveGrant('personal.youtube',{...body,...change}));
 assert.equal(calls.length,count);
});
test('safe10·계정·연결·공급자·개인정보 필드 위조 응답은 승인 능력을 주지 않는다',async()=>{
 const bodies=[{...response(),private:{evidence:'secret'}},response('dept'),response('personal','personal.second'),response('personal','personal.youtube',{publication_grant:grant('personal','personal.youtube',{credential_ref:'secret'})}),response('personal','personal.youtube',{publication_grant:grant('personal','personal.youtube',{target_id:'other'})}),response('personal','personal.youtube',{publication_grant:grant('personal','personal.youtube',{provider_id:'blogger'})}),response('personal','personal.youtube',{available_actions:['publish']}),response('personal','personal.youtube',{connection_revision:'7'}),response('personal','personal.youtube',{publication_grant:grant('personal','personal.youtube',{status:'granted'})})];
 for(const value of bodies){const {c,panel}=await setup({grant:async()=>value});await c.reloadPublicationGrant();assert.equal(c.getState().publicationGrantResult,null);assert.equal(c.canPublicationGrantAction('approve'),false);assert.doesNotMatch(panel.root.textContent,/secret/);}
 assert.throws(()=>assertPublicationGrantResponse({...response(),access_token:'secret'}));
});
test('검사기 미등록 또는 서버 actions 비어 있으면 승인 버튼을 켜지 않는다',async()=>{
 const {c,panel}=await setup({grant:async()=>response('personal','personal.youtube',{available_actions:[],reason_codes:['publication_verifier_unregistered']})});
 await expand(panel);await c.reloadPublicationGrant();assert.equal(button(panel,'publication-grant-approve').disabled,true);assert.equal(button(panel,'publication-grant-revoke').disabled,true);assert.match(panel.root.textContent,/게시 권한 검사기가 등록되지 않았습니다/);assert.doesNotMatch(panel.root.textContent,/publication_verifier_unregistered/);
 const absent=await setup({grant:undefined,approveGrant:undefined,revokeGrant:undefined});await absent.c.reloadPublicationGrant();assert.match(absent.panel.root.textContent,/등록되지 않았/);assert.equal(absent.calls.length,0);
});
test('계정 또는 연결 전환 뒤 늦은 조회·변경 응답은 현재 상태를 덮어쓰지 않는다',async()=>{
 for(const action of [false,true])for(const accountSwap of [false,true]){
  const gate=deferred();const {c,api}=await setup();
  if(action){await c.reloadPublicationGrant();api.approveGrant=()=>gate.promise;}else api.grant=()=>gate.promise;
  const pending=action?c.approvePublicationGrant():c.reloadPublicationGrant();assert.equal(c.getState().publicationGrantBusy,true);
  if(accountSwap){c.setContext({account_id:'dept'});await c.load();c.selectProvider('youtube');c.selectConnection('dept.youtube');}else c.selectConnection('personal.second');
  gate.resolve(response());await pending;
  assert.equal(c.getState().publicationGrantResult,null);assert.equal(c.getState().publicationGrantBusy,false);assert.equal(c.getState().connection_id,accountSwap?'dept.youtube':'personal.second');
 }
});
test('불확실·409·세션 오류 뒤에는 재전송 없이 능력을 지우고 수동 재조회만 허용한다',async()=>{
 for(const status of [undefined,401,409,503]){
  const {c,api,calls,panel}=await setup();await expand(panel);await c.reloadPublicationGrant();
  api.approveGrant=async()=>{calls.push(['uncertain']);throw Object.assign(new Error('private token'),{status});};
  await c.approvePublicationGrant();assert.equal(c.getState().publicationGrantUnknown,true);assert.equal(c.getState().publicationGrantResult,null);
  await c.approvePublicationGrant();await c.revokePublicationGrant();assert.equal(calls.filter(row=>row[0]==='uncertain').length,1);
  assert.match(panel.root.textContent,/결과 미확인/);assert.match(panel.root.textContent,/자동 재시도하지 않습니다/);assert.doesNotMatch(panel.root.textContent,/private token/);
  await c.load();assert.equal(c.getState().publicationGrantUnknown,true);
  await c.reloadPublicationGrant();assert.equal(c.getState().publicationGrantUnknown,false);assert.equal(c.canPublicationGrantAction('approve'),true);
 }
});
test('전체 계정에서는 발행 사용 승인 조회나 변경을 하지 않는다',async()=>{
 const {c,calls}=await setup();c.setContext({account_id:'all'});await c.reloadPublicationGrant();await c.approvePublicationGrant();await c.revokePublicationGrant();assert.equal(calls.length,0);
});

test('발행 사용 승인 차단 사유는 한국어로 안내하고 알 수 없는 코드 원문을 숨긴다',async()=>{
 const codes=['oauth_publication_verifier_unavailable','oauth_publication_scope_consent_required','oauth_publication_binding_changed','oauth_credential_expired','oauth_publication_storage_uninitialized','oauth_publication_authorization_unavailable','oauth_publication_policy_blocked','unknown_internal_condition'];
 const {c,panel}=await setup({grant:async()=>response('personal','personal.youtube',{available_actions:[],reason_codes:codes})});
 await c.reloadPublicationGrant();
 for(const text of ['게시 권한 검사기가 등록되지 않았습니다','추가 권한에 먼저 동의','현재 연결이 변경','자격이 만료','승인 저장소가 준비되지','앱·비용 조건 검사기가 등록되지','정책에서 이 연결의 발행 사용을 허용하지','서버에서 승인 조건을 확인하지 못했습니다'])assert.ok(panel.root.textContent.includes(text),text);
 for(const code of codes)assert.equal(panel.root.textContent.includes(code),false);
 assert.equal(c.canPublicationGrantAction('approve'),false);
});
