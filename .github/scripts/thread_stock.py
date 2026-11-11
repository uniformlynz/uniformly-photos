"""Every 15 minutes: read Thread Project's live file over SFTP, and Cloke's API, and publish STOCK ONLY (no prices)
to the `stock` branch as thread-project.json and cloke.json, for the Uniformly workshop and website.
Their prices (Gold, Silver) are Hayden's trade prices and are never written out.
11 Nov 2026: Cloke added. Each supplier is on its own: one failing leaves the other's last file in place."""
import base64, hashlib, io, json, os, re, stat, subprocess, sys, tempfile, time
import paramiko, openpyxl

# their address and the login name are kept in the repo's secrets, not here (11 Nov 2026, his call)
HOST, USER = os.environ.get('TP_HOST') or sys.exit('The TP_SFTP_HOST secret is not set yet'), os.environ.get('TP_USER') or sys.exit('The TP_SFTP_USER secret is not set yet')
FINGERPRINT = '/90Kc8DhIdbERJ1oTUdA5ypf+7YjNT2U/44hHPEvQyI'   # their ed25519 host key, SHA256
PASS = os.environ.get('TP_PASS') or sys.exit('The TP_SFTP_PASS secret is not set yet')

t = paramiko.Transport((HOST, 22))
t.start_client(timeout=30)
key = t.get_remote_server_key()
fp = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
if fp != FINGERPRINT:
    sys.exit('Their server key changed (%s %s), so not logging in' % (key.get_name(), fp))
t.auth_password(USER, PASS)
sftp = paramiko.SFTPClient.from_transport(t)
files = [f for f in sftp.listdir_attr('.') if stat.S_ISREG(f.st_mode) and re.search(r'\.(xlsx|csv)$', f.filename, re.I)]
if not files:
    sys.exit('No feed file on their server')
f = max(files, key=lambda x: x.st_mtime)
buf = io.BytesIO()
sftp.getfo(f.filename, buf)
sftp.close(); t.close()
buf.seek(0)

COLCODE = {'NAT': 'Natural', 'BLK': 'Black', 'WHT': 'White', 'NAT-BLK': 'Natural/Black', 'WHT-BLK': 'White/Black'}

def szkey(s):
    s = re.sub(r'\s+', '', str(s or '')).upper()
    m = re.match(r'^(X{2,})(S|L)$', s)
    return (str(len(m.group(1))) + 'X' + m.group(2)) if m else (s or 'OS')

rows = list(openpyxl.load_workbook(buf, read_only=True, data_only=True).worksheets[0].iter_rows(values_only=True))
H = [str(h or '').strip().lower() for h in rows[0]]
iS, iN, iO, iSt = H.index('sku'), H.index('product name'), H.index('option 1'), H.index('stock available')
items, n = {}, 0
for r in rows[1:]:
    sku = str(r[iS] or '').strip()
    if not sku:
        continue
    n += 1
    code, name = sku.split('-')[0], str(r[iN] or '').strip()
    bits = re.split(r'\s+-\s+', name)
    if len(bits) > 1:
        col = re.sub(r'\s*-\s*(kids|youth)\s*$', '', ' - '.join(bits[1:]), flags=re.I).strip()
    else:
        cc = '-'.join(sku.split('-')[1:])
        col = COLCODE.get(cc, cc or 'One colour')
    it = items.setdefault(code, {'name': bits[0].strip(), 'cols': {}})
    ck = re.sub(r'\s+', '', col.lower())
    C = it['cols'].setdefault(ck, {'label': col, 'sz': {}})
    try:
        st = int(round(float(r[iSt])))
    except Exception:
        st = 0
    C['sz'][szkey(r[iO])] = {'s': st, 'lab': str(r[iO] or '').strip() or 'one size'}

out = {'sup': 'Thread Project', 'file': f.filename, 'fileAt': int(f.st_mtime * 1000),
       'readAt': int(time.time() * 1000), 'rows': n, 'items': items}

