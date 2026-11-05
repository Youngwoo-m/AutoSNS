"""tistory adapter와 서버 고정 child launcher. import는 I/O를 하지 않는다."""
from .blog_adapter import BlogAdapter


def build_adapter(registry, bridge):
    return BlogAdapter('tistory', registry, bridge)


def bridge_bootstrap():
    from .blog_runtime import bridge_bootstrap as bootstrap
    return bootstrap('tistory')


if __name__ == '__main__':
    from .bridge_host import main
    raise SystemExit(main(bootstrap=bridge_bootstrap, bootstrap_module=__spec__.name))
