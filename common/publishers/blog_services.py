"""Google client/DOM의 최하위 서비스. 준비·import에는 연결·파일 접근이 없다."""
from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit
import hashlib
import tempfile

from .blog_legacy import ROOT

PROFILES = {
    'dept.naver_blog': ROOT / 'dept/naver-blog-auto/chrome-profile',
    'personal.naver_blog': ROOT / 'dept/naver-blog-auto/chrome-profile-safeworking',
    'personal.tistory': ROOT / 'personal/naver-blog-auto/chrome-profile-tistory',
}


def _observation(target, authenticated, subject=None, reason=None):
    return dict(platform=target['platform'], target_id=target['target_id'] if authenticated else None,
                authenticated=authenticated, login_subject=subject,
                verification_method='immutable_blog_membership', status='ready' if authenticated else 'needs_review',
                reason=reason)


def target_matches(observed, target):
    return (isinstance(observed, Mapping) and observed.get('authenticated') is True
            and observed.get('target_id') == target['target_id']
            and isinstance(observed.get('login_subject'), str) and bool(observed['login_subject'])
            and (not target.get('expected_login_subject') or observed['login_subject'] == target['expected_login_subject']))


class GoogleBlogServices:
    def __init__(self, service, *, public_service=None, clock=None):
        self.service, self.public_service = service, public_service
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.before_write = lambda: None

    def inspect(self, target):
        try:
            subject = self.service.users().get(userId='self').execute().get('id')
            blog = self.service.blogs().get(blogId=target['target_id']).execute()
            membership = self.service.blogs().listByUser(userId='self', view='AUTHOR').execute()
            allowed = blog.get('id') == target['target_id'] and any(row.get('id') == target['target_id'] for row in membership.get('items', []))
            observed = _observation(target, bool(allowed and isinstance(subject, str) and subject), subject)
            if not target_matches(observed, target): return _observation(target, False, subject, 'target_or_login_mismatch')
            return observed
        except Exception:
            result = _observation(target, False, reason='authentication_required')
            result['status'] = 'needs_auth'
            return result

    def submit(self, prepared, target):
        if not target_matches(self.inspect(target), target):
            return {'outcome': 'failed', 'evidence': {'reason': 'target_unverified', 'confirmed_not_submitted': True}}
        if prepared.get('assets'):
            # Blogger에는 별도 media upload API가 없다. 공개 업로드를 몰래 준비하지 않는다.
            return {'outcome': 'failed', 'evidence': {'reason': 'blogger_asset_upload_unsupported', 'confirmed_not_submitted': True}}
        body = dict(kind='blogger#post', title=prepared['title'], content=prepared['body_html'], labels=prepared.get('labels', []))
        try:
            self.before_write()
            result = self.service.posts().insert(blogId=target['target_id'], body=body, isDraft=False).execute()
            if not isinstance(result.get('id'), str) or not result['id']:
                return {'outcome': 'unknown', 'url': result.get('url'), 'evidence': {'reason': 'remote_id_missing'}}
            return dict(outcome='submitted', remote_id=result['id'], url=result.get('url'))
        except Exception:
            return {'outcome': 'unknown', 'evidence': {'reason': 'blog_submission_uncertain'}}

    def lookup(self, target, attempt):
        if not target_matches(self.inspect(target), target): return {'items': [], 'unsupported': True}
        remote_id = attempt.get('remote_id') or (attempt.get('result') or {}).get('remote_id')
        if remote_id:
            raw = self.verify(target, remote_id)
            return {'items': [raw] if raw else [], 'unsupported': not bool(raw)}
        try:
            result = self.service.posts().list(blogId=target['target_id'], fetchBodies=True, maxResults=100,
                        startDate=attempt.get('created_at'), endDate=self.clock().isoformat(), view='AUTHOR').execute()
            return dict(items=result.get('items', []), unsupported=bool(result.get('nextPageToken')))
        except Exception:
            return {'items': [], 'unsupported': True}

    def verify(self, target, remote_id):
        if not isinstance(remote_id, str) or not remote_id: return None
        if not target_matches(self.inspect(target), target): return None
        try:
            raw = self.service.posts().get(blogId=target['target_id'], postId=remote_id, view='ADMIN').execute()
            if raw.get('id') != remote_id or (raw.get('blog') or {}).get('id') != target['target_id']: return raw
            if self.public_service is not None:
                try:
                    public = self.public_service.posts().get(blogId=target['target_id'], postId=remote_id, view='READER').execute()
                    # 공개 응답 자체의 본문·대상으로 검증한다. 관리자 응답에 공개 flag만 덧씌우지 않는다.
                    if public.get('id') == remote_id and (public.get('blog') or {}).get('id') == target['target_id']:
                        raw = dict(public, visibility='public', publicly_readable=True)
                except Exception:
                    pass
            return raw
        except Exception:
            return None


