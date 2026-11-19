"""Weekly photos from the suppliers' own feeds (20 Nov 2026, his call): Thread Project (their stock file has a photo link
for every colour) and Cloke (their API has one per colour, once their login works again).
Only NEW colours are added, as a front photo, to the styles in the library (and any new Thread Project style). Photos
already there (the full front, back and model sets from their photo packs) are never touched or re-downloaded.
A colour the feed no longer has is listed in tools/feed_photos_report.json, not deleted, so nothing good goes by mistake.
  python3 tools/feed_photos.py"""
import base64, hashlib, io, json, os, re, stat, time, urllib.request, urllib.error
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
UA = 'Mozilla/5.0 (photo sync)'   # nothing about him or the business in it (his rule)
def norm(c): return re.sub(r'[^a-z0-9]', '', str(c or '').lower())
def slug(c): return re.sub(r'[^a-z0-9]+', '-', str(c or '').lower()).strip('-')
def fetch(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=40) as r: return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 404): return None
        except Exception: pass
        time.sleep(3 + i * 3)
    return None
def rgb(im):
    if im.mode in ('RGBA', 'LA', 'P'):
        im = im.convert('RGBA'); bg = Image.new('RGB', im.size, (255, 255, 255)); bg.paste(im, mask=im.split()[-1]); return bg
    return im.convert('RGB')

def tp_colours():
    """{code: {colour: image url}} off Thread Project's stock file (the same SFTP file the stock job reads)"""
    import paramiko, openpyxl
    host, user, pw = os.environ.get('TP_HOST'), os.environ.get('TP_USER'), os.environ.get('TP_PASS')
    if not (host and user and pw): print('Thread Project: no SFTP secrets, skipped'); return None
    t = paramiko.Transport((host, 22)); t.start_client(timeout=30)
    fp = base64.b64encode(hashlib.sha256(t.get_remote_server_key().asbytes()).digest()).decode().rstrip('=')
    if fp != '/90Kc8DhIdbERJ1oTUdA5ypf+7YjNT2U/44hHPEvQyI': t.close(); print('Thread Project: their server key changed, not logging in'); return None
    t.auth_password(user, pw); sftp = paramiko.SFTPClient.from_transport(t)
    files = [f for f in sftp.listdir_attr('.') if stat.S_ISREG(f.st_mode) and re.search(r'\.(xlsx|csv)$', f.filename, re.I)]
    if not files: t.close(); print('Thread Project: no file'); return None
    f = max(files, key=lambda x: x.st_mtime); buf = io.BytesIO(); sftp.getfo(f.filename, buf); sftp.close(); t.close(); buf.seek(0)
    rows = list(openpyxl.load_workbook(buf, read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True))
    H = [str(h or '').strip().lower() for h in rows[0]]
    if 'sku' not in H or 'imageurl' not in H: print('Thread Project: the file has changed shape'); return None
    iS, iN, iI = H.index('sku'), H.index('product name'), H.index('imageurl')
    CC = {'NAT': 'Natural', 'BLK': 'Black', 'WHT': 'White', 'NAT-BLK': 'Natural/Black', 'WHT-BLK': 'White/Black'}
    out = {}
    for r in rows[1:]:
        sku = str(r[iS] or '').strip(); u = str(r[iI] or '').strip()
        if not sku: continue
        code, name = sku.split('-')[0], str(r[iN] or '').strip(); bits = re.split(r'\s+-\s+', name)
        col = re.sub(r'\s*-\s*(kids|youth)\s*$', '', ' - '.join(bits[1:]), flags=re.I).strip() if len(bits) > 1 else CC.get('-'.join(sku.split('-')[1:]), '')
        if col and u.startswith('http'): out.setdefault(code, {}).setdefault(col, u)
        elif col: out.setdefault(code, {}).setdefault(col, '')
    print('Thread Project: %d styles in their file' % len(out)); return out

