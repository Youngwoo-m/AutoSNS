import test from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';
import {createOAuthApi} from '../ax-console/app/web/oauth_api.js';
import {createOAuthController} from '../ax-console/app/web/oauth_controller.js';
import {webSource} from './helpers/staged_web.mjs';
async function fixture(t) {
 const child=spawn(process.env.OAUTH_TEST_PYTHON||'python3',[fileURLToPath(new URL('./helpers/oauth_fixture.py',import.meta.url))],{stdio:['pipe','pipe','pipe']});
 let errors='';child.stderr.on('data',v=>errors+=v);const queue=[];
 createInterface({input:child.stdout}).on('line',line=>queue.shift()?.resolve(JSON.parse(line)));
 child.on('exit',code=>{for(const item of queue.splice(0))item.reject(new Error(`fixture ${code}: ${errors}`));});
 t.after(()=>{child.stdin.end();});
 const command=value=>new Promise((resolve,reject)=>{queue.push({resolve,reject});child.stdin.write(JSON.stringify(value)+'\n');});
 let failGet=false;const posts=[];
 const api=createOAuthApi(async(path,options)=>{
   if(failGet&&options.method==='GET'&&path.startsWith('/api/v2/oauth/connections'))throw new Error('GET unavailable');
   if(options.method==='POST')posts.push({path,body:JSON.parse(options.body)});
   const r=await command({path,...options,headers:{...options.headers,Origin:options.method==='POST'?'http://127.0.0.1:PLACEHOLDER':undefined}});
   return {ok:r.status===200,status:r.status,json:async()=>JSON.parse(r.body)};
 });
 const controller=createOAuthController({api});
 return {controller,command,posts,setFailGet:v=>failGet=v};
}
async function connected(f) {
 const c=f.controller;c.setContext({account_id:'personal'});await c.load();assert.equal(c.getState().catalog.length,10,JSON.stringify(c.getState()));c.selectProvider('youtube');
 await c.start();let s=c.getState();assert.equal(s.attempt?.state,'consent_pending',s.message);
 const state=new URL(s.attempt.authorize_url).searchParams.get('state');assert.equal((await f.command({command:'callback',state})).status,303);
 await c.reloadOwnedResult();assert.equal(c.getState().attempt,null);
 await c.selectOwnedAttempt(s.attempt.attempt_id);await c.continue();await c.inspect();
 assert.equal(c.canConfirmTarget(),true);await c.confirmTarget();return c;
}
test('actual HTTP null-ID confirm reloads current revision before refresh/disconnect',async t=>{
 const f=await fixture(t),c=await connected(f);let s=c.getState();
 assert.equal(s.attempt.state,'connected');assert.ok(s.connection_id.startsWith('oauth.'));
 assert.equal(s.connections.find(r=>r.id===s.connection_id||r.connection_id===s.connection_id)?.connection_revision,s.connection_revision);
 assert.ok(s.connection_revision>0,'confirm must fetch current connection revision');
 const revision=s.connection_revision;await c.refresh();s=c.getState();assert.equal(s.pending,null,s.message);assert.ok(s.connection_revision>revision);
 await c.disconnect();s=c.getState();assert.equal(s.pending,null,s.message);assert.equal(s.connections.some(r=>(r.id||r.connection_id)===s.connection_id),false);
});
test('successful POST followed by failed GET keeps success and never retries mutation',async t=>{
 const f=await fixture(t),c=await connected(f);f.setFailGet(true);const before=f.posts.length;await c.disconnect();
 assert.equal(c.getState().pending,null);assert.equal(c.getState().errorStatus,null);assert.match(c.getState().message,/완료|성공/);assert.match(c.getState().message,/조회/);
 await c.retryPending();await c.disconnect();assert.equal(f.posts.length,before+1);f.setFailGet(false);await c.load();assert.equal(c.getState().connections.some(r=>(r.id||r.connection_id)===c.getState().connection_id),false);
});
test('host connects OAuth mode and clean result shell without query reflection',()=>{
 const app=webSource('app.js'),index=webSource('index.html');
 assert.match(app,/createOAuthController/);assert.match(app,/detailMode/);assert.match(app,/oauth-result/);assert.doesNotMatch(app,/searchParams.*(?:code|state|token)/);
 assert.match(index,/href="\/web\/styles.css"/);assert.match(index,/src="\/web\/app.js"/);
});

import vm from 'node:vm';
import {createOAuthPanel} from '../ax-console/app/web/oauth_panel.js';
import {harness} from './helpers/execution_dom.mjs';
test('actual host request-close guards pending/busy before panel cleanup and native close',async()=>{
 const source=webSource('app.js');
 const guard=source.slice(source.indexOf('function guardOAuth()'),source.indexOf('\nconst oauthPanel='));
 const close=source.slice(source.indexOf('function finishDetailClose()'),source.indexOf("\n$('#drawer-close')"));
 const {document}=harness();const opener=document.createElement('button');opener.focus();
 let busy=false,dirty=true,allow=false,closed=0,cleaned=0;
 const controller={getState:()=>({account_id:'personal',catalog:[],connections:[],ownedResults:[],busy,pending:dirty?{}:null}),subscribe:()=>()=>{},close(){cleaned++;dirty=false;},canStart:()=>false};
 const dialog={open:true,close(){closed++;this.open=false;}};
 const context={oauthBusy:()=>busy,oauthDirty:()=>dirty,globalThis:{confirm:()=>allow},$:()=>dialog,editorActive:false,detailMode:'oauth'};
 const host=vm.runInNewContext(`${guard}\n${close}\n({guardOAuth,closeDetail,finishDetailClose})`,context);
 const panel=createOAuthPanel({controller,document,onClose:host.guardOAuth,onClosed:host.finishDetailClose});context.oauthPanel=panel;panel.open();
 host.closeDetail();await Promise.resolve();assert.equal(cleaned,0);assert.equal(closed,0);assert.equal(dirty,true);
 busy=true;allow=true;host.closeDetail();await Promise.resolve();assert.equal(cleaned,0);assert.equal(closed,0);
 busy=false;host.closeDetail();await Promise.resolve();assert.equal(cleaned,1);assert.equal(closed,1);assert.equal(document.activeElement,opener);
});