# 실제 DOM의 불변 data attribute와 관리 링크만 읽는다. 표시명·제목을 ID로 바꾸지 않는다.
IDENTITY_JS = r'''/* AX_BLOG_IDENTITY_READ */
const subjects = [...document.querySelectorAll('[data-user-id]')].map(e=>e.getAttribute('data-user-id')).filter(Boolean);
const targets = [...document.querySelectorAll('[data-blog-id]')].map(e=>({id:e.getAttribute('data-blog-id'),url:e.href||e.getAttribute('data-blog-url')})).filter(e=>e.id);
return {authenticated:new Set(subjects).size===1,login_subject:new Set(subjects).size===1?subjects[0]:null,targets};
'''
REMOTE_JS = r'''/* AX_BLOG_REMOTE_READ */
const post=document.querySelector('[data-post-id][data-blog-id]');
if(!post)return null;
const body=post.querySelector('.contents_style,.se-main-container,[data-post-body]');
const visible=post.getAttribute('data-visibility');
return {remote_id:post.getAttribute('data-post-id'),target_id:post.getAttribute('data-blog-id'),
body_html:body?body.innerHTML:null,created_at:post.getAttribute('data-published-at'),
visibility:visible||'unknown',media:body&&!body.querySelector('img,video,audio,source,iframe,object,embed,a[download]')?[]:null,url:location.href};
'''


def chrome_driver(profile):
    if Path(profile) == PROFILES['personal.tistory']:
        from .blog_legacy import load_tistory_support
        return load_tistory_support().build_read_driver(profile=profile, headless=True)
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    options = Options()
    options.add_argument('--user-data-dir=' + str(profile))
    options.add_argument('--headless=new')
    options.add_argument('--lang=ko-KR')
    options.add_experimental_option('excludeSwitches', ['enable-automation', 'use-mock-keychain'])
    options.set_capability('unhandledPromptBehavior', 'dismiss')
    return webdriver.Chrome(options=options)