def cloke_colours():
    """{code: {colour: image url}} off Cloke's API (Basic auth). Their logins are refused at the moment: then skipped"""
    u = os.environ.get('CLOKE_USER'); tries = [x for x in (os.environ.get('CLOKE_PASS'), os.environ.get('CLOKE_KEY')) if x]
    if not u or not tries: print('Cloke: no secrets, skipped'); return None
    B = 'https://apical.beyondexpectations.co.nz/api/banbury/products'
    auth = None
    for p in tries:
        a = 'Basic ' + base64.b64encode(('%s:%s' % (u, p)).encode()).decode()
        try:
            with urllib.request.urlopen(urllib.request.Request(B + '?pageNum=1&pageSize=1', headers={'Authorization': a, 'Accept': 'application/json', 'User-Agent': 'stock-sync'}), timeout=60) as r: r.read()
            auth = a; break
        except urllib.error.HTTPError as e: print('Cloke: login said %d' % e.code)
    if not auth: print('Cloke: not logged in, skipped this week'); return None
    def g(o, *ns):
        if not isinstance(o, dict): return None
        low = {re.sub(r'[\s_\-]', '', k.lower()): v for k, v in o.items()}
        for n in ns:
            v = low.get(re.sub(r'[\s_\-]', '', n.lower()))
            if v not in (None, ''): return v
        return None
    out, page = {}, 1
    while page < 200:
        with urllib.request.urlopen(urllib.request.Request('%s?pageNum=%d&pageSize=250' % (B, page), headers={'Authorization': auth, 'Accept': 'application/json', 'User-Agent': 'stock-sync'}), timeout=60) as r: body = json.loads(r.read().decode())
        lst = body if isinstance(body, list) else (g(body, 'products', 'data', 'items', 'results', 'records') or [])
        for P in lst:
            code = str(g(P, 'styleCode', 'style', 'code') or '').strip()
            if not code: continue
            for O in (g(P, 'productOptions', 'options', 'variants') or []):
                col = str(g(O, 'optionValue', 'colour', 'color', 'colourName') or '').strip()
                img = g(O, 'image', 'imageUrl', 'colourImage', 'images')
                if isinstance(img, list): img = img[0] if img else ''
                if isinstance(img, dict): img = g(img, 'url', 'src', 'link') or ''
                if col: out.setdefault(code, {}).setdefault(col, str(img or ''))
        if len(lst) < 250: break
        page += 1; time.sleep(1)   # gently
    print('Cloke: %d styles in their API' % len(out)); return out

def add(P, brand, folder, feed, new_styles):
    have = P['brands'].setdefault(brand, {}); added, gone = [], []
    for code, cols in sorted(feed.items()):
        cu = code.upper()
        if cu not in have and not new_styles: continue
        cur = have.setdefault(cu, {}); hn = {norm(c) for c in cur}; fn = {norm(c) for c in cols}
        # a colour the library has under a fuller name the feed doesn't use (library "White/Black", feed "White") is
        # the same colour: not added again
        spare = [h for h in hn if h not in fn]
        for col, url in sorted(cols.items()):
            if norm(col) in hn or not url: continue
            if any(h.startswith(norm(col)) or norm(col).startswith(h) for h in spare): continue
            b = fetch(url)
            if not b: continue
            try: im = rgb(Image.open(io.BytesIO(b)))
            except Exception: continue
            im.thumbnail((900, 900), Image.LANCZOS)
            rel = '%s/%s/%s-front.webp' % (folder, code.lower(), slug(col)); os.makedirs(os.path.dirname(os.path.join(ROOT, rel)), exist_ok=True)
            im.save(os.path.join(ROOT, rel), 'WEBP', quality=82, method=6)
            cur[col] = [rel]; added.append([code, col]); time.sleep(0.5)
        gone += [[code, c] for c in cur if norm(c) not in fn]
        if not cur: del have[cu]
    return added, gone

if __name__ == '__main__':
    P = json.load(open(os.path.join(ROOT, 'photos.json'))); rep = {}
    for brand, folder, getter, new_styles in (('Thread Project', 'thread-project', tp_colours, True), ('Cloke', 'cloke', cloke_colours, False)):
        try: feed = getter()
        except Exception as e: print('%s: failed (%s)' % (brand, type(e).__name__)); feed = None
        if not feed: continue
        a, g = add(P, brand, folder, feed, new_styles)
        rep[brand] = {'added': a, 'no_longer_in_their_feed': g}
        print('%s: %d new colours added, %d in the library they no longer list' % (brand, len(a), len(g)))
    if any(v['added'] for v in rep.values()):
        P['v'] = time.strftime('%Y%m%d%H%M'); json.dump(P, open(os.path.join(ROOT, 'photos.json'), 'w'), separators=(',', ':'))
    json.dump(rep, open(os.path.join(HERE, 'feed_photos_report.json'), 'w'), indent=0)
