"""고정 loopback(127.0.0.1) Voicebox client. 이미 실행 중인 앱의 generate/history/audio leaf만 호출한다.

URL/host/프록시/리다이렉트/외부 fallback/앱 시작/키 조회가 없고, 생성자는 I/O를 하지 않는다.
오류는 고정 코드의 ContractError로만 나오며 예외·응답 원문은 노출하지 않는다.
"""
import http.client
import json
import re
import time

from common.operations.models import ContractError

HOST = '127.0.0.1'
TIMEOUT_SECONDS = 30
MAX_JSON_BYTES = 1024 * 1024
MAX_WAV_BYTES = 100 * 1024 * 1024
MAX_TEXT_CHARS = 2000
MAX_SEED = 2147483647
_ID = re.compile(r'[A-Za-z0-9_-]{1,128}')
_STATUSES = frozenset(('pending', 'queued', 'running', 'completed', 'failed', 'cancelled'))
_ACTIVE = frozenset(('pending', 'queued', 'running'))
_FIELDS = frozenset(('profile_id', 'text', 'language', 'engine', 'model_size', 'seed', 'normalize', 'max_chunk_chars'))
_UNVERIFIABLE = 'voicebox_recovery_unverifiable'


class VoiceboxGenerationUnknown(ContractError):
    """POST /generate 결과를 알 수 없다. 이미 생성됐을 수 있으므로 자동 재호출하지 않는다."""
    def __init__(self):
        super().__init__('voicebox_generation_unknown')


def _require(condition, code):
    if not condition:
        raise ContractError(code)


