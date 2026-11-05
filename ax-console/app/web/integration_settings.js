// Preferences only: saving never installs, authenticates, schedules, or publishes.
export const integrationPlatforms={metricool:['instagram','threads','x','facebook','youtube','tiktok'],vidiq:['youtube','instagram','tiktok'],local:['youtube','tiktok','instagram','threads','x','facebook','tistory','naver_blog','blogger','homepage','kakao']};
export function settingsPayload(draft){
  const {account_id,provider_id,connection_id,platform,target_label,enabled_preference,notes}=draft;
  return {account_id,provider_id,connection_id,expected_revision:draft.revision??0,platform,target_label,enabled_preference,notes};
}
export function rebaseSettingsDraft(draft,latest){
  if(['account_id','provider_id','connection_id'].some(key=>draft[key]!==latest[key]))throw new Error('설정 키가 일치하지 않습니다.');
  return {...draft,revision:latest.revision};
}
const fresh=()=>({account_id:'',provider_id:'local',connection_id:'main',platform:'youtube',target_label:'',enabled_preference:false,notes:'',revision:0});
export function createIntegrationDraftState(){
  return {draft:fresh(),dirty:false,account:'all',hasUnsavedChanges(){return this.dirty;},discardChanges(){this.draft=fresh();this.dirty=false;}};
}
export function confirmSettingsNavigation(settings,confirm,otherDirty=false){
  const dirty=settings.hasUnsavedChanges();
  if(!otherDirty&&!dirty)return true;
  if(!confirm('저장하지 않은 변경을 버리고 이동할까요?'))return false;
  if(dirty)settings.discardChanges();return true;
}
export function createIntegrationSettings({api,onSaved=()=>{}}){
  const element=document.createElement('section');element.className='integration-settings';
  const heading=document.createElement('h2');heading.textContent='계정별 도구 사용 선호';element.append(heading);
  const explanation=document.createElement('p');explanation.textContent='이 설정은 웹의 사용 선호입니다. 설치·인증 상태는 미확인, 실행 상태는 연결되지 않음입니다. 저장해도 자동 작업이나 발행은 시작되지 않습니다.';element.append(explanation);
  const feedback=document.createElement('p');feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');element.append(feedback);
  const list=document.createElement('div');element.append(list);
  const form=document.createElement('form');element.append(form);
  const fields={};
  function field(key,label,options){
    const wrap=document.createElement('label');wrap.textContent=label+' ';
    const input=document.createElement(options?'select':key==='notes'?'textarea':'input');input.name=key;
    if(options)for(const [value,text] of options){const option=document.createElement('option');option.value=value;option.textContent=text;input.append(option);}
    if(key==='enabled_preference')input.type='checkbox';
    if(key==='connection_id'){input.pattern='[a-z0-9][a-z0-9_-]{0,63}';input.maxLength=64;}
    if(key==='target_label')input.maxLength=300;if(key==='notes')input.maxLength=2000;
    if(!['notes','enabled_preference','revision'].includes(key))input.required=true;
    if(key==='revision')input.readOnly=true;
    wrap.append(input);form.append(wrap);fields[key]=input;
  }
  field('account_id','소유 계정',[['','계정을 선택하세요'],['personal','개인'],['dept','학과']]);
  field('provider_id','도구',Object.keys(integrationPlatforms).map(key=>[key,key]));
  field('connection_id','연결 식별자');field('platform','플랫폼',[]);field('target_label','대상 이름');
  field('enabled_preference','사용 선호');field('notes','메모');field('revision','저장 버전');
  const submit=document.createElement('button');submit.type='submit';submit.textContent='선호 저장';form.append(submit);
  const newButton=document.createElement('button');newButton.type='button';newButton.textContent='새 설정';element.append(newButton);
  const discard=document.createElement('button');discard.type='button';discard.textContent='미저장 변경 버리고 새 설정';discard.hidden=true;element.append(discard);
  const rebase=document.createElement('button');rebase.type='button';rebase.textContent='내 입력을 유지하고 최신 버전 확인';rebase.hidden=true;element.append(rebase);
  const state=createIntegrationDraftState();let busy=false,generation=0;
  function platformOptions(value){fields.platform.replaceChildren();for(const name of integrationPlatforms[fields.provider_id.value]){const option=document.createElement('option');option.value=name;option.textContent=name;fields.platform.append(option);}fields.platform.value=value;if(!fields.platform.value)fields.platform.selectedIndex=0;}
  function paint(){
    for(const [key,input] of Object.entries(fields))if(key!=='platform'){if(key==='enabled_preference')input.checked=state.draft[key];else input.value=state.draft[key];}
    platformOptions(state.draft.platform);
    for(const key of ['account_id','provider_id','connection_id'])fields[key].disabled=state.draft.revision>0||busy;
    for(const key of ['platform','target_label','notes','enabled_preference'])fields[key].disabled=busy;
    submit.disabled=busy;newButton.disabled=busy;discard.disabled=busy;rebase.disabled=busy;
  }
  function read(){for(const [key,input] of Object.entries(fields))if(key!=='revision')state.draft[key]=key==='enabled_preference'?input.checked:input.value;return state.draft;}
  function reset(){state.discardChanges();discard.hidden=true;rebase.hidden=true;feedback.textContent='새 설정의 소유 계정을 선택하세요.';paint();}
  form.addEventListener('input',()=>{read();state.dirty=true;});
  fields.provider_id.addEventListener('change',()=>{platformOptions(state.draft.platform);read();state.dirty=true;});
  newButton.addEventListener('click',()=>{if(state.dirty){feedback.textContent='입력한 변경이 있습니다. 버리려면 아래 버튼을 누르세요.';discard.hidden=false;return;}reset();});
  discard.addEventListener('click',reset);
  function renderList(items){
    list.replaceChildren();if(!items.length){const p=document.createElement('p');p.textContent='저장된 선호 설정이 없습니다.';list.append(p);}
    for(const item of items){const button=document.createElement('button');button.type='button';button.textContent=`${item.account_id==='personal'?'개인':'학과'} · ${item.provider_id} · ${item.platform} · ${item.target_label} · v${item.revision} · 인증 미확인 / 실행 연결되지 않음`;button.addEventListener('click',()=>{if(busy)return;if(state.dirty){feedback.textContent='미저장 변경을 저장하거나 버린 뒤 다른 설정을 선택하세요.';discard.hidden=false;return;}state.draft={...item};rebase.hidden=true;paint();feedback.textContent='저장된 사용 선호를 편집합니다.';});list.append(button);}
  }
  async function load(scope='all'){
    if(!['all','personal','dept'].includes(scope))throw new Error('잘못된 계정 범위입니다.');
    state.account=scope;const current=++generation;
    try{const result=await api.listIntegrationSettings(scope);if(current!==generation)return;renderList(result.items);}
    catch(error){if(current===generation)feedback.textContent=error.status===401?'로그인이 필요합니다.':'설정을 불러오지 못했습니다. 다시 시도하세요.';}
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;read();busy=true;paint();feedback.textContent='선호를 저장하고 있습니다.';
    try{const saved=await api.putIntegrationSettings(settingsPayload(state.draft));state.draft={...saved};state.dirty=false;rebase.hidden=true;discard.hidden=true;await load(state.account);feedback.textContent='사용 선호를 저장했습니다. 인증은 미확인, 실행은 연결되지 않음입니다.';onSaved(saved);}
    catch(error){if(error.status===409){feedback.textContent='다른 창에서 변경했습니다. 입력은 보존했습니다. 최신 버전을 확인한 다음 다시 저장하세요.';rebase.hidden=false;}else feedback.textContent=error.status===401?'로그인이 필요합니다. 입력은 보존했습니다.':'저장하지 못했습니다. 입력은 보존했습니다.';}
    finally{busy=false;paint();}
  });
  rebase.addEventListener('click',async()=>{
    if(busy)return;busy=true;paint();
    try{const result=await api.listIntegrationSettings(state.draft.account_id);const latest=result.items.find(item=>['account_id','provider_id','connection_id'].every(key=>item[key]===state.draft[key]));if(!latest)throw new Error('설정을 찾지 못했습니다.');state.draft=rebaseSettingsDraft(state.draft,latest);state.dirty=true;rebase.hidden=true;feedback.textContent=`최신 버전 ${latest.revision}을 확인했습니다. 내 입력을 유지했습니다. 내용을 확인하고 저장하세요.`;}
    catch{feedback.textContent='최신 버전을 확인하지 못했습니다. 입력은 보존했습니다.';}
    finally{busy=false;paint();}
  });
  paint();return {element,load,hasUnsavedChanges:()=>state.hasUnsavedChanges(),discardChanges:reset};
}
