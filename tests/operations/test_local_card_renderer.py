import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from types import SimpleNamespace
from common.operations.local_card_renderer import LocalCardRenderer,local_card_template_hash,validate_image_spec
from common.operations.models import ContractError

SPEC=dict(template='steps',title='안전 절차',body=['첫째','둘째'],footer='검토 전')
PNG=b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',1080,1350)+b'\x08\x02\x00\x00\x00'+b'\x00'*4

class LocalCardRendererTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.code=Path(self.tmp.name)/'code';self.root=self.code/'common/remotion-shorts'
        for source in ('src/local-card/index.ts','src/local-card/Root.tsx','src/local-card/LocalCard.tsx'):
            path=self.root/source;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source)
        package={'dependencies':{'remotion':'4.0.535','@remotion/cli':'4.0.535'}}
        (self.root/'package.json').write_text(json.dumps(package));(self.root/'package-lock.json').write_text('{}')
        self.font=self.root/'public/Pretendard-Bold.otf';self.font.parent.mkdir();self.font.write_bytes(b'OTTOtest')
        modules=self.root/'node_modules';binary=modules/'@remotion/cli/remotion-cli.js';binary.parent.mkdir(parents=True);binary.write_text('cli')
        (modules/'.bin').mkdir();(modules/'.bin/remotion').symlink_to('../@remotion/cli/remotion-cli.js')
        for name in ('remotion','@remotion/cli'):
            path=modules/name/'package.json';path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps({'version':'4.0.535'}))
        self.output=Path(self.tmp.name)/'artifact';self.calls=[]
        self.browser=Path(self.tmp.name)/'browser';self.browser.write_text('browser');self.browser.chmod(0o755)
        lock=self.code/'common/shared/axlock.py';lock.parent.mkdir(parents=True);lock.write_text('lock')
    def make(self,execute=None):
        return LocalCardRenderer(self.code,expected_template_hash=local_card_template_hash(self.root),expected_font_hash=hashlib.sha256(self.font.read_bytes()).hexdigest(),execute=execute or self.execute,browser_executable=self.browser)
    def execute(self,args,**kwargs):
        self.calls.append((args,kwargs));native=args[args.index('--')+1:];Path(native[6]).write_bytes(PNG);return SimpleNamespace(returncode=0)
    def test_constructor_is_inert_and_explicit_call_has_fixed_args_and_minimal_env(self):
        renderer=self.make();self.assertFalse(self.output.exists());self.assertEqual(self.calls,[])
        self.assertTrue(renderer.verify()['verified']);self.assertFalse(self.output.exists())
        result=renderer(SPEC,owner_account_id='personal',artifact_root=self.output)
        self.assertEqual((result['width'],result['height']),(1080,1350));self.assertEqual(result['size'],len(PNG))
        args,kwargs=self.calls[0];self.assertEqual(args[1:9],[str(self.code/'common/shared/axlock.py'),'run','--job','managed-local-card','--res','renderer:local-card','--','npx']);native=args[args.index('--')+1:];self.assertIn('--browser-executable='+str(self.browser),native);self.assertEqual(native[:6],['npx','--no-install','remotion','still','src/local-card/index.ts','LocalCard'])
        self.assertFalse(kwargs['shell']);self.assertEqual(kwargs['cwd'],self.root);self.assertEqual(set(kwargs['env']),{'HOME','USER','LOGNAME','PATH','LANG'})
        props=json.loads((self.output/'props.json').read_text());self.assertEqual(props,dict(spec=SPEC,owner_account_id='personal'))
    def test_exact_spec_rejects_paths_unknown_keys_and_invalid_owner_before_native(self):
        for spec in ({**SPEC,'path':'/tmp/a'},{**SPEC,'body':[]},{**SPEC,'title':'x'*81},{**SPEC,'body':['x'*121]},{**SPEC,'template':'other'}):
            with self.assertRaises(ContractError):self.make()(spec,owner_account_id='dept',artifact_root=self.output)
        with self.assertRaises(ContractError):self.make()(SPEC,owner_account_id='other',artifact_root=self.output)
        self.assertEqual(self.calls,[])
    def test_changed_source_font_or_cli_link_is_refused(self):
        renderer=self.make();(self.root/'src/local-card/Root.tsx').write_text('changed')
        self.assertFalse(renderer.verify()['verified'])
        with self.assertRaises(ContractError):renderer(SPEC,owner_account_id='dept',artifact_root=self.output)
        self.assertEqual(self.calls,[])
        renderer=self.make();self.font.write_bytes(b'OTTOchanged');self.assertFalse(renderer.verify()['verified'])
    def test_unsafe_cli_and_artifact_links_are_refused(self):
        cli=self.root/'node_modules/.bin/remotion';cli.unlink();cli.symlink_to('/usr/bin/true')
        self.assertFalse(self.make().verify()['verified'])
        self.output.symlink_to(self.code,target_is_directory=True)
        with self.assertRaises(ContractError):self.make()(SPEC,owner_account_id='personal',artifact_root=self.output)
        self.assertEqual(self.calls,[])
    def test_invalid_output_or_native_error_never_claims_image(self):
        def bad(args,**kwargs):Path(args[args.index('--')+7]).write_bytes(PNG[:16]+struct.pack('>II',1,1)+PNG[24:]);return SimpleNamespace(returncode=0)
        with self.assertRaises(ContractError):self.make(bad)(SPEC,owner_account_id='personal',artifact_root=self.output)
    def test_text_is_copied_as_data_and_never_added_to_command(self):
        spec={**SPEC,'title':'$(secret) <script>','body':['한글 & <tag>']};original=json.dumps(spec,ensure_ascii=False)
        self.make()(spec,owner_account_id='dept',artifact_root=self.output)
        self.assertEqual(json.dumps(spec,ensure_ascii=False),original)
        self.assertNotIn(spec['title'],' '.join(self.calls[0][0]))

    def test_missing_browser_or_unsafe_browser_refuses_before_props_and_execute(self):
        renderer=LocalCardRenderer(self.code,expected_template_hash=local_card_template_hash(self.root),expected_font_hash=hashlib.sha256(self.font.read_bytes()).hexdigest(),execute=self.execute)
        self.assertTrue(renderer.verify()['verified'])
        with self.assertRaises(ContractError) as raised:renderer(SPEC,owner_account_id='personal',artifact_root=self.output)
        self.assertEqual(str(raised.exception),'image_browser_required');self.assertFalse(self.output.exists());self.assertEqual(self.calls,[])
        self.browser.chmod(0o644)
        with self.assertRaises(ContractError):self.make()(SPEC,owner_account_id='personal',artifact_root=self.output)
        self.browser.unlink();self.browser.symlink_to('/usr/bin/true')
        with self.assertRaises(ContractError):self.make()(SPEC,owner_account_id='personal',artifact_root=self.output)
        self.assertFalse(self.output.exists());self.assertEqual(self.calls,[])

    def test_stop_marker_blocks_before_props_or_native_even_when_dangling_link(self):
        stop=self.code/'ax-console/data/STOP.json';stop.parent.mkdir(parents=True);stop.symlink_to(self.code/'missing-stop')
        with self.assertRaises(ContractError) as raised:self.make()(SPEC,owner_account_id='personal',artifact_root=self.output)
        self.assertEqual(str(raised.exception),'image_stopped');self.assertFalse(self.output.exists());self.assertEqual(self.calls,[])
