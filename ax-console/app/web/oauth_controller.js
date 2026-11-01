import {providerIds, assertSafeOAuthResponse} from './oauth_api.js';
const accounts = new Set(['all', 'personal', 'dept']);
const requestKey = () => globalThis.crypto.randomUUID();
const clean = account_id => ({account_id, provider_id: '', connection_id: '', base_revision: null, connection_revision: 0,
  catalog: [], connections: [], ownedResults: [], attempt: null, pending: null, requested_scopes: [], live_enabled: false,
  busy: false, message: '계정과 연결 방식을 선택하세요.', errorStatus: null});
export function matchesOAuthConnection(row, provider) {
  if (!row || !provider) return false;
  return row.provider_id != null ? row.provider_id === provider.provider_id : row.platform === provider.platform;
}
export function createOAuthController({api, onChange = () => {}}) {
  let state = clean('all'), generation = 0, selection = 0;
  const listeners = new Set();
  const emit = () => { onChange(getState()); for (const listener of listeners) listener(getState()); };
  const getState = () => structuredClone(state);
  const feedback = error => {
    state.errorStatus = error?.status || null;
    state.message = ({401: '다시 로그인하세요. 선택과 대기 요청은 보존했습니다.', 409: '연결이 변경되었습니다. 선택을 보존했으니 최신 상태를 확인하세요.', 503: '저장소 또는 연결 기능을 사용할 수 없습니다. 기존 연결과 입력은 보존했습니다.'})[error?.status] || '요청을 처리하지 못했습니다. 기존 연결과 입력은 보존했습니다.';
  };
  const provider = () => state.catalog.find(row => row.provider_id === state.provider_id);
  const connection = () => state.connections.find(row => (row.connection_id || row.id) === state.connection_id);
  const blocked = row => !row || !providerIds.includes(row.provider_id) || row.login_method === 'unsupported' ||
    row.registration_status !== 'ready' || row.cost_gate !== 'no_additional_cost' || row.policy_gate !== 'allowed' ||
    (row.blockers || []).length > 0 || (row.policy_reasons || []).length > 0;
  const canStart = () => state.account_id !== 'all' && state.live_enabled && !blocked(provider()) && !state.busy;
  function setContext(context = {}) {
    const value = context.account_id ?? context.account ?? 'all';
    if (!accounts.has(value)) throw new Error('계정 범위가 올바르지 않습니다.');
    generation++; selection++;
    state = {...clean(value), provider_id: context.provider_id || '', connection_id: context.connection_id || '',
      base_revision: context.base_revision ?? null, connection_revision: context.connection_revision ?? 0};
    emit();
  }
  function clearSelection() {
    selection++; state.attempt = null; state.pending = null; state.requested_scopes = []; state.errorStatus = null;
    state.connection_id = ''; state.connection_revision = 0;
  }
  function selectProvider(value) {
    if (state.busy) return;
    clearSelection(); state.provider_id = providerIds.includes(value) ? value : ''; state.connection_id = '';
    state.requested_scopes = [...(provider()?.read_scopes || [])]; emit();
  }
  function selectConnection(value) {
    if (state.busy) return;
    const row = state.connections.find(item => (item.connection_id || item.id) === value);
    clearSelection();
    state.connection_id = row && row.account_id === state.account_id && matchesOAuthConnection(row, provider()) ? value : '';
    state.connection_revision = state.connection_id ? row.connection_revision ?? row.revision ?? 0 : 0;
    state.requested_scopes = [...(provider()?.read_scopes || [])]; emit();
  }
  async function load() {
    if (state.busy) return false;
    const current = ++generation; let loaded = false; state.busy = true; emit();
    try {
      const [catalog, connections] = await Promise.all([api.catalog(state.account_id), api.connections(state.account_id)]);
      if (current !== generation) return;
      assertSafeOAuthResponse(catalog); assertSafeOAuthResponse(connections);
      state.catalog = (catalog.items || []).filter(row => providerIds.includes(row.provider_id));
      state.live_enabled = catalog.live_enabled === true;
      state.connections = (connections.items || []).filter(row => state.account_id === 'all' || row.account_id === state.account_id);
      state.base_revision = connections.base_revision;
      const selectedConnection = connection();
      if (selectedConnection) state.connection_revision = selectedConnection.connection_revision ?? selectedConnection.revision ?? 0;
      loaded = true;
      state.message = '권한·비용·준비 상태를 확인하세요. 발행 실행은 비활성입니다.';
    } catch (error) { if (current === generation) feedback(error); }
    finally { if (current === generation) { state.busy = false; emit(); } }
    return loaded;
  }
  async function reloadOwnedResult() {
    if (state.busy) return;
    const current = generation; state.busy = true; emit();
    try {
      const result = assertSafeOAuthResponse(await api.result());
      if (current !== generation) return;
      state.ownedResults = result.items || []; state.attempt = null;
      state.message = '이 세션의 돌아온 시도를 직접 선택하세요. 연결 계속은 별도 확인입니다.';
    } catch (error) { if (current === generation) feedback(error); }
    finally { if (current === generation) { state.busy = false; emit(); } }
  }
  async function selectOwnedAttempt(value) {
    if (state.busy || !state.ownedResults.some(row => row.attempt_id === value && row.account_id === state.account_id)) return;
    const current = generation, selected = ++selection;
    state.attempt = null; state.pending = null; state.busy = true; emit();
    try {
      const result = assertSafeOAuthResponse(await api.attempt(value));
      if (current !== generation || selected !== selection) return;
      if (result.account_id !== state.account_id || result.attempt_id !== value || !providerIds.includes(result.provider_id)) throw new Error();
      state.attempt = result; state.provider_id = result.provider_id;
      state.connection_id = typeof result.connection_id === 'string' ? result.connection_id : '';
      const selectedConnection = connection();
      state.connection_revision = selectedConnection?.connection_revision ?? selectedConnection?.revision ?? result.connection_revision ?? 0;
      if (!selectedConnection && typeof result.base_revision === 'string') state.base_revision = result.base_revision;
      state.message = '동의 복귀는 연결 완료가 아닙니다. 상태를 확인하고 계속하세요.';
    } catch (error) { if (current === generation && selected === selection) feedback(error); }
    finally { if (current === generation && selected === selection) { state.busy = false; emit(); } }
  }
  async function mutate(operation, target, payload) {
    if (state.busy) return;
    const signature = JSON.stringify([operation, target, payload]);
    if (state.pending && state.pending.signature !== signature) {
      state.message = '이전 대기 요청을 확인하거나 선택을 취소한 뒤 다른 동작을 진행하세요.'; emit(); return;
    }
    if (!state.pending) state.pending = {operation, target, signature, ...payload, request_key: requestKey()};
    const {request_key} = state.pending;
    const current = generation, selected = selection;
    state.busy = true; state.errorStatus = null; emit();
    try {
      const result = assertSafeOAuthResponse(await (operation === 'start' ? api.start({...payload, request_key}) : api[operation](target, {...payload, request_key})));
      if (current !== generation || selected !== selection) return;
      if (result.account_id && result.account_id !== state.account_id) throw new Error();
      if (result.provider_id && result.provider_id !== state.provider_id) throw new Error();
      if (['continue', 'inspect'].includes(operation) && result.attempt_id !== target) throw new Error();
      if (result.connection_id && state.connection_id && result.connection_id !== state.connection_id) throw new Error();
      state.pending = null;
      if (result.attempt_id) state.attempt = result;
      if (operation === 'start' && typeof result.connection_id === 'string') {
        state.connection_id = result.connection_id;
        state.connection_revision = result.connection_revision ?? 0;
      }
      state.message = operation === 'disconnect' ? '로컬 연결을 해제했습니다. 제공자의 원격 권한 해지는 수행하지 않았습니다.' :
        operation === 'revoke' ? '원격 권한 해지 결과를 확인하세요. 다른 연결의 영향은 별도입니다.' : '서버 결과를 확인하세요. 발행 실행은 비활성입니다.';
    } catch (error) { if (current === generation && selected === selection) feedback(error); }
    finally { if (current === generation && selected === selection) { state.busy = false; emit(); } }
  }
  function retryPending() {
    if (!state.pending || state.busy) return;
    const {operation, target, signature, request_key, ...payload} = state.pending;
    if (operation === 'start' && !canStart()) {state.message = '현재 등록·비용·정책 상태에서 대기 요청을 재전송할 수 없습니다.'; emit(); return;}
    return mutate(operation, target, payload);
  }
  async function revalidatePending() {
    if (state.busy || !state.pending || state.errorStatus !== 409) return;
    const pending = state.pending;
    if (!['start', 'refresh', 'disconnect', 'revoke'].includes(pending.operation)) {
      state.message = '이 시도는 돌아온 결과에서 최신 상태와 대상을 다시 확인해야 합니다. 대기 요청은 보존했습니다.'; emit(); return;
    }
    if (!await load() || state.pending?.request_key !== pending.request_key) return;
    const selectedConnection = connection();
    if ((state.connection_id && (!selectedConnection || !matchesOAuthConnection(selectedConnection, provider()))) ||
        (pending.operation === 'start' && (!canStart() || state.requested_scopes.some(scope => !provider()?.read_scopes?.includes(scope))))) {
      state.message = '최신 등록·권한·비용·연결 조건이 맞지 않습니다. 원래 대기 요청과 입력은 보존했습니다.'; emit(); return;
    }
    state.connection_revision = selectedConnection?.connection_revision ?? selectedConnection?.revision ?? 0;
    state.pending = null; state.errorStatus = null;
    state.message = '최신 기준으로 재검증했습니다. 입력을 검토한 뒤 다시 누르면 새 요청 키로 제출합니다.'; emit();
  }
  const revisions = () => ({expected_base_revision: state.base_revision, expected_connection_revision: state.connection_revision});
  const start = () => {
    if (!canStart()) {state.message = '로그인 준비가 되지 않았습니다. 계정·등록·권한·비용·정책 차단을 확인하세요.'; emit(); return;}
    return mutate('start', null, {account_id: state.account_id, provider_id: state.provider_id, connection_id: state.connection_id || null,
      ...revisions(), requested_scopes: [...state.requested_scopes]});
  };
  const continueAttempt = () => ['callback_staged', 'resume_pending'].includes(state.attempt?.state) ? mutate('continue', state.attempt.attempt_id, {expected_revision: state.attempt.revision}) : undefined;
  const inspect = () => ['token_exchanged', 'principal_pending'].includes(state.attempt?.state) ? mutate('inspect', state.attempt.attempt_id, {expected_revision: state.attempt.revision}) : undefined;
  const canConfirmTarget = () => {
    const proposal = state.attempt?.target_proposal;
    return state.attempt?.state === 'target_confirmation' &&
      state.attempt.account_id === state.account_id && state.attempt.provider_id === state.provider_id &&
      Number.isInteger(state.attempt.revision) && state.attempt.revision >= 0 && !!proposal &&
      typeof proposal.proposal_id === 'string' && !!proposal.proposal_id &&
      typeof proposal.target_id === 'string' && !!proposal.target_id &&
      typeof proposal.target_label === 'string' &&
      typeof proposal.expected_base_revision === 'string' && !!proposal.expected_base_revision &&
      Number.isInteger(proposal.expected_connection_revision) && proposal.expected_connection_revision >= 0;
  };
  function confirmTarget() {
    const proposal = state.attempt?.target_proposal;
    if (!canConfirmTarget()) {state.message = '대상 제안의 ID와 기준 버전이 미확인입니다. 새 서버 상태를 확인하세요.'; emit(); return;}
    return mutate('confirmTarget', proposal.proposal_id, {expected_base_revision: proposal.expected_base_revision, expected_connection_revision: proposal.expected_connection_revision});
  }
  function connectionAction(operation) {
    const row = connection();
    if (!row || state.account_id === 'all') return;
    if (operation !== 'disconnect' && (!row.available_actions?.includes(operation) || blocked(provider()))) return;
    return mutate(operation, state.connection_id, revisions());
  }
  function close() { generation++; selection++; state = clean(state.account_id); emit(); }
  return {getState, subscribe(listener) {listeners.add(listener); return () => listeners.delete(listener);}, setContext, load, selectProvider, selectConnection,
    clearSelection() {if (!state.busy) {clearSelection(); state.provider_id = ''; state.connection_id = ''; emit();}},
    reloadOwnedResult, selectOwnedAttempt, retryPending, revalidatePending, start, continue: continueAttempt, inspect, confirmTarget,
    refresh: () => connectionAction('refresh'), disconnect: () => connectionAction('disconnect'), revoke: () => connectionAction('revoke'),
    canStart, canConfirmTarget, close, isBusy: () => state.busy, hasUnsavedChanges: () => !!state.pending,
  };
}
