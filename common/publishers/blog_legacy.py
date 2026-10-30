"""서버 고정 다섯 연결→leaf 파일. 요청의 모듈·경로를 해석하지 않는다."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
LEAVES = {
    'dept.blogger': 'dept/naver-blog-auto/post_blogger.py',
    'personal.blogger': 'dept/naver-blog-auto/geoai_blogger.py',
    'dept.naver_blog': 'dept/naver-blog-auto/publish_naver.py',
    'personal.naver_blog': 'dept/naver-blog-auto/naver_crosspost_personal.py',
    'personal.tistory': 'personal/naver-blog-auto/tistory_post.py',
}


def load_blog_leaf(connection_id):
    relative = LEAVES.get(connection_id)
    if relative is None: raise ValueError('blog_connection_unregistered')
    name = '_autosns_managed_' + connection_id.replace('.', '_')
    return _load_fixed(name, relative)


def load_tistory_support():
    return _load_fixed('_autosns_managed_tistory_crosspost', 'personal/naver-blog-auto/tistory_crosspost.py')


def _load_fixed(name, relative):
    if name in sys.modules: return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module
