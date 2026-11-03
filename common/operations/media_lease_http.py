"""Opt-in loopback transport for opaque media leases; never starts a service.

Both guards must return literal True. serving_allowed() means STOP is absent and
serving is currently permitted; authority_guard(metadata) verifies current authority.
Authority is checked before response headers. STOP and explicit lease revocation
are checked per chunk; later authority changes apply to the next request.
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
import re
import threading
from datetime import datetime, timezone

CHUNK_SIZE = 64 * 1024
_ROUTE = re.compile(r"/media/v1/([0-9a-f]{64})\Z")
def _utc_now():
    return datetime.now(timezone.utc)


_RANGE = re.compile(r"bytes=([0-9]*)-([0-9]*)\Z")


def make_media_handler(store, *, authority_guard, serving_allowed, clock=_utc_now,
                       expected_host):
    """Create a fail-closed handler. Store owns expiration and payload validation."""
    if not expected_host or any(c in expected_host for c in '/\r\n '):
        raise ValueError('invalid expected_host')

    class MediaHandler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def handle_expect_100(self):
            self._headers(400)
            return False

        def log_message(self, *_args):
            pass  # Tokens and raw request targets must never enter access logs.

        def send_response(self, code, message=None):
            self.send_response_only(code, message)  # No identifying Server header.

        def _headers(self, status, length=0, *, media_type=None, content_range=None):
            self._response_started = True
            self.send_response(status)
            self.send_header('Content-Length', str(length))
            self.send_header('Cache-Control', 'no-store, no-transform')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Connection', 'close')
            if media_type:
                self.send_header('Content-Type', media_type)
                self.send_header('Content-Disposition', 'inline; filename="media.' +
                                 ('mp4' if media_type == 'video/mp4' else 'jpg') + '"')
                if media_type == 'video/mp4':
                    self.send_header('Accept-Ranges', 'bytes')
            if content_range:
                self.send_header('Content-Range', content_range)
            self.end_headers()
            self.close_connection = True

        def _allowed(self, metadata=None):
            try:
                return (serving_allowed() is True and
                        (metadata is None or authority_guard(metadata) is True))
            except Exception:
                return False

        def _valid_request(self):
            # Inspect raw target: BaseHTTPRequestHandler normalizes leading //.
            parts = self.raw_requestline.rstrip(b'\r\n').split(b' ')
            if len(parts) != 3:
                return None
            try:
                target = parts[1].decode('ascii')
            except UnicodeDecodeError:
                return None
            match = _ROUTE.fullmatch(target)
            if not match:
                return None
            for name in ('Host', 'Range', 'Content-Length'):
                if len(self.headers.get_all(name, [])) > 1:
                    return None
            if self.headers.get('Host') != expected_host:
                return None
            for name in self.headers:
                low = name.lower()
                if low in ('transfer-encoding', 'forwarded', 'expect') or low.startswith('x-forwarded-'):
                    return None
            if self.headers.get('Content-Length') not in (None, '0'):
                return None
            return match.group(1)

        def _serve(self, head=False):
            self._response_started = False
            token = self._valid_request()
            if token is None:
                self._headers(400)
                return
            if not self._allowed():
                self._headers(404)
                return
            try:
                metadata = store.lookup(token, now=clock())
                if metadata is None or not self._allowed(metadata):
                    self._headers(404)
                    return
                size = metadata['asset_size']
                media_type = metadata['media_type']
                if type(size) is not int or size <= 0 or media_type not in ('image/jpeg', 'video/mp4'):
                    self._headers(404)
                    return
                start, end, status = 0, size - 1, 200
                requested = self.headers.get('Range')
                if requested is not None:
                    match = _RANGE.fullmatch(requested) if media_type == 'video/mp4' else None
                    if not match or not any(match.groups()):
                        self._headers(416, content_range=f'bytes */{size}')
                        return
                    first, last = match.groups()
                    if first:
                        start = int(first)
                        end = min(int(last), size - 1) if last else size - 1
                    else:
                        suffix = int(last)
                        start = max(0, size - suffix)
                    if start > end or start >= size or (not first and int(last) == 0):
                        self._headers(416, content_range=f'bytes */{size}')
                        return
                    status = 206
                length = end - start + 1
                crange = f'bytes {start}-{end}/{size}' if status == 206 else None
                if not self._allowed(metadata if head else None) or not store.is_active(metadata['lease_id'], now=clock()):
                    self._headers(404)
                    return
                if head:
                    self._headers(status, length, media_type=media_type, content_range=crange)
                    return
                with store.open_payload(metadata['lease_id'], now=clock()) as payload:
                    payload.seek(start)
                    if not self._allowed(metadata) or not store.is_active(metadata['lease_id'], now=clock()):
                        self._headers(404)
                        return
                    self._headers(status, length, media_type=media_type, content_range=crange)
                    remaining = length
                    while remaining:
                        if not self._allowed() or not store.is_active(metadata['lease_id'], now=clock()):
                            return
                        chunk = payload.read(min(CHUNK_SIZE, remaining))
                        if not chunk:
                            return
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except Exception:
                # Once headers began, close rather than emit a second response.
                if not self._response_started:
                    self._headers(404)
                self.close_connection = True

        def do_GET(self):
            self._serve()

        def do_HEAD(self):
            self._serve(head=True)

        def _unsupported(self):
            self._headers(405)

        do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_CONNECT = do_TRACE = _unsupported

        def send_error(self, code, message=None, explain=None):
            self._headers(code)

    return MediaHandler


class _BoundedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 8

    def __init__(self, address, handler, *, max_connections, socket_timeout):
        self._slots = threading.BoundedSemaphore(max_connections)
        self._socket_timeout = socket_timeout
        super().__init__(address, handler)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(self._socket_timeout)
        return request, address

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


def build_media_server(store, *, authority_guard, serving_allowed, enabled=False,
                       host='127.0.0.1', port=0, expected_host=None, clock=_utc_now,
                       max_connections=4, socket_timeout=5):
    """Bind only when explicitly enabled; caller owns serve_forever and server_close.

    This dedicated listener must never be attached to the administrative server.
    expected_host is exact; by default use the bound loopback address and port.
    """
    if enabled is not True:
        raise ValueError('media transport disabled')
    if host != '127.0.0.1' or not 1 <= max_connections <= 32 or not 0 < socket_timeout <= 60:
        raise ValueError('invalid loopback server configuration')
    # Bind before deriving Host when requesting an ephemeral test port.
    server = _BoundedServer((host, port), BaseHTTPRequestHandler,
                            max_connections=max_connections, socket_timeout=socket_timeout)
    try:
        server.RequestHandlerClass = make_media_handler(
            store, authority_guard=authority_guard, serving_allowed=serving_allowed,
            clock=clock, expected_host=expected_host or f'{host}:{server.server_port}')
    except BaseException:
        server.server_close()
        raise
    return server