class BrowserBlogServices:
    def __init__(self, connection_id, *, driver_factory=chrome_driver, asset_reader=None, clock=None):
        if connection_id not in PROFILES: raise ValueError('blog_connection_unregistered')
        self.connection_id, self.driver_factory = connection_id, driver_factory
        self.profile = PROFILES[connection_id]
        self.asset_reader = asset_reader
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.before_write = lambda: None

    @contextmanager
    def _driver(self):
        driver = self.driver_factory(self.profile)
        try: yield driver
        finally: driver.quit()  # restore/save/relogin을 호출하지 않는다.

    def _identity(self, driver, target):
        driver.get('https://www.tistory.com/' if target['platform'] == 'tistory' else 'https://blog.naver.com/MyBlog.naver')
        identity = driver.execute_script(IDENTITY_JS)
        if not isinstance(identity, Mapping): return _observation(target, False, reason='identity_dom_unavailable'), None
        if identity.get('authenticated') is not True:
            observed = _observation(target, False, reason='authentication_required')
            observed['status'] = 'needs_auth'
            return observed, None
        matches = [item for item in identity.get('targets', []) if isinstance(item, Mapping) and item.get('id') == target['target_id']]
        subject = identity.get('login_subject')
        observed = _observation(target, identity.get('authenticated') is True and len(matches) == 1, subject)
        if not target_matches(observed, target): return _observation(target, False, subject, 'identity_dom_unavailable'), None
        return observed, matches[0]

    def inspect(self, target):
        with self._driver() as driver:
            observed, _ = self._identity(driver, target)
            return observed

    def _blog_url(self, target, member, suffix):
        if target['platform'] == 'tistory':
            parsed = urlsplit(member.get('url') or '')
            if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.tistory.com') or parsed.username or parsed.password:
                raise ValueError('target_url_unverified')
            return 'https://' + parsed.hostname + suffix
        return 'https://blog.naver.com/' + suffix

    def submit(self, prepared, target, input_leaf, upload_leaf=None, configure_leaf=None):
        if prepared.get('assets') and (not callable(self.asset_reader) or not callable(upload_leaf)):
            return {'outcome': 'failed', 'evidence': {'reason': 'reviewed_asset_reader_unavailable', 'confirmed_not_submitted': True}}
        started = False
        try:
            with self._driver() as driver:
                observed, member = self._identity(driver, target)
                if not target_matches(observed, target):
                    return {'outcome': 'failed', 'evidence': {'reason': 'target_unverified', 'confirmed_not_submitted': True}}
                editor = self._blog_url(target, member, '/manage/newpost/' if target['platform'] == 'tistory'
                                        else 'GoBlogWrite.naver?blogId=' + quote(target['target_id'], safe=''))
                driver.get(editor)
                # 편집기 이동 후에도 대상/로그인 근거가 유지돼야 한다.
                identity = driver.execute_script(IDENTITY_JS)
                if (not isinstance(identity, Mapping) or identity.get('login_subject') != observed['login_subject']
                    or not any(item.get('id') == target['target_id'] for item in identity.get('targets', []) if isinstance(item, Mapping))):
                    return {'outcome': 'failed', 'evidence': {'reason': 'editor_target_unverified', 'confirmed_not_submitted': True}}
                # 입력/첨부도 서버 부작용이다. 이후 실패는 미발행으로 단정하지 않는다.
                self.before_write()
                started = True
                input_leaf(driver, prepared)
                for asset in prepared.get('assets', []):
                    meta, data = self.asset_reader(asset['id'])
                    if meta.get('sha256') != asset.get('sha256') or hashlib.sha256(data).hexdigest() != asset.get('sha256'):
                        raise ValueError('asset_changed')
                    filename = Path(meta['filename']).name
                    with tempfile.TemporaryDirectory(prefix='autosns-blog-asset-') as directory:
                        path = Path(directory) / filename
                        path.write_bytes(data)
                        self.before_write()
                        upload_leaf(driver, str(path))
                if configure_leaf is not None:
                    configure_leaf(driver, prepared)
                self.before_write()
                result = driver.execute_script('''/* AX_BLOG_FINAL_PUBLISH */
const button=document.querySelector(arguments[0]);if(!button)throw Error('publish selector unavailable');button.click();
''', '#publish-btn' if target['platform'] == 'tistory' else 'button.confirm_btn__WEaBq,button[data-action="publish-confirm"]')
                # 최종 결과의 실제 원격 ID 없이는 성공을 만들지 않는다.
                result = driver.execute_script('''/* AX_BLOG_SUBMIT_RESULT */
const p=document.querySelector('[data-post-id][data-blog-id]');
return p?{remote_id:p.getAttribute('data-post-id'),target_id:p.getAttribute('data-blog-id'),url:location.href}:null;
''')
                if not isinstance(result, Mapping) or not isinstance(result.get('remote_id'), str) or not result['remote_id']:
                    return {'outcome': 'unknown', 'evidence': {'reason': 'remote_id_missing'}}
                if result.get('target_id') != target['target_id']:
                    return {'outcome': 'unknown', 'evidence': {'reason': 'remote_target_missing'}}
                return dict(outcome='submitted', remote_id=result['remote_id'], url=result.get('url'))
        except Exception:
            return {'outcome': 'unknown' if started else 'failed', 'evidence': {'reason': 'blog_submission_uncertain' if started else 'target_unverified'}}

    def lookup(self, target, attempt):
        remote_id = attempt.get('remote_id') or (attempt.get('result') or {}).get('remote_id')
        if not remote_id: return {'items': [], 'unsupported': True}  # 제목 검색은 강한 일치 근거가 아니다.
        raw = self.verify(target, remote_id)
        return {'items': [raw] if raw else [], 'unsupported': not bool(raw)}

    def verify(self, target, remote_id):
        if not isinstance(remote_id, str) or not remote_id: return None
        with self._driver() as driver:
            observed, member = self._identity(driver, target)
            if not target_matches(observed, target): return None
            if target['platform'] == 'tistory':
                if not remote_id.isdecimal(): return None
                url = self._blog_url(target, member, '/' + remote_id)
            else:
                url = self._blog_url(target, member, 'PostView.naver?blogId=' + quote(target['target_id'], safe='') + '&logNo=' + quote(remote_id, safe=''))
            driver.get(url)
            return driver.execute_script(REMOTE_JS)


def create_blog_services(connection_id, credentials):
    if connection_id.endswith('.blogger'):
        from googleapiclient.discovery import build
        service = build('blogger', 'v3', credentials=credentials, cache_discovery=False)
        import httplib2
        public = build('blogger', 'v3', http=httplib2.Http(), cache_discovery=False)
        return GoogleBlogServices(service, public_service=public)
    return BrowserBlogServices(connection_id)
