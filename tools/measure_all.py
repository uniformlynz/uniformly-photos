"""Re-measure every front and back photo and write fits.json. Run after adding photos:
    python3 tools/measure_all.py
Needs numpy, scipy and Pillow."""
import os, sys, glob, json, time, statistics as st, collections
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from measure import measure
from multiprocessing import Pool

def one(f):
    try:
        r = measure(f)
    except Exception:
        r = None
    return os.path.relpath(f, ROOT).replace(os.sep, '/'), r

if __name__ == '__main__':
    fs = sorted(glob.glob(os.path.join(ROOT, '*/*/*-front.webp'))) + sorted(glob.glob(os.path.join(ROOT, '*/*/*-back.webp')))
    F = {}
    with Pool() as p:
        for k, r in p.imap_unordered(one, fs, chunksize=20):
            F[k] = r
    # photos of one style in different colours come from the same shoot: one that reads more than 8% off the
    # others was misread (a white tee on white, a strap across the body), so it takes the middle one's numbers
    grp = collections.defaultdict(list)
    for k, r in F.items():
        if r:
            b, s, f = k.split('/')
            grp[(b, s, 'back' if f.endswith('-back.webp') else 'front')].append(k)
    out = {}
    for L in grp.values():
        ref = None
        if len(L) >= 3:
            m = st.median(F[k]['cw'] for k in L)
            ref = min(L, key=lambda k: abs(F[k]['cw'] - m))
        for k in L:
            r = F[k]
            if ref and abs(r['cw'] - F[ref]['cw']) / F[ref]['cw'] > 0.08:
                r = F[ref]
            out[k] = [r['cx'], r['cy'], r['cw'], r['top'], r['bot']]
    doc = {'v': time.strftime('%Y%m%d%H%M'),
           'note': 'Where the garment sits in each flat photo, as thousandths of the image: [centre x, chest line y, chest width, top y, bottom y]. The chest line is just under the armpits. Worked out by tools/measure.py; a print at its real size is chest width x (print mm / garment half chest mm).',
           'f': out}
    json.dump(doc, open(os.path.join(ROOT, 'fits.json'), 'w'), separators=(',', ':'))
    print(len(out), 'photos measured')
