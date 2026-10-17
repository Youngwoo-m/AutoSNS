"""공통 틀 점검용 에이전트: 콘솔 문서 목록을 보고 한 문서를 읽어 요약해 제출한다(읽기만)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_core import Agent, Budget, Tool, submit_tool, CONSOLE  # noqa: E402

DOCS = CONSOLE / 'docs'


def list_docs():
    return [p.name for p in sorted(DOCS.glob('*.md'))]


def read_doc(name):
    p = (DOCS / name).resolve()
    if p.parent != DOCS.resolve() or not p.exists():
        raise ValueError('docs 폴더의 문서만 읽을 수 있습니다')
    return p.read_text()


def main(max_tokens):
    tools = [Tool('list_docs', 'AX 콘솔 docs 폴더의 문서 이름 목록', {'type': 'object', 'properties': {}}, list_docs),
             Tool('read_doc', '문서 하나를 읽는다', {'type': 'object', 'properties': {'name': {'type': 'string'}},
                                                   'required': ['name']}, read_doc, max_calls=3),
             submit_tool('결과 제출', {'type': 'object', 'properties': {
                 'doc': {'type': 'string'}, 'summary': {'type': 'string', 'description': '3줄 요약'}},
                 'required': ['doc', 'summary']})]
    a = Agent('selftest', '너는 문서를 찾아 요약하는 도우미다.', tools, Budget(max_tokens=max_tokens, max_turns=8))
    r = a.run('파이프라인 문서를 찾아 ⑥ 발행 단계를 3줄로 요약해 제출하라.')
    print(json.dumps(r.__dict__, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40000)
