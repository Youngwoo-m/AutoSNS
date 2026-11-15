// Required public resources: prevents publishing an old folder without the course.
const fs=require('fs');
const path=require('path');
const root=path.resolve(process.argv[2]||__dirname);
const required=['index.html','privacy/index.html','terms/index.html','about/index.html','contact/index.html','study/index.html','ai-education/index.html','ai-education/game-demos/index.html','ai-education/guides/index.html',...['request-and-check','agent-tools','game-verification','hwpx-report'].map(x=>'ai-education/guides/'+x+'/index.html')];
const errors=required.filter(relative=>!fs.existsSync(path.join(root,relative))).map(relative=>'Missing: '+relative);
const supplement=path.join(root,'ai-education/visual-effects/index.html');
if(!fs.existsSync(supplement))errors.push('Missing visual-effects supplement.');
else {
 const html=fs.readFileSync(supplement,'utf8');
 if((html.match(/data-copy="/g)||[]).length!==8)errors.push('The supplement must contain 8 prompt copy buttons.');
 for(const m of html.matchAll(/(?:src|poster)="(assets\/[^"?]+)"/g))if(!fs.existsSync(path.resolve(path.dirname(supplement),m[1])))errors.push('Missing supplement asset: '+m[1]);
}
const course=path.join(root,'ai-education/index.html');
if(fs.existsSync(course)){
 const html=fs.readFileSync(course,'utf8');
 if((html.match(/data-copy="/g)||[]).length!==14)errors.push('The course must contain 14 prompt copy buttons.');
 const sources=[...html.matchAll(/(?:src|poster)="(videos28\/[^"?]+)"/g)].map(m=>m[1]);
 for(const relative of sources)if(!fs.existsSync(path.join(root,'ai-education',relative)))errors.push('Missing course asset: '+relative);
 const game=path.join(root,'ai-education/game-demos/index.html');
 if(fs.existsSync(game)){
  const content=fs.readFileSync(game,'utf8');
  if(/<script[^>]+src=["'][^"']*adsbygoogle|<ins[^>]+class=["']adsbygoogle/i.test(content))errors.push('The game demonstration page must not contain ad code.');
  for(const m of content.matchAll(/(?:src|poster)="(\.\.\/videos28\/[^"?]+)"/g))if(!fs.existsSync(path.resolve(path.dirname(game),m[1])))errors.push('Missing game asset: '+m[1]);
 }
}
if(errors.length){console.error('Hosting publication stopped: required content is incomplete.\n'+errors.join('\n'));process.exitCode=1;}
else console.log('Hosting content check passed: required pages, 14 prompts and referenced demonstration assets are present.');
