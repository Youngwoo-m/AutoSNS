// 계정별 음성 프로필 준비 설정. 저장은 다음 명시 기동에만 적용한다.
const KEYS=['account_id','revision','enabled_preference','profile_id','applies_to','execution_enabled'];
const validProfile=v=>v===null||(typeof v==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(v));
const validRow=(r,a)=>r&&typeof r==='object'&&!Array.isArray(r)&&Object.keys(r).length===KEYS.length&&KEYS.every(k=>Object.hasOwn(r,k))&&r.account_id===a&&Number.isInteger(r.revision)&&r.revision>=0&&typeof r.enabled_preference==='boolean'&&validProfile(r.profile_id)&&(!r.enabled_preference||r.profile_id!==null)&&r.applies_to==='next_startup'&&r.execution_enabled===false;
export function createVoiceSettingsPanel({document,fetcher=globalThis.fetch,onChange=()=>{}}={}){
 const root=document.createElement('details');root.className='panel voice-settings';
 let account=null,writable=false,baseline=null,draft=null,revision=0,busy=false,message='',generation=0,loaded=false;
 const dirty=()=>!!draft&&JSON.stringify(draft)!==JSON.stringify(baseline);
 const editable=()=>writable&&!busy&&!!draft;
 const copy=v=>({...v});
 const node=(tag,attrs={},text)=>{const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='disabled')n.disabled=v;else n.setAttribute(k,String(v));}if(text!==undefined)n.textContent=text;return n;};
 function controls(){for(const n of root.querySelectorAll('[data-voice-settings-field]'))n.disabled=!editable();for(const n of root.querySelectorAll('[data-voice-settings-action]')){const a=n.getAttribute('data-voice-settings-action');n.disabled=a==='reload'?busy||!account:a==='discard'?busy||!draft:!editable();}}
 function paint(){
  const body=node('div',{class:'panel-body'});body.append(node('p',{},`${account==='personal'?'개인':account==='dept'?'학과':'계정 선택 전'} 음성 설정 · 저장은 다음 명시 기동에 적용됩니다. 현재 음성 합성·발행·유료 호출을 실행하지 않습니다.`));
  if(draft){
   const enabled=node('input',{type:'checkbox','data-voice-settings-field':'enabled'});enabled.checked=draft.enabled_preference;
   enabled.addEventListener('change',()=>{if(!editable())return;draft.enabled_preference=enabled.checked;onChange();});
   const label=node('label');label.append(enabled,document.createTextNode(' 다음 음성 제작 기동에서 이 계정 사용'));body.append(label);
   const profile=node('input',{type:'text',maxlength:128,'aria-label':'음성 프로필 ID','data-voice-settings-field':'profile'});profile.value=draft.profile_id??'';
   profile.addEventListener('input',()=>{if(!editable())return;draft.profile_id=profile.value===''?null:profile.value;onChange();});
   const field=node('label');field.append(document.createTextNode('로컬 음성 프로필 ID '),profile);body.append(field,node('p',{class:'sub'},'영문·숫자·밑줄·하이픈으로 된 기존 로컬 프로필 ID만 입력하세요. 프로필 생성·복제·검증은 이 저장에서 실행하지 않습니다.'));
   for(const [name,text,handler] of [['save','설정 저장',save],['discard','입력 버리기',discard]]){const button=node('button',{type:'button',class:'btn btn-small','data-voice-settings-action':name},text);button.addEventListener('click',handler);body.append(button);}
  }
  const reload=node('button',{type:'button',class:'btn btn-small','data-voice-settings-action':'reload'},'다시 조회');reload.addEventListener('click',reloadSettings);body.append(reload,node('p',{role:'status'},message));
  root.replaceChildren(node('summary',{},'계정별 음성 설정'),body);controls();
 }
 function apply(row){revision=row.revision;baseline={enabled_preference:row.enabled_preference,profile_id:row.profile_id};draft=copy(baseline);loaded=true;}
 async function request(mine,method,body){
  let response;try{response=await fetcher(`/api/v2/accounts/${mine}/voice-settings`,{method,credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});}catch{throw new Error('음성 설정 서버에 연결하지 못했습니다. 입력은 유지됩니다.');}
  if(!response.ok)throw new Error(response.status===409?'다른 창에서 음성 설정이 바뀌었습니다. 입력을 보존했습니다. 다시 조회해 비교하세요.':response.status===401?'로그인 후 다시 시도하세요. 입력은 유지됩니다.':'음성 설정을 처리하지 못했습니다. 입력은 유지됩니다.');
  let row;try{row=await response.json();}catch{row=null;}
  if(!validRow(row,mine))throw new Error('음성 설정 응답의 계정과 형식을 확인할 수 없습니다. 입력은 유지됩니다.');return row;
 }
 async function load(){
  if(!account||busy)return;const mine=account,token=++generation;busy=true;message='조회 중';paint();onChange();
  try{const row=await request(mine,'GET');if(token!==generation)return;apply(row);message='저장된 준비 설정 · 다음 명시 기동에 적용';}catch(e){if(token===generation)message=e.message;}finally{if(token===generation){busy=false;paint();onChange();}}
 }
 async function save(){
  if(!editable()||!account)return;
  if(!validProfile(draft.profile_id)||(draft.enabled_preference&&draft.profile_id===null)){message='사용할 음성 프로필 ID를 영문·숫자·밑줄·하이픈 1~128자로 입력하세요.';paint();return;}
  const mine=account,token=++generation,body={expected_revision:revision,settings:copy(draft)};busy=true;message='저장 중';paint();onChange();
  try{const row=await request(mine,'POST',body);if(token!==generation)return;apply(row);message='준비 설정을 저장했습니다. 현재 실행과 발행은 변경하지 않았습니다.';}catch(e){if(token===generation)message=e.message;}finally{if(token===generation){busy=false;paint();onChange();}}
 }
 function discard(){if(busy||!baseline)return;draft=copy(baseline);paint();onChange();}
 async function reloadSettings(){if(!account||busy)return;if(dirty()&&(typeof globalThis.confirm!=='function'||!globalThis.confirm('미저장 음성 설정을 버리고 다시 조회할까요?')))return;return load();}
 root.addEventListener('toggle',()=>{if(root.open&&account&&!loaded&&!busy)return load();});paint();
 return {element:root,isDirty:dirty,isBusy:()=>busy,discardChanges:discard,refreshControls(options={}){if(options.writable!==undefined)writable=options.writable===true;controls();},open(value,{writable:w=true}={}){writable=w===true;const next=value==='personal'||value==='dept'?value:null;if(next===account){controls();return Promise.resolve();}generation++;account=next;baseline=draft=null;revision=0;busy=false;message='';loaded=false;root.open=false;paint();onChange();return Promise.resolve();}};
}
