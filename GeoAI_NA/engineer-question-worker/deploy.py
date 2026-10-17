"""Deploy only the static website; credentials and queue are never included."""
import io, json, time, zipfile
from netlify_api import api, SITE_ID, SITE_DIR

def deploy():
    archive=io.BytesIO()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for path in sorted(SITE_DIR.rglob('*')):
            relative=path.relative_to(SITE_DIR)
            if path.is_file() and not any(part.startswith('.') for part in relative.parts):
                z.write(path,relative.as_posix())
    result=api('/sites/'+SITE_ID+'/deploys?title=Engineer-question-portal', 'POST', archive.getvalue(),'application/zip')
    deploy_id=result['id']
    print(json.dumps({'deploy_id':deploy_id,'state':result.get('state')},ensure_ascii=False),flush=True)
    for attempt in range(20):
        current=api('/deploys/'+deploy_id)
        if current['state']=='ready':
            print(json.dumps({'state':'ready','url':current.get('ssl_url'),'deploy_url':current.get('deploy_ssl_url')},ensure_ascii=False))
            return current
        if current['state']=='error': raise RuntimeError(current.get('error_message','Deploy failed'))
        time.sleep(3)
    raise RuntimeError('Deploy confirmation timed out: '+deploy_id)

if __name__=='__main__': deploy()
