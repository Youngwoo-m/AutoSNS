const base = '/api/v2/oauth';
export const providerIds = Object.freeze(['instagram_login', 'instagram_facebook', 'threads', 'facebook_pages', 'x', 'tiktok', 'youtube', 'blogger', 'naver', 'tistory']);
const authorizeEndpoints = Object.freeze({
  instagram_login: ['https://www.instagram.com/oauth/authorize'],
  instagram_facebook: ['https://www.facebook.com/v23.0/dialog/oauth'],
  threads: ['https://threads.net/oauth/authorize', 'https://www.threads.net/oauth/authorize'],
  facebook_pages: ['https://www.facebook.com/v23.0/dialog/oauth'],
  x: ['https://x.com/i/oauth2/authorize'],
  tiktok: ['https://www.tiktok.com/v2/auth/authorize/'],
  youtube: ['https://accounts.google.com/o/oauth2/v2/auth'],
  blogger: ['https://accounts.google.com/o/oauth2/v2/auth'],
  naver: ['https://nid.naver.com/oauth2.0/authorize'],
});
const secretKey = /^(?:access_token|refresh_token|token|client_secret|client_secret_ref|credential_ref|credential_refs|code|code_ref|client_ref|token_ref|verifier_ref|ticket_ref|verifier|code_verifier|ticket|session_binding|state_hash)$/i;
const attemptStates = new Set(['registration_blocked', 'consent_pending', 'callback_staged', 'resume_pending', 'token_exchanged', 'principal_pending', 'target_confirmation', 'connected', 'denied', 'expired', 'error', 'revoked', 'unknown', 'disconnected', 'reauth_required']);
export function safeAuthorizeUrl(provider, value) {
  try {
    const url = new URL(value);
    if (url.username || url.password || url.hash || !authorizeEndpoints[provider]?.includes(url.origin + url.pathname)) return null;
    const allowed = new Set(['client_id', 'redirect_uri', 'response_type', 'scope', 'state', 'code_challenge', 'code_challenge_method', 'access_type', 'prompt', 'include_granted_scopes', 'enable_fb_login', 'force_authentication']);
    for (const key of url.searchParams.keys()) if (!allowed.has(key) || url.searchParams.getAll(key).length !== 1) return null;
    return url.href;
  } catch { return null; }
}
export function assertSafeOAuthResponse(value) {
  if (!value || typeof value !== 'object') return value;
  for (const [key, child] of Object.entries(value)) {
    if (secretKey.test(key) || (key === 'state' && !attemptStates.has(child))) throw new Error('안전하지 않은 OAuth 응답입니다.');
    if (key === 'authorize_url') {
      if (!safeAuthorizeUrl(value.provider_id, child)) throw new Error('안전하지 않은 OAuth 응답입니다.');
    } else if (child && typeof child === 'object') assertSafeOAuthResponse(child);
  }
  return value;
}
const exactGrantObject=(value,keys)=>!!value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).length===keys.length&&keys.every(key=>Object.hasOwn(value,key));
const grantText=(value,max=500)=>typeof value==='string'&&value.length>0&&value.length<=max&&!/[\x00-\x1f\x7f-\x9f]/.test(value);
const grantTime=value=>value===null||typeof value==='string'&&/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(value)&&Number.isFinite(Date.parse(value));
export function assertPublicationGrantResponse(value,binding={}) {
  assertSafeOAuthResponse(value);
  const fields=['connection_id','account_id','platform','provider_id','target_id','revision','status','approved_at','expires_at','policy_revision'];
  const invalid=()=>{throw new Error('발행 사용 승인 응답의 계정과 형식을 확인할 수 없습니다.');};
  if(!exactGrantObject(value,['publication_grant','available_actions','reason_codes','base_revision','connection_revision']))invalid();
  const grant=value.publication_grant;
  if(!exactGrantObject(grant,fields)||!['personal','dept'].includes(grant.account_id)||!providerIds.includes(grant.provider_id)||!['blocked','granted','revoked','expired'].includes(grant.status)||!Number.isSafeInteger(grant.revision)||grant.revision<0||!['connection_id','platform','target_id','policy_revision'].every(key=>grantText(grant[key]))||!grantTime(grant.approved_at)||!grantTime(grant.expires_at))invalid();
  if(grant.status==='granted'&&(grant.approved_at===null||grant.expires_at===null||Date.parse(grant.expires_at)<=Date.parse(grant.approved_at)))invalid();
  for(const key of ['account_id','connection_id','platform','provider_id','target_id'])if(binding[key]!==undefined&&grant[key]!==binding[key])invalid();
  if(!grantText(value.base_revision)||!Number.isSafeInteger(value.connection_revision)||value.connection_revision<0||!Array.isArray(value.available_actions)||value.available_actions.length>2||new Set(value.available_actions).size!==value.available_actions.length||!value.available_actions.every(action=>['approve','revoke'].includes(action))||!Array.isArray(value.reason_codes)||value.reason_codes.length>30||!value.reason_codes.every(reason=>typeof reason==='string'&&/^[a-z0-9_.-]{1,160}$/.test(reason)))invalid();
  return value;
}
const id = value => {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_.-]{1,160}$/.test(value)) throw new Error('식별자가 올바르지 않습니다.');
  return encodeURIComponent(value);
};
const account = value => {
  if (!['all', 'personal', 'dept'].includes(value)) throw new Error('계정 범위가 올바르지 않습니다.');
  return value;
};
export function createOAuthApi(request = globalThis.fetch) {
  async function get(path) { return send(path); }
  async function send(path, body, csrf) {
    const response = await request(base + path, {
      method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', redirect: 'error',
      headers: {Accept: 'application/json', ...(body === undefined ? {} : {'Content-Type': 'application/json', 'X-CSRF-Token': csrf})},
      ...(body === undefined ? {} : {body: JSON.stringify(body)}),
    });
    if (!response.ok) throw Object.assign(new Error('OAuth 요청을 처리하지 못했습니다.'), {status: response.status});
    return assertSafeOAuthResponse(await response.json());
  }
  async function post(path, body, fields) {
    const expected = ['request_key', ...fields];
    if (!body || Object.keys(body).length !== expected.length || expected.some(key => !Object.hasOwn(body, key))) throw new Error('OAuth 요청 필드가 올바르지 않습니다.');
    if (Object.keys(body).some(key => secretKey.test(key))) throw new Error('비밀 입력은 허용되지 않습니다.');
    if (typeof body.request_key !== 'string' || !body.request_key) throw new Error('요청 키가 필요합니다.');
    if ('requested_scopes' in body && (!Array.isArray(body.requested_scopes) || body.requested_scopes.some(scope => typeof scope !== 'string' || !scope))) throw new Error('권한 범위가 올바르지 않습니다.');
    if ('provider_id' in body && !providerIds.includes(body.provider_id)) throw new Error('제공자가 올바르지 않습니다.');
    if ('account_id' in body && !['personal', 'dept'].includes(body.account_id)) throw new Error('연결 계정이 올바르지 않습니다.');
    for (const key of ['expected_revision', 'expected_connection_revision', 'expected_grant_revision']) if (key in body && (!Number.isInteger(body[key]) || body[key] < 0)) throw new Error('예상 버전이 올바르지 않습니다.');
    const csrf = await get('/csrf');
    if (typeof csrf.csrf_token !== 'string' || !csrf.csrf_token) throw new Error('세션 확인이 필요합니다.');
    return send(path, body, csrf.csrf_token);
  }
  const revisions = ['expected_base_revision', 'expected_connection_revision'];
  const api = {
    catalog: (value = 'all') => get(`/catalog?account=${account(value)}`),
    connections: (value = 'all') => get(`/connections?account=${account(value)}`),
    result: () => get('/result'),
    attempt: value => get(`/attempts/${id(value)}`),
    start: body => post('/attempts', body, ['account_id', 'provider_id', 'connection_id', ...revisions, 'requested_scopes']),
    continue: (value, body) => post(`/attempts/${id(value)}/continue`, body, ['expected_revision']),
    inspect: (value, body) => post(`/attempts/${id(value)}/inspect`, body, ['expected_revision']),
    confirmTarget: (value, body) => post(`/targets/${id(value)}/confirm`, body, revisions),
    grant: async value => assertPublicationGrantResponse(await get(`/connections/${id(value)}/publication-grant`),{connection_id:value}),
  };
  for (const operation of ['approve','revoke']) api[operation+'Grant']=async(value,body)=>{
    if(!body||!grantText(body.expected_base_revision))throw new Error('예상 기준 버전이 올바르지 않습니다.');
    return assertPublicationGrantResponse(await post(`/connections/${id(value)}/publication-grant/${operation}`,body,[...revisions,'expected_grant_revision']),{connection_id:value});
  };
  for (const operation of ['refresh', 'disconnect', 'revoke']) api[operation] = (value, body) => post(`/connections/${id(value)}/${operation}`, body, revisions);
  return api;
}
