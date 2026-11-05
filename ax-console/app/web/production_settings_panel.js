// 계정별 제작 준비 설정. 저장은 다음 명시 기동에만 적용되며 실행하지 않는다.
export function createProductionSettingsPanel({document,fetcher=globalThis.fetch,onChange=()=>{}}={}) {
  const root=document.createElement('details');root.className='panel production-settings';
  let account=null,writable=false,baseline=null,draft=null,busy=false,message='',generation=0;
  const copy=value=>JSON.parse(JSON.stringify(value));
  const dirty=()=>!!draft&&JSON.stringify(draft)!==JSON.stringify(baseline);
  const node=(tag,attrs={},text)=>{const n=document.createElement(tag);for(const [k,v] of Object.entries(attrs)){if(k==='disabled')n.disabled=v;else n.setAttribute(k,String(v));}if(text!==undefined)n.textContent=text;return n;};
  async function request(method,body){const requestedAccount=account;const response=await fetcher(`/api/v2/production/settings?account=${requestedAccount}`,{method,credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});if(!response.ok)throw Object.assign(new Error(response.status===409?'다른 창에서 설정이 바뀌었습니다. 입력을 보존했습니다.':response.status===401?'로그인 후 다시 시도하세요. 입력은 유지됩니다.':'제작 설정을 처리하지 못했습니다. 입력은 유지됩니다.'),{status:response.status});const row=await response.json();if(row?.account_id!==requestedAccount||!Number.isInteger(row.revision)||row.revision<0||typeof row.enabled_preference!=='boolean'||row.execution_enabled!==false||row.applies_to!=='next_startup'||!(row.daily_limit===null||(Number.isInteger(row.daily_limit)&&row.daily_limit>0&&row.daily_limit<=2147483647)))throw new Error('제작 설정 응답의 계정과 형식을 확인할 수 없습니다. 입력은 유지됩니다.');return row;}
  function paint(){
    const summary=node('summary',{},'제작 설정');const body=node('div',{class:'panel-body'});
    body.append(node('p',{},'Claude Max 구독 · 텍스트 제작. 저장은 다음 명시적 제작 기동에 적용되며, 현재 실행·발행을 켜지 않습니다.'));
    if(draft){
      const enabled=node('input',{type:'checkbox',disabled:!writable||busy});enabled.checked=draft.enabled_preference;
      enabled.addEventListener('change',()=>{draft.enabled_preference=enabled.checked;onChange();});
      const label=node('label');label.append(enabled,document.createTextNode(' 다음 제작 기동에서 이 계정 사용'));body.append(label);
      const limit=node('input',{type:'number',min:1,step:1,'aria-label':'하루 최대 제작 횟수',disabled:!writable||busy});limit.value=draft.daily_limit??'';
      limit.addEventListener('input',()=>{draft.daily_limit=limit.value===''?null:Number(limit.value);onChange();});
      const field=node('label');field.append(document.createTextNode('하루 최대 제작 횟수'),limit);body.append(field,node('p',{},'관리 웹에서 만드는 텍스트 작업 횟수입니다. Claude 구독 잔여량과 기존 자동 발행 한도를 뜻하지 않습니다.'));
      const save=node('button',{type:'button',class:'btn btn-small',disabled:!writable||busy},busy?'저장 중…':'제작 설정 저장');save.addEventListener('click',saveSettings);body.append(save);
    }
    const reload=node('button',{type:'button',class:'btn btn-small',disabled:busy},'저장된 설정 다시 조회');reload.addEventListener('click',()=>{if(!dirty()||globalThis.confirm('미저장 제작 설정을 버리고 다시 조회할까요?'))load();});body.append(reload,node('p',{role:'status'},message));
    root.replaceChildren(summary,body);
  }
  async function load(){const token=++generation;busy=true;message='조회 중';paint();onChange();try{const result=await request('GET');if(token!==generation)return;baseline={enabled_preference:result.enabled_preference,daily_limit:result.daily_limit};draft=copy(baseline);root.dataset.revision=String(result.revision);message='저장된 준비 설정 · 실제 기동과 별개';}catch(e){if(token===generation)message=e.message;}finally{if(token===generation){busy=false;paint();onChange();}}}
  async function saveSettings(){if(!writable||busy||!draft)return;const cap=draft.daily_limit;if((cap!==null&&(!Number.isInteger(cap)||cap<1||cap>2147483647))||(draft.enabled_preference&&cap===null)){message='사용할 계정은 하루 최대 제작 횟수를 1 이상의 정수로 입력하세요.';paint();return;}busy=true;message='';paint();onChange();try{const result=await request('POST',{expected_revision:Number(root.dataset.revision||0),...draft});baseline={enabled_preference:result.enabled_preference,daily_limit:result.daily_limit};draft=copy(baseline);root.dataset.revision=String(result.revision);message='준비 설정을 저장했습니다. 현재 실행과 발행은 변경하지 않았습니다.';}catch(e){message=e.message;}finally{busy=false;paint();onChange();}}
  return {element:root,isDirty:dirty,isBusy:()=>busy,discardChanges(){if(baseline)draft=copy(baseline);paint();},render(options){writable=options.writable===true;if(account!==options.account){account=options.account;baseline=draft=null;message='';paint();load();}else paint();return root;}};
}
