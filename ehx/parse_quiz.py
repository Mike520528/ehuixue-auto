# -*- coding: utf-8 -*-
import re,sys,glob,os
import html as ihtml
def clean(s):
    s=re.sub(r'<[^>]+>','',s); s=ihtml.unescape(s)
    return re.sub(r'\s+',' ',s).strip()
def parse(h):
    out=[]
    for m in re.finditer(r'<table[^>]*class="layui-table tableone"[^>]*id="exam(\d+)"[^>]*>(.*?)</table>',h,re.S):
        qid=m.group(1); blk=m.group(2)
        hid=re.search(r'name="answer\[%s\]"\s*attr1="(\d+)"'%qid,blk)
        qtype=hid.group(1) if hid else '?'
        stem=''; opts=[]
        for r in re.findall(r'<tr>(.*?)</tr>',blk,re.S):
            tds=re.findall(r'<td[^>]*>(.*?)</td>',r,re.S)
            if not tds: continue
            if stem=='' and 'input' not in r and len(tds)>=2:
                stem=clean(tds[-1]); continue
            if qtype=='3':
                for mm in re.finditer(r'<input type="radio"[^>]*name="pd_%s"[^>]*value="(\d)"[^>]*title="([^"]*)"'%qid,r):
                    opts.append((mm.group(1),mm.group(2)))
            else:
                for mm in re.finditer(r'<input type="(?:radio|checkbox)"[^>]*name="(?:sq|mq)_%s"[^>]*value="([^"]*)"'%qid,r):
                    tds2=[clean(t) for t in tds if 'input' not in t]
                    opts.append((mm.group(1),tds2[-1] if tds2 else ''))
        if stem and opts:
            seen=set(); u=[]
            for v,t in opts:
                if v not in seen: seen.add(v); u.append((v,t))
            out.append({'qid':qid,'qtype':qtype,'stem':stem,'opts':u})
    return out
if __name__=='__main__':
    for f in sys.argv[1:] or sorted(glob.glob(r'C:\tmp\quiz_*.html')):
        qs=parse(open(f,encoding='utf-8').read())
        print('==',os.path.basename(f),len(qs))
        for q in qs: print('  Q%s t%s %s'%(q['qid'],q['qtype'],q['stem'][:60]))
