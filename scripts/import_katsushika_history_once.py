#!/usr/bin/env python3
"""One-shot import for Katsushika rental history.
Safety rule: import only rows that have returned date.
"""

from __future__ import annotations
import re, html, json, requests
from urllib.parse import urljoin

BASE='https://www.lib.city.katsushika.lg.jp/'
API='http://localhost:18080/api/items'


def strip_tags(s:str)->str:
    s=re.sub(r'<br\s*/?>','\n',s,flags=re.I)
    s=re.sub(r'<[^>]+>','',s)
    return ' '.join(html.unescape(s).replace('\xa0',' ').split())

def jp_date(s:str)->str:
    m=re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日',s)
    if not m: return ''
    y,mn,d=map(int,m.groups())
    return f'{y:04d}-{mn:02d}-{d:02d}'

def key(i):
    p=(i.get('artist') or i.get('author') or '').strip().lower()
    t=' '.join((i.get('title') or '').split()).lower()
    return (t,p,i.get('borrowed_date'))

def map_type(fields):
    val=' '.join([fields.get('資料形態',''),fields.get('数量',''),fields.get('書名',''),fields.get('タイトル','')]).lower()
    if any(k in val for k in ['コンパクトディスク','cd','録音']): return 'cd'
    if any(k in val for k in ['dvd','ビデオディスク','映像']): return 'dvd'
    if any(k in val for k in ['図書','冊','文庫','単行本']) or fields.get('ＩＳＢＮ') or fields.get('ISBN'): return 'book'
    return 'other'


def main():
    import argparse, subprocess
    ap=argparse.ArgumentParser()
    ap.add_argument('--vault',default='OpenClaw')
    ap.add_argument('--item',default='Katsushika')
    args=ap.parse_args()

    p=subprocess.run(['op','item','get',args.item,'--vault',args.vault,'--format','json'],capture_output=True,text=True,check=True)
    obj=json.loads(p.stdout)
    u=w=''
    for f in obj.get('fields',[]):
        label=(f.get('label') or '').lower(); purpose=(f.get('purpose') or '').lower(); fid=(f.get('id') or '').lower(); v=f.get('value') or ''
        if not u and (purpose=='username' or fid=='username' or 'user' in label or 'id' in label): u=v
        if not w and (purpose=='password' or fid=='password' or 'pass' in label): w=v

    s=requests.Session()
    r=s.get(urljoin(BASE,'login'),timeout=20)
    action=re.search(r'<form[^>]*id="ida"[^>]*action="([^"]+)"',r.text,re.I).group(1)
    s.post(urljoin(r.url,action),data={'textUserId':u,'textPassword':w,'buttonLogin':'ログイン'},timeout=20)
    h=s.get(urljoin(BASE,'rentalhistorylist'),timeout=20)
    sections=re.findall(r'<section class="infotable">(.*?)</section>',h.text,re.S|re.I)

    existing=requests.get(API,timeout=20).json(); seen={key(i) for i in existing}
    inserted=skipped=no_return=0
    for sec in sections:
        m=re.search(r'<a[^>]+href="([^"]*rentalhistorydetail\?[^\"]+)"[^>]*>\s*<span>(.*?)</span>',sec,re.S|re.I)
        if not m: continue
        rel=html.unescape(m.group(1)); fallback=strip_tags(m.group(2))
        d=s.get(urljoin(BASE,rel),timeout=20)
        fields={}
        for fm in re.finditer(r'<th[^>]*scope="row"[^>]*>(.*?)</th>\s*<td>(.*?)</td>',d.text,re.S|re.I):
            fields[strip_tags(fm.group(1))]=strip_tags(fm.group(2))
        loan=jp_date(strip_tags(re.search(r'<th[^>]*>貸出日</th>\s*<td[^>]*>(.*?)</td>',d.text,re.S|re.I).group(1))) if re.search(r'<th[^>]*>貸出日</th>\s*<td[^>]*>(.*?)</td>',d.text,re.S|re.I) else ''
        ret=jp_date(strip_tags(re.search(r'<th[^>]*>返却日</th>\s*<td[^>]*>(.*?)</td>',d.text,re.S|re.I).group(1))) if re.search(r'<th[^>]*>返却日</th>\s*<td[^>]*>(.*?)</td>',d.text,re.S|re.I) else ''

        if not ret:
            no_return += 1
            continue

        t=map_type(fields)
        title=fields.get('タイトル') or fields.get('書名') or fallback
        person=fields.get('著作者') or fields.get('著者') or fields.get('著者名') or ''
        item={'type':t,'title':title,'library':'葛飾区立中央図書館','borrowed_date':loan,'due_date':ret,'returned_at':ret+'T00:00:00Z'}
        if t=='book':
            if person: item['author']=person
        else:
            if person: item['artist']=person

        k=key(item)
        if k in seen:
            skipped += 1
            continue
        rr=requests.post(API,json=item,timeout=20)
        if rr.ok:
            inserted += 1
            seen.add(k)

    print(json.dumps({'fetched':len(sections),'inserted':inserted,'skipped':skipped,'no_return_skipped':no_return},ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
