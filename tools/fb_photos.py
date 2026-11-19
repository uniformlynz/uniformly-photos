"""Fashion Biz photos (16 Nov 2026). Downloads the photos in a list straight from Fashion Biz's image server
(cdn.fashionbizapps.nz), shrinks them to webp like the other brands and adds them to photos.json.
  python3 tools/fb_photos.py sample tools/fb_sample.json   -> fb-sample/<code>/<file>.jpg thumbnails, to look at
  python3 tools/fb_photos.py full tools/fb_list.json       -> fashion-biz/<code>/<colour>-front|back|model.webp + photos.json
A colour Fashion Biz no longer lists is taken out again on the next full run (their media terms: withdrawn images go)."""
import sys, os, json, io, time, shutil
from concurrent.futures import ThreadPoolExecutor
import requests
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
S = requests.Session(); S.headers['User-Agent'] = 'Mozilla/5.0 (photo sync)'   # nothing about him or the business in it (his rule)
def get(url):
    for i in range(3):
        try:
            r = S.get(url, timeout=40)
            if r.status_code == 200 and r.content: return r.content, 200
            if r.status_code in (403, 404): return None, r.status_code
        except Exception as e:
            err = str(e)
        time.sleep(2 + i * 3)
    return None, 'fail'
def to_rgb(im):
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA'); bg = Image.new('RGB', im.size, (255, 255, 255)); bg.paste(im, mask=im.split()[-1]); return bg
    return im.convert('RGB')
def sample(lst):
    out = os.path.join(ROOT, 'fb-sample'); rep = []
    def one(x):
        b, st = get(x['url'])
        if b is None: rep.append([x['code'], x['name'], st]); return
        im = to_rgb(Image.open(io.BytesIO(b))); w, h = im.size; im.thumbnail((360, 360))
        d = os.path.join(out, x['code']); os.makedirs(d, exist_ok=True)
        im.save(os.path.join(d, os.path.splitext(x['name'])[0] + '.jpg'), quality=80)
        rep.append([x['code'], x['name'], 200, w, h])
    with ThreadPoolExecutor(8) as ex: list(ex.map(one, lst))
    json.dump(sorted(rep), open(os.path.join(out, 'report.json'), 'w'), indent=0)
def full(lst):
    base = os.path.join(ROOT, 'fashion-biz'); P = json.load(open(os.path.join(ROOT, 'photos.json')))
    keep = set(); rep = {'ok': 0, 'missing': []}; got = {}
    def one(x):
        d = os.path.join(base, x['code'].lower()); os.makedirs(d, exist_ok=True); paths = []
        for role in ('front', 'back', 'model'):
            u = x.get(role)
            if not u: continue
            rel = 'fashion-biz/%s/%s-%s.webp' % (x['code'].lower(), x['slug'], role); f = os.path.join(ROOT, rel)
            if not os.path.exists(f):
                b, st = get(u)
                if b is None: rep['missing'].append([x['code'], x['colour'], role, st]); continue
                im = to_rgb(Image.open(io.BytesIO(b)))
                im.thumbnail((733, 1100) if role == 'model' else (900, 900), Image.LANCZOS)
                im.save(f, 'WEBP', quality=82, method=6)
            keep.add(rel); paths.append(rel)
        if paths: got[(x['brand'], x['code'], x['colour'])] = paths; rep['ok'] += 1
    with ThreadPoolExecutor(12) as ex: list(ex.map(one, lst))
    # anything Fashion Biz no longer lists comes out
    for dp, dn, fn in os.walk(base):
        for n in fn:
            rel = os.path.relpath(os.path.join(dp, n), ROOT).replace(os.sep, '/')
            if rel not in keep: os.remove(os.path.join(dp, n))
    for br in set(x['brand'] for x in lst): P['brands'][br] = {}
    for (br, code, col), paths in sorted(got.items()):
        P['brands'].setdefault(br, {}).setdefault(code.upper(), {})[col] = paths
    P['v'] = time.strftime('%Y%m%d%H%M')
    json.dump(P, open(os.path.join(ROOT, 'photos.json'), 'w'), separators=(',', ':'))
    json.dump(rep, open(os.path.join(HERE, 'fb_report.json'), 'w'), indent=0)
    print('colours with photos', rep['ok'], 'missing', len(rep['missing']))
if __name__ == '__main__':
    mode, lf = sys.argv[1], sys.argv[2]; lst = json.load(open(lf))
    sample(lst) if mode == 'sample' else full(lst)
