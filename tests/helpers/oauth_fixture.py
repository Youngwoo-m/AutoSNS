"""Node 통합 시험 전용 JSON-lines bridge. 외부/native 호출 없이 실제 HTTP 사용."""
from dataclasses import replace
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.test_web_oauth import OAuthHTTPTests


def main():
    fixture = OAuthHTTPTests()
    fixture.setUp()
    # UI URL allowlist를 통과하지만 실제 요청은 하지 않는 가짜 authorize URL.
    original = fixture.fixture.provider.authorize
    def authorize(attempt, client):
        return original(attempt, client).replace('https://provider.test/authorize', 'https://accounts.google.com/o/oauth2/v2/auth')
    fixture.fixture.provider.authorize = authorize
    fixture.fixture.provider.definition = replace(fixture.fixture.provider.definition, operations=tuple(
        replace(rule, endpoint='https://accounts.google.com/o/oauth2/v2/auth') if rule.operation == 'authorize' else rule
        for rule in fixture.fixture.provider.definition.operations))
    fixture.server.oauth_service = fixture.fixture.make_service()
    try:
        for line in sys.stdin:
            value = json.loads(line)
            if value.get('command') == 'callback':
                status, headers, data = fixture.callback(value['state'])
                result = {'status': status, 'headers': headers}
            elif value.get('command') == 'restart':
                fixture.server.oauth_service = fixture.fixture.make_service()
                result = {'status': 200}
            else:
                headers_in = value.get('headers') or {}
                if value.get('method') == 'POST':
                    headers_in['Origin'] = 'http://127.0.0.1:' + str(fixture.server.server_port)
                status, headers, data = fixture.request(value['path'], value.get('method', 'GET'),
                    raw=value.get('body'), cookie=value.get('cookie', 'fixture'), headers=headers_in)
                result = {'status': status, 'headers': headers, 'body': data.decode()}
            print(json.dumps(result), flush=True)
    finally:
        fixture.doCleanups()


if __name__ == '__main__':
    main()