def _valid_id(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _canonical_status(value):
    # 설치 Voicebox 0.5.0의 실제 생성 상태만 내부 상태 이름으로 결속한다.
    if value == 'generating':
        return 'running'
    return value


def _limit_for(path):
    return MAX_WAV_BYTES if path.startswith('/audio/') else MAX_JSON_BYTES


class _LoopbackTransport:
    """고정 127.0.0.1:port HTTP. 프록시/리다이렉트 추적 없음. 본문은 limit+1 바이트까지만 읽는다."""
    def __init__(self, port):
        self._port = port

    def __call__(self, method, path, body=None):
        connection = http.client.HTTPConnection(HOST, self._port, timeout=TIMEOUT_SECONDS)
        try:
            headers = {'Accept': 'application/json, audio/wav'}
            if body is not None:
                headers['Content-Type'] = 'application/json'
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            data = response.read(_limit_for(path) + 1)
            return response.status, dict(response.getheaders()), data
        finally:
            connection.close()


class LocalVoiceboxClient:
    def __init__(self, profile_id, *, port=17493, transport=None, clock=time.monotonic, sleep=time.sleep,
                 poll_timeout=600, poll_interval=3):
        _require(_valid_id(profile_id), 'invalid_voicebox_registration')
        _require(type(port) is int and 1 <= port <= 65535, 'invalid_voicebox_registration')
        _require(transport is None or callable(transport), 'invalid_voicebox_registration')
        _require(callable(clock) and callable(sleep), 'invalid_voicebox_registration')
        for value in (poll_timeout, poll_interval):
            _require(type(value) in (int, float) and 0 < value <= 3600, 'invalid_voicebox_registration')
        self.profile_id = profile_id
        self._transport = transport if transport is not None else _LoopbackTransport(port)
        self._clock, self._sleep = clock, sleep
        self._poll_timeout, self._poll_interval = poll_timeout, poll_interval

    # -- 내부 -----------------------------------------------------------------
    def _send(self, method, path, body, limit):
        """(status, bytes) 또는 고정 코드의 None 실패. 호출자가 코드를 선택한다."""
        try:
            result = self._transport(method, path, body)
            status, _headers, data = result
        except Exception:
            return None
        if type(status) is not int or not isinstance(data, (bytes, bytearray)) or len(data) > limit:
            return None
        return status, bytes(data)

    @staticmethod
    def _json(data):
        def reject(_value):
            raise ValueError
        try:
            return json.loads(data.decode('utf-8'), parse_constant=reject)
        except (ValueError, UnicodeDecodeError, RecursionError):
            return None

    def _get_json(self, path):
        sent = self._send('GET', path, None, MAX_JSON_BYTES)
        _require(sent is not None, 'voicebox_unavailable')
        status, data = sent
        _require(200 <= status < 300, 'voicebox_unavailable' if not 300 <= status < 400 else 'voicebox_invalid_response')
        payload = self._json(data)
        _require(payload is not None, 'voicebox_invalid_response')
        return payload

    @staticmethod
    def _projection(payload):
        if not isinstance(payload, dict):
            return None
        generation_id, status = payload.get('id'), _canonical_status(payload.get('status'))
        if not _valid_id(generation_id) or not isinstance(status, str) or status not in _STATUSES:
            return None
        return {'id': generation_id, 'status': status}

    def _recovery_projection(self, payload, generation_id):
        """복구 대조에 필요한 8개 필드만 정확히 검증해 돌려준다. 하나라도 불확실하면 None."""
        if not isinstance(payload, dict):
            return None
        status, profile_id, text = _canonical_status(payload.get('status')), payload.get('profile_id'), payload.get('text')
        seed = payload.get('seed')
        if payload.get('id') != generation_id or not isinstance(status, str) or status not in _STATUSES:
            return None
        if profile_id != self.profile_id:
            return None
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_CHARS or '\x00' in text:
            return None
        try:
            text.encode('utf-8')
        except UnicodeError:
            return None
        if type(seed) is not int or not 0 <= seed <= MAX_SEED:
            return None
        if payload.get('language') != 'ko' or payload.get('engine') != 'qwen' or payload.get('model_size') != '0.6B':
            return None
        return {'id': generation_id, 'status': status, 'profile_id': profile_id, 'text': text, 'seed': seed,
                'language': 'ko', 'engine': 'qwen', 'model_size': '0.6B'}

    # -- 공개 -----------------------------------------------------------------
    def ready(self):
        try:
            payload = self._get_json('/profiles')
        except ContractError:
            return False
        rows = payload.get('profiles') if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return False
        return any(isinstance(row, dict) and row.get('id') == self.profile_id for row in rows)

    def generate(self, **body):
        _require(set(body) == _FIELDS, 'voicebox_invalid_request')
        text = body['text']
        _require(body['profile_id'] == self.profile_id, 'voicebox_profile_mismatch')
        _require(isinstance(text, str) and bool(text.strip()) and len(text) <= MAX_TEXT_CHARS and '\x00' not in text,
                 'voicebox_invalid_request')
        _require(body['language'] == 'ko' and body['engine'] == 'qwen' and body['model_size'] == '0.6B',
                 'voicebox_invalid_request')
        seed = body['seed']
        _require(type(seed) is int and 0 <= seed <= MAX_SEED, 'voicebox_invalid_request')
        _require(body['normalize'] is True, 'voicebox_invalid_request')
        _require(type(body['max_chunk_chars']) is int and body['max_chunk_chars'] == 250, 'voicebox_invalid_request')
        payload = json.dumps(dict(profile_id=self.profile_id, text=text.strip(), language='ko', engine='qwen',
                                  model_size='0.6B', seed=seed, normalize=True, max_chunk_chars=250),
                             ensure_ascii=True, separators=(',', ':')).encode('ascii')
        # 딱 한 번만 POST한다. 이후 어떤 실패도 재시도하지 않는다.
        sent = self._send('POST', '/generate', payload, MAX_JSON_BYTES)
        if sent is None:
            raise VoiceboxGenerationUnknown() from None
        status, data = sent
        if 400 <= status < 500:
            raise ContractError('voicebox_invalid_response')
        if not 200 <= status < 300:
            raise VoiceboxGenerationUnknown() from None
        generated = self._projection(self._json(data))
        if generated is None:
            raise VoiceboxGenerationUnknown() from None
        return generated

    def poll_once(self, generation_id):
        """저장된 생성 ID를 GET 한 번으로 확인한다. 대기·재생성하지 않는다."""
        _require(_valid_id(generation_id), 'voicebox_invalid_request')
        current = self._projection(self._get_json(f'/history/{generation_id}'))
        _require(current is not None and current['id'] == generation_id, 'voicebox_invalid_response')
        return current

    def inspect_generation(self, generation_id):
        """ID 없는 작업의 복구용 읽기 전용 확인. GET /history/{id} 한 번만 호출한다.

        id/status/profile_id/text/seed/language/engine/model_size가 모두 정확히 유효할 때만 그 8개 필드를 돌려준다.
        그 밖의 원문·경로·URL은 버리고, 인증·POST·스캔·재시도·네트워크 fallback은 없다.
        실제 서버의 history 스키마는 검증되지 않았으므로 불확실하면 항상 닫힌 쪽(실패)으로 처리한다.
        """
        _require(_valid_id(generation_id), 'voicebox_invalid_request')
        try:
            payload = self._get_json(f'/history/{generation_id}')
        except ContractError:
            raise ContractError(_UNVERIFIABLE) from None
        candidate = self._recovery_projection(payload, generation_id)
        _require(candidate is not None, _UNVERIFIABLE)
        return candidate

    def wait_completed(self, generation_id):
        _require(_valid_id(generation_id), 'voicebox_invalid_request')
        deadline = self._clock() + self._poll_timeout
        attempts = int(self._poll_timeout / self._poll_interval) + 2
        for _ in range(attempts):
            current = self.poll_once(generation_id)
            if current['status'] == 'completed':
                return current
            _require(current['status'] in _ACTIVE, 'voicebox_generation_failed')
            remaining = deadline - self._clock()
            if remaining <= 0:
                break
            self._sleep(min(self._poll_interval, remaining))
        raise ContractError('voicebox_poll_timeout')

    def audio(self, generation_id):
        _require(_valid_id(generation_id), 'voicebox_invalid_request')
        sent = self._send('GET', f'/audio/{generation_id}', None, MAX_WAV_BYTES + 1)
        _require(sent is not None, 'voicebox_unavailable')
        status, data = sent
        _require(status == 200, 'voicebox_unavailable')
        _require(len(data) <= MAX_WAV_BYTES, 'voicebox_audio_invalid')
        _require(len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WAVE', 'voicebox_audio_invalid')
        return data
