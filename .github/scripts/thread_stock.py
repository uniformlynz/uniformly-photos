"""Every 15 minutes: read Thread Project's live file over SFTP and publish STOCK ONLY (no prices)
to the `stock` branch as thread-project.json, for the Uniformly workshop and website.
The Gold prices in that file are Hayden's trade prices and are never written out."""
import base64, hashlib, io, json, os, re, stat, subprocess, sys, tempfile, time
import paramiko, openpyxl

HOST, USER = '[their SFTP address, now a secret]', '[their SFTP login, now a secret]'
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
d = tempfile.mkdtemp()
with open(os.path.join(d, 'thread-project.json'), 'w') as fh:
    fh.write(json.dumps(out, separators=(',', ':'), ensure_ascii=False))
with open(os.path.join(d, 'README.md'), 'w') as fh:
    fh.write('Thread Project stock levels, refreshed every 15 minutes. Stock only, no prices.\n')
repo = 'https://x-access-token:%s@github.com/%s.git' % (os.environ['GH_TOKEN'], os.environ['GITHUB_REPOSITORY'])
who = ['-c', 'user.name=uniformly-stock', '-c', 'user.email=uniformly@uniformly.co.nz']

def g(*a):
    subprocess.run(['git', '-C', d] + list(a), check=True)

g('init', '-q')
g('checkout', '-q', '-b', 'stock')
g(*who, 'add', '.')
g(*who, 'commit', '-qm', 'Thread Project stock %s' % time.strftime('%Y-%m-%d %H:%M UTC'))
g('push', '-q', '--force', repo, 'stock')   # one commit, replaced each time, so the repo doesn't grow
print('Published %d lines from %s' % (n, f.filename))