# ---- Cloke: their API, stock only ----
def cloke_stock():
    import urllib.request, urllib.error
    u = os.environ.get('CLOKE_USER'); tries = [x for x in (os.environ.get('CLOKE_PASS'), os.environ.get('CLOKE_KEY')) if x]
    if not u or not tries: print('Cloke: no secrets yet, skipped'); return None
    auth = None
    for p in tries:   # the password, then the API key if Cloke turn the password down
        a = 'Basic ' + base64.b64encode(('%s:%s' % (u, p)).encode()).decode()
        try:
            with urllib.request.urlopen(urllib.request.Request('https://apical.beyondexpectations.co.nz/api/banbury/products?pageNum=1&pageSize=1', headers={'Authorization': a, 'Accept': 'application/json', 'User-Agent': 'Uniformly workshop'}), timeout=60) as r: r.read()
            auth = a; break
        except urllib.error.HTTPError as e: print('Cloke: login said %d' % e.code)
    if not auth: return None
    low = lambda o: {re.sub(r'[\s_\-]', '', k.lower()): v for k, v in o.items()} if isinstance(o, dict) else {}
    def get(o, *ns):
        L = low(o)
        for x in ns:
            v = L.get(re.sub(r'[\s_\-]', '', x.lower()))
            if v not in (None, ''): return v
        return None
    prods, page = [], 1
    while page < 200:
        req = urllib.request.Request('https://apical.beyondexpectations.co.nz/api/banbury/products?pageNum=%d&pageSize=250' % page, headers={'Authorization': auth, 'Accept': 'application/json', 'User-Agent': 'Uniformly workshop'})
        try:
            with urllib.request.urlopen(req, timeout=60) as r: body = json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            print('Cloke: page %d said %d' % (page, e.code)); return None
        lst = body if isinstance(body, list) else (get(body, 'products', 'data', 'items', 'results', 'records') or [])
        prods += lst
        if len(lst) < 250: break
        page += 1
    its, rows = {}, 0
    for P in prods:
        code = str(get(P, 'styleCode', 'style', 'code') or '').strip()
        if not code: continue
        it = its.setdefault(code, {'name': str(get(P, 'name', 'productName') or '').strip(), 'cols': {}})
        for O in (get(P, 'productOptions', 'options', 'variants') or []):
            rows += 1
            col = str(get(O, 'optionValue', 'colour', 'color', 'colourName') or 'One colour').strip()
            C = it['cols'].setdefault(re.sub(r'\s+', '', col.lower()), {'label': col, 'sz': {}})
            size = str(get(O, 'size', 'sizeName') or '').strip()
            try: st = int(round(float(get(O, 'stockAvailable', 'stock', 'available', 'qty') or 0)))
            except Exception: st = 0
            C['sz'][szkey(size) if size else 'OS'] = {'s': st, 'lab': size or 'one size'}
    # only the styles he carries (a folder in the library's cloke/), so the file the workshop downloads stays small
    try:
        rq = urllib.request.Request('https://api.github.com/repos/%s/contents/cloke' % os.environ['GITHUB_REPOSITORY'], headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(rq, timeout=30) as r: mine = set(x['name'].upper() for x in json.loads(r.read().decode()) if x.get('type') == 'dir')
        if mine: its = {k: v for k, v in its.items() if k.upper() in mine}
    except Exception: pass
    now = int(time.time() * 1000)
    print('Cloke: %d options, %d of his styles' % (rows, len(its)))
    top = max([e['s'] for it in its.values() for C in it['cols'].values() for e in C['sz'].values()] or [0])
    o = {'sup': 'Cloke', 'file': 'Cloke API', 'fileAt': now, 'readAt': now, 'rows': rows, 'items': its}
    if top == 99: o['capped'] = 99
    return o

try: ck = cloke_stock()
except Exception as e: print('Cloke: failed (%s)' % type(e).__name__); ck = None

repo = 'https://x-access-token:%s@github.com/%s.git' % (os.environ['GH_TOKEN'], os.environ['GITHUB_REPOSITORY'])
d = tempfile.mkdtemp()
# start from what's there, so a supplier that failed this time keeps its last file
subprocess.run(['git', 'clone', '-q', '--depth', '1', '-b', 'stock', repo, d], check=False)
subprocess.run(['rm', '-rf', os.path.join(d, '.git')], check=False)
with open(os.path.join(d, 'thread-project.json'), 'w') as fh:
    fh.write(json.dumps(out, separators=(',', ':'), ensure_ascii=False))
if ck:
    with open(os.path.join(d, 'cloke.json'), 'w') as fh:
        fh.write(json.dumps(ck, separators=(',', ':'), ensure_ascii=False))
with open(os.path.join(d, 'README.md'), 'w') as fh:
    fh.write('Thread Project and Cloke stock levels, refreshed every 15 minutes. Stock only, no prices.\n')
who = ['-c', 'user.name=uniformly-stock', '-c', 'user.email=uniformly@uniformly.co.nz']

def g(*a):
    subprocess.run(['git', '-C', d] + list(a), check=True)

g('init', '-q')
g('checkout', '-q', '-b', 'stock')
g(*who, 'add', '.')
g(*who, 'commit', '-qm', 'Thread Project stock %s' % time.strftime('%Y-%m-%d %H:%M UTC'))
g('push', '-q', '--force', repo, 'stock')   # one commit, replaced each time, so the repo doesn't grow
print('Published %d lines from %s' % (n, f.filename))
