import {matchesOAuthConnection} from './oauth_controller.js';
import {safeAuthorizeUrl} from './oauth_api.js';
const providerNames = {instagram_login: 'Instagram Login', instagram_facebook: 'Instagram · Facebook Login', threads: 'Threads', facebook_pages: 'Facebook Pages', x: 'X', tiktok: 'TikTok', youtube: 'YouTube', blogger: 'Blogger', naver: 'Naver 회원 프로필', tistory: 'Tistory · 공식 API 종료'};
const stateNames = {registration_blocked: '로그인 준비 안 됨', consent_pending: '공식 서비스 동의 대기', callback_staged: '돌아오기 수신 · 연결 계속 필요', resume_pending: '같은 사이트 연결 계속 대기', token_exchanged: '주체 조회 필요', principal_pending: '주체 조회 대기', target_confirmation: '대상 확인 필요', connected: '서버에서 연결 확인', denied: '동의 거부 · 기존 연결 유지', expired: '시도 만료 · 기존 연결 유지', error: '연결 오류 · 기존 연결 유지', revoked: '권한 해지', unknown: '결과 불확실 · 자동 재전송 없음', disconnected: '로컬 연결 해제'};
const accountName = value => ({personal: '개인', dept: '학과', all: '전체 · 조회 전용'})[value] || '미확인';
const reasons = {cost_evidence_unverified: '추가 비용 0원 근거 미확인', app_registration_unverified: '앱 등록 미확인', https_callback_unaccepted: 'HTTPS 복귀 경계 미수락', paid_gate_unverified: '유료 사용 차단', profile_only: '회원 프로필만 지원', blog_publication_unsupported: '블로그 API 글쓰기 미지원', official_api_discontinued: '공식 API 종료', remote_revoke_project_impact_unverified: '프로젝트의 다른 연결에 미치는 해지 영향 미확인'};
export function createOAuthPanel({controller, document, onClose = () => true, onContextChange = () => true}) {
  const root = document.createElement('section');
  root.className = 'oauth-panel';
  root.setAttribute('role', 'dialog'); root.setAttribute('aria-modal', 'true'); root.setAttribute('aria-label', '채널·계정 OAuth 연결');
  root.style.maxWidth = '100%'; root.style.minWidth = '0'; root.style.overflowWrap = 'anywhere';
  let opener = null, opened = false, guardGeneration = 0;
  function node(tag, text) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    return item;
  }
  function button(parent, name, text, action, disabled = false) {
    const item = node('button', text); item.type = 'button'; item.disabled = disabled;
    item.setAttribute('data-oauth-action', name); item.addEventListener('click', action); parent.append(item); return item;
  }
  function select(parent, name, text, value, options, change, disabled) {
    const label = node('label', text), input = node('select');
    input.name = name; input.setAttribute('aria-label', text); input.disabled = disabled;
    for (const [id, title] of options) {const option = node('option', title); option.value = id; input.append(option);}
    input.value = value; input.addEventListener('change', () => change(input.value)); label.append(input); parent.append(label);
  }
  function authorizationDetails(parent, metadata) {
    const scopes = Array.isArray(metadata?.observed_scopes) && metadata.observed_scopes.every(scope => typeof scope === 'string')
      ? metadata.observed_scopes.join(', ') || '없음' : '미확인';
    const read = {not_checked: '미확인', verified: '확인됨', unknown: '불확실', error: '오류'};
    const publication = {not_checked: '미확인', blocked: '차단'};
    const credential = {pending: '보관 대기', stored: '보관됨', active: '활성 자격 확인', reauth_required: '재동의 필요', unknown: '불확실'};
    parent.append(node('p', `실제 동의된 scope: ${scopes}`));
    parent.append(node('p', `자격 만료: ${typeof metadata?.credential_expires_at === 'string' ? metadata.credential_expires_at : '미확인'}`));
    parent.append(node('p', `읽기 검증: ${read[metadata?.read_status] || '미확인'} · 발행 권한: ${publication[metadata?.publication_status] || '미확인'}`));
    parent.append(node('p', `자격 상태: ${credential[metadata?.credential_status] || '미확인'} · 발행 실행 비활성`));
  }
  async function close() {
    const current = ++guardGeneration;
    if (await onClose(controller.getState()) !== true || current !== guardGeneration) return false;
    controller.close(); opened = false; root.hidden = true;
    if (opener?.isConnected !== false) opener?.focus();
    return true;
  }
  async function changeAccount(value) {
    const current = ++guardGeneration;
    if (await onContextChange({account_id: value}, controller.getState()) === true && current === guardGeneration) controller.setContext({account_id: value});
    paint();
  }
  root.addEventListener('keydown', event => {
    if (event.key === 'Escape') {event.preventDefault(); return close();}
    if (event.key !== 'Tab') return;
    const controls = [...root.querySelectorAll('button,select,a[href],input,[tabindex]')].filter(item => !item.disabled && !item.hidden && item.getAttribute('tabindex') !== '-1');
    if (!controls.length) {event.preventDefault(); root.focus(); return;}
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && (document.activeElement === first || !root.contains(document.activeElement))) {event.preventDefault(); last.focus();}
    else if (!event.shiftKey && (document.activeElement === last || !root.contains(document.activeElement))) {event.preventDefault(); first.focus();}
  });
  function paint() {
    const focused = root.contains(document.activeElement) ? document.activeElement : null;
    const focusAction = focused?.getAttribute('data-oauth-action'), focusName = focused?.name;
    const state = controller.getState(), busy = state.busy, attempt = state.attempt;
    root.replaceChildren();
    const header = node('header'); header.append(node('h2', '채널·계정 연결')); button(header, 'close', '닫기', close); root.append(header);
    const progress = node('ol'); progress.setAttribute('aria-label', '연결 단계');
    const step = !state.provider_id ? 0 : !attempt ? 1 : attempt.state === 'consent_pending' ? 2 : ['callback_staged', 'resume_pending'].includes(attempt.state) ? 3 : attempt.state === 'connected' ? 5 : 4;
    ['계정·플랫폼', '지원·권한·비용', '공식 서비스 동의', '돌아오기', '주체·대상 확인', '연결 결과'].forEach((text, index) => {
      const item = node('li', `${index + 1}. ${text}`); if (index === step) item.setAttribute('aria-current', 'step'); progress.append(item);
    }); root.append(progress);
    const status = node('p', state.message); status.setAttribute('role', 'status'); status.setAttribute('aria-live', 'polite'); root.append(status);
    root.append(node('p', `${accountName(state.account_id)} · 발행 실행 비활성 · 연결 동의는 발행 승인이 아닙니다.`));
    select(root, 'account_id', '운영 계정', state.account_id, [['all', '전체 · 조회 전용'], ['personal', '개인'], ['dept', '학과']], changeAccount, busy);
    select(root, 'provider_id', '공식 연결 방식', state.provider_id, [['', '방식을 선택하세요'], ...state.catalog.map(row => [row.provider_id, providerNames[row.provider_id] || '미지원 방식'])], controller.selectProvider, busy);
    select(root, 'connection_id', '기존 연결 또는 신규 제안', state.connection_id, [['', '신규 연결 제안'], ...state.connections.filter(row => !state.provider_id || matchesOAuthConnection(row, state.catalog.find(item => item.provider_id === state.provider_id))).map(row => [row.connection_id || row.id, row.target_label || row.connection_id || row.id])], controller.selectConnection, busy);
    button(root, 'load', '등록·연결 상태 조회', controller.load, busy);
    button(root, 'clear', '선택 취소', controller.clearSelection, busy);
    if (state.pending) {
      root.append(node('p', '대기 요청은 원래 입력과 요청 키를 보존합니다. 상태 조회만으로 새 요청을 보내지 않습니다.'));
      button(root, 'retry-pending', '원래 입력·같은 키로 대기 요청 재확인', controller.retryPending, busy);
      if (state.errorStatus === 409 && ['start', 'refresh', 'disconnect', 'revoke'].includes(state.pending.operation)) button(root, 'revalidate-pending', '입력 유지하고 최신 기준 재검증 · 새 요청 준비', controller.revalidatePending, busy);
    }
    const provider = state.catalog.find(row => row.provider_id === state.provider_id);
    if (provider) {
      const conditions = node('section'); conditions.append(node('h3', '지원·권한·비용'), node('p', providerNames[provider.provider_id]));
      conditions.append(node('p', `등록: ${provider.registration_status === 'ready' ? '서버 준비 확인' : '로그인 준비 안 됨'} · 비용: ${provider.cost_gate === 'no_additional_cost' ? '추가 비용 0원 증거 범위 확인' : '유료·크레딧·미확인 비용은 호출 차단'}`));
      for (const reason of [...(provider.blockers || []), ...(provider.policy_reasons || [])]) conditions.append(node('p', reasons[reason] || `준비 조건 미충족: ${reason}`));
      conditions.append(node('p', `요청할 읽기 권한 · 주체와 대상 확인용: ${(provider.read_scopes || []).join(', ') || '없음·미확인'}`));
      conditions.append(node('p', `발행 추가 권한 · 별도 동의 필요: ${(provider.publication_scopes || []).join(', ') || '미지원·미확인'}`));
      if (provider.provider_id === 'naver') conditions.append(node('p', '회원 로그인은 네이버 블로그 게시 권한이 아닙니다.'));
      if (['youtube', 'blogger'].includes(provider.provider_id)) conditions.append(node('p', 'Google 원격 해지는 같은 프로젝트의 다른 클라이언트에도 영향을 줄 수 있습니다. 영향 미확인 시 차단합니다.'));
      if (provider.provider_id === 'tiktok') conditions.append(node('p', 'Display 읽기·inbox 업로드·Direct Post는 별개입니다. 앱 심사와 사용 목적 미확인입니다.'));
      button(conditions, 'start', '공식 서비스에서 동의 준비', controller.start, !controller.canStart()); root.append(conditions);
    }
    button(root, 'owned-results', '이 세션의 돌아온 시도 조회', controller.reloadOwnedResult, busy);
    if (state.ownedResults.length) {
      select(root, 'attempt_id', '돌아온 시도 직접 선택', attempt?.attempt_id || '', [['', '시도를 직접 선택하세요'], ...state.ownedResults.filter(row => row.account_id === state.account_id).map(row => [row.attempt_id, `${providerNames[row.provider_id] || '미지원'} · ${stateNames[row.state] || '상태 미확인'} · ${row.attempt_id}`])], value => value ? controller.selectOwnedAttempt(value) : controller.clearSelection(), busy);
    }
    if (attempt) {
      root.append(node('h3', stateNames[attempt.state] || '서버 상태 미확인'));
      const href = safeAuthorizeUrl(attempt.provider_id, attempt.authorize_url);
      if (attempt.state === 'consent_pending' && href) {
        const link = node('a', '공식 서비스 동의 화면 열기'); link.href = href; link.target = '_blank'; link.rel = 'noopener noreferrer'; link.referrerPolicy = 'no-referrer'; root.append(link);
        root.append(node('p', '동의를 거부하거나 창을 닫으면 기존 연결을 유지합니다. 자동 재시도하지 않습니다.'));
      }
      if (['callback_staged', 'resume_pending'].includes(attempt.state)) button(root, 'continue', '같은 사이트에서 연결 계속', controller.continue, busy);
      if (['token_exchanged', 'principal_pending'].includes(attempt.state)) button(root, 'inspect', '비용 0원 범위에서 주체·대상 확인', controller.inspect, busy);
      const subject = attempt.provider_subject;
      if (subject) root.append(node('p', `실제 로그인 주체: ${typeof subject === 'string' ? subject : subject.subject_id || subject.id || '미확인'}`));
      for (const target of attempt.targets || []) root.append(node('p', `관측 대상: ${target.target_label || ''} · ID ${target.target_id}`));
      const proposal = attempt.target_proposal;
      if (attempt.state === 'target_confirmation' && proposal) {
        root.append(node('p', `확인할 대상: ${proposal.target_label || ''} · 원격 ID ${proposal.target_id || '미확인'}`), node('p', '표시 이름과 원격 ID를 확인하세요. 다른 원격 계정으로 자동 교체하지 않습니다.'));
        button(root, 'confirm-target', '이 주체·대상으로 연결 확인', controller.confirmTarget, busy || !controller.canConfirmTarget());
      }
      root.append(node('p', `연결 시도 만료: ${attempt.expires_at || '미확인'}`));
      authorizationDetails(root, attempt.authorization);
    }
    const connection = state.connections.find(row => (row.connection_id || row.id) === state.connection_id);
    if (connection && state.account_id !== 'all') {
      const lifecycle = node('section'); lifecycle.append(node('h3', '연결 수명주기')); authorizationDetails(lifecycle, connection.authorization); lifecycle.append(node('p', '로컬 연결 해제는 이 콘솔의 관리 연결 사용만 중단합니다. 원격 권한 해지와 기존 발행 자격 삭제는 별개입니다.'));
      button(lifecycle, 'disconnect', '로컬 연결만 해제', controller.disconnect, busy);
      button(lifecycle, 'refresh', '명시적으로 자격 갱신', controller.refresh, busy || !connection.available_actions?.includes('refresh'));
      button(lifecycle, 'revoke', '제공자 원격 권한 해지', controller.revoke, busy || !connection.available_actions?.includes('revoke'));
      lifecycle.append(node('p', '원격 해지 영향과 비용이 확인되지 않으면 차단합니다. 로컬 해제를 원격 해지 성공으로 표시하지 않습니다.')); root.append(lifecycle);
    }
    if (focused) {
      const replacement = [...root.querySelectorAll('button,select,a[href]')].find(item => !item.disabled && (focusAction ? item.getAttribute('data-oauth-action') === focusAction : item.name === focusName));
      (replacement || root.querySelector('button'))?.focus();
    }
  }
  const unsubscribe = controller.subscribe(paint);
  paint();
  return {root, render: () => root, open() {opener = document.activeElement; opened = true; root.hidden = false; paint(); root.querySelector('button')?.focus(); return root;}, close,
    async destroy() {if (opened && !await close()) return false; unsubscribe(); return true;}};
}
