import io
import unittest
from datetime import datetime, timezone
import http.client
import threading
from contextlib import contextmanager
from common.operations.media_lease_http import make_media_handler, build_media_server, CHUNK_SIZE

TOKEN = 'a' * 64
PATH = '/media/v1/' + TOKEN
NOW = datetime(2026, 11, 4, tzinfo=timezone.utc)
EXPIRED = datetime(2030, 1, 1, tzinfo=timezone.utc)


class Store:
    def __init__(self, media_type='video/mp4', payload=b'0123456789'):
        self.payload = payload
        self.metadata = dict(lease_id='lease', asset_size=len(payload), media_type=media_type,
                             request={}, authority={}, expires_at='2030-01-01T00:00:00Z')
        self.active = True
        self.opens = 0
        self.reads = []
        self.after_read = lambda: None

    def lookup(self, token, *, now):
        return self.metadata if self.active and token == TOKEN and now < EXPIRED else None

    def is_active(self, lease_id, *, now):
        return self.active and now < EXPIRED

    @contextmanager
    def open_payload(self, lease_id, *, now):
        self.opens += 1
        owner = self
        class Payload(io.BytesIO):
            def read(self, size):
                owner.reads.append(size)
                result = super().read(size)
                owner.after_read()
                return result
        yield Payload(self.payload)


class Socket:
    def __init__(self, request):
        self.input = io.BytesIO(request)
        self.output = io.BytesIO()
    def makefile(self, *_args, **_kwargs):
        return self.input
    def sendall(self, data):
        self.output.write(data)


class MediaHTTPTests(unittest.TestCase):
    def exchange(self, store=None, *, method='GET', target=PATH, headers=(),
                 allowed=lambda: True, authority=lambda meta: True, now=NOW):
        store = store or Store()
        handler = make_media_handler(store, authority_guard=authority,
                                     serving_allowed=allowed, clock=lambda: now,
                                     expected_host='127.0.0.1:9999')
        request = f'{method} {target} HTTP/1.1\r\nHost: 127.0.0.1:9999\r\n'
        request += ''.join(f'{k}: {v}\r\n' for k, v in headers) + '\r\n'
        sock = Socket(request.encode())
        handler(sock, ('127.0.0.1', 1234), object())
        raw = sock.output.getvalue()
        head, _, body = raw.partition(b'\r\n\r\n')
        lines = head.decode().split('\r\n')
        return int(lines[0].split()[1]), dict(line.split(': ', 1) for line in lines[1:]), body

    def test_original_and_headers(self):
        status, headers, body = self.exchange()
        self.assertEqual((status, body), (200, b'0123456789'))
        self.assertEqual(headers['Cache-Control'], 'no-store, no-transform')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        for name in ('Server', 'Set-Cookie', 'Access-Control-Allow-Origin', 'Location'):
            self.assertNotIn(name, headers)

    def test_strict_raw_routes(self):
        for target in (PATH+'?x=1', PATH+'#x', PATH+'/', PATH.upper(), '//media/v1/'+TOKEN,
                       '/media/v1/%61'+TOKEN[1:], 'http://127.0.0.1:9999'+PATH,
                       '/media/../media/v1/'+TOKEN):
            with self.subTest(target=target):
                self.assertEqual(self.exchange(target=target)[0], 400)

    def test_headers_and_methods(self):
        for headers in ((('Host', 'evil'),), (('Range','bytes=1-2'),('Range','bytes=3-4')),
                        (('Content-Length','0'),('Content-Length','0')),
                        (('Content-Length','1'),), (('Transfer-Encoding','chunked'),),
                        (('Forwarded','host=evil'),), (('Expect','100-continue'),), (('X-Forwarded-Host','evil'),)):
            self.assertEqual(self.exchange(headers=headers)[0], 400)
        for method in ('POST','PUT','DELETE','PATCH','OPTIONS','CONNECT','TRACE'):
            store = Store()
            self.assertEqual(self.exchange(store, method=method)[0], 405)
            self.assertEqual(store.opens, 0)

    def test_guards_expiration_revocation(self):
        for options in (dict(allowed=lambda: False), dict(authority=lambda m: None),
                        dict(now=EXPIRED)):
            store = Store()
            self.assertEqual(self.exchange(store, **options)[0], 404)
            self.assertEqual(store.opens, 0)
        store = Store()
        store.active = False
        self.assertEqual(self.exchange(store)[0], 404)

    def test_ranges_and_head(self):
        for value, expected, content_range in (
                ('bytes=2-4', b'234', 'bytes 2-4/10'),
                ('bytes=7-', b'789', 'bytes 7-9/10'),
                ('bytes=-3', b'789', 'bytes 7-9/10'),
                ('bytes=0-99', b'0123456789', 'bytes 0-9/10')):
            status, headers, body = self.exchange(headers=(('Range', value),))
            self.assertEqual((status, body, headers['Content-Range']), (206, expected, content_range))
            store = Store()
            hs, hh, hb = self.exchange(store, method='HEAD', headers=(('Range',value),))
            self.assertEqual((hs, hh, hb), (status, headers, b''))
            self.assertEqual(store.opens, 0)
        for value in ('bytes=10-', 'bytes=5-1', 'bytes=-0', 'bytes=-',
                      'bytes=1-2,4-5', 'items=1-2'):
            status, headers, body = self.exchange(headers=(('Range', value),))
            self.assertEqual((status, headers['Content-Range'], body), (416, 'bytes */10', b''))
        self.assertEqual(self.exchange(Store('image/jpeg'), headers=(('Range','bytes=1-2'),))[0],416)
        self.assertEqual(self.exchange(Store('image/jpeg'))[2], b'0123456789')

    def test_authority_loss_and_store_errors_fail_closed(self):
        store = Store()
        calls = [0]
        def authority(metadata):
            calls[0] += 1
            return calls[0] == 1
        self.assertEqual(self.exchange(store, authority=authority)[0], 404)
        self.assertEqual(store.reads, [])
        def broken_lookup(token, *, now):
            raise OSError('private internal detail')
        store.lookup = broken_lookup
        status, headers, body = self.exchange(store)
        self.assertEqual((status, body), (404, b''))

    def test_stream_checks_stop_and_revocation(self):
        for mode in ('stop','revoke'):
            store = Store(payload=b'x' * (CHUNK_SIZE * 3))
            allowed = [True]
            def change():
                if mode == 'stop':
                    allowed[0] = False
                else:
                    store.active = False
            store.after_read = change
            status, headers, body = self.exchange(store, allowed=lambda: allowed[0])
            self.assertEqual(status, 200)
            self.assertEqual(len(body), CHUNK_SIZE)
            self.assertEqual(store.reads, [CHUNK_SIZE])

    def test_loopback_server(self):
        server = build_media_server(Store(), enabled=True, clock=lambda: NOW,
                                    authority_guard=lambda m: True,
                                    serving_allowed=lambda: True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
            conn.request('GET', PATH, headers={'Range': 'bytes=2-4'})
            response = conn.getresponse()
            self.assertEqual((response.status, response.read()), (206, b'234'))
            conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_builder_disabled_and_nonloopback(self):
        for options in ({}, dict(enabled=True, host='0.0.0.0')):
            with self.assertRaises(ValueError):
                build_media_server(Store(), authority_guard=lambda m: True,
                                   serving_allowed=lambda: True, **options)


if __name__ == '__main__':
    unittest.main()
