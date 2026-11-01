import {mkdtempSync,cpSync,existsSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
const base=fileURLToPath(new URL('../../',import.meta.url));
const oauth=join(base,'.superpowers/sdd/2026-11-01-sns-oauth-connections/web-artifacts/manifest.json');
const toolkit=join(base,'.superpowers/sdd/2026-10-31-local-sns-toolkit/web-artifacts/manifest.json');
const phase6=join(base,'.superpowers/sdd/2026-10-30-web-phase6a/web-artifacts/manifest.json');
const temporary=mkdtempSync(join(tmpdir(),'staged-web-'));
const root=join(temporary,'web');cpSync(join(base,'ax-console/app/web'),root,{recursive:true});
const sha=p=>createHash('sha256').update(readFileSync(p)).digest('hex');
const plan=existsSync(oauth)?oauth:existsSync(toolkit)?toolkit:phase6;
if(existsSync(plan)){
 const manifest=JSON.parse(readFileSync(plan));
 for(const e of manifest.entries){
  if(sha(join(base,e.artifact))!==e.artifact_sha256)throw new Error(`artifact SHA mismatch: ${e.target}`);
  if(![e.original_sha256,e.artifact_sha256].includes(sha(join(root,e.target.split('/').at(-1)))))throw new Error(`actual baseline SHA mismatch: ${e.target}`);
 }
 for(const e of manifest.new_modules||[]){if(sha(join(base,e.source))!==(e.sha256||e.artifact_sha256))throw new Error(`module SHA mismatch: ${e.target}`);}
 for(const e of manifest.entries)cpSync(join(base,e.artifact),join(root,e.target.split('/').at(-1)));
 for(const e of manifest.new_modules||[]){const source=join(base,e.source);if(sha(source)!==(e.sha256||e.artifact_sha256))throw new Error(`module SHA mismatch: ${e.target}`);cpSync(source,join(root,e.target.split('/').at(-1)));}
}
// 별도 검토한 기술사 표시 artifact도 같은 임시 webroot에만 적용한다.
const engineer=join(base,'.superpowers/sdd/2026-10-30-web-phase6a/engineer-label-artifact.js');
if(plan!==oauth&&existsSync(engineer))cpSync(engineer,join(root,'engineer_panel.js'));
process.on('exit',()=>rmSync(temporary,{recursive:true,force:true}));
export const stagedWebRoot=root;
export const webSource=name=>readFileSync(join(root,name),'utf8');
export const loadWebModule=name=>import(pathToFileURL(join(root,name)));
