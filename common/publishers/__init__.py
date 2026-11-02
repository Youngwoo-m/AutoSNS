"""서버가 명시 등록한 연결만 조립한다. 인자 없는 factory는 외부 I/O 없이 빈 값이다."""
def build_adapters(*,registry=None,bridge=None):
    if registry is None or bridge is None:return {}
    from .blog_runtime import BLOG_BINDINGS
    from .youtube_runtime import YOUTUBE_BINDINGS
    from .blog_adapter import BlogAdapter
    from .youtube import YoutubeAdapter
    from .threads_runtime import THREADS_BINDINGS
    from .threads import ThreadsAdapter
    from .facebook_runtime import FACEBOOK_BINDINGS
    from .facebook import FacebookAdapter
    from .instagram_runtime import INSTAGRAM_BINDINGS
    from .instagram import InstagramAdapter
    result={}
    for key in BLOG_BINDINGS:
        connection=registry.connections.get(key)
        if connection and connection.enabled and connection.target_id:
            result[key]=BlogAdapter(connection.platform,registry,bridge)
    for key in YOUTUBE_BINDINGS:
        connection=registry.connections.get(key)
        if connection and connection.enabled and connection.target_id:result[key]=YoutubeAdapter(registry,bridge)
    for key in THREADS_BINDINGS:
        connection=registry.connections.get(key)
        if connection and connection.enabled and connection.target_id:result[key]=ThreadsAdapter(registry,bridge)
    for key in FACEBOOK_BINDINGS:
        connection=registry.connections.get(key)
        if connection and connection.enabled and connection.platform=='facebook' and connection.target_id:
            result[key]=FacebookAdapter(registry,bridge)
    for key in INSTAGRAM_BINDINGS:
        connection=registry.connections.get(key)
        if connection and connection.enabled and connection.platform=='instagram' and connection.target_id:
            result[key]=InstagramAdapter(registry,bridge)
    return result
