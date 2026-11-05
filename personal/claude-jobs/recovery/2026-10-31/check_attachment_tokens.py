from pathlib import Path
import sys
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS')
sys.path.insert(0,str(ROOT/'dept/naver-blog-auto'))
import tistory_post as tp
# Observed editor shape: two attachment tokens share a paragraph with a caption.
a='[##_Image|kage@first/img.png|CDM|1.3|{"originWidth":1200}_##]'
b='[##_Image|kage@second/img.png|CDM|1.3|{"originWidth":1200}_##]'
f='[##_File|kage@pdf/file.pdf|filename.pdf|size="1000"_길이_##]'
before='<p>'+a+'<small>AI 생성 배너</small></p><p data-ax-attach="diagram.png"></p>'
after='<p>'+b+a+'<small>AI 생성 배너</small></p><p data-ax-attach="diagram.png"></p>'
old=set(tp.TOKEN.findall(before));new=[t for t in tp.TOKEN.findall(after) if t not in old]
assert new==[b], 'new attachment must be recognized independently of adjacent tokens/caption'
moved=after.replace(new[0],'',1);moved=tp.MARKER.sub(lambda _:new[0],moved,count=1)
assert moved.count(a)==1 and moved.count(b)==1 and 'AI 생성 배너' in moved
assert moved.index(a)<moved.index(b)
assert set(tp.TOKEN.findall('<p>'+a+'</p><p>'+f+'</p>'))=={a,f}
print('PASS: adjacent images, caption preservation, placement and PDF tokens')
