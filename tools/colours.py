"""Measure the garment colour in every colour's main photo and write colours.json. Run after adding photos:
    python3 tools/colours.py
Same reading the workshop does on screen: the photo scaled to 80px wide, the middle of the chest
(38% to 62% across, 34% to 52% down), the median of the solid pixels. Needs Pillow."""
import os, json, time
from multiprocessing import Pool
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)

def one(rel):
    try:
        im = Image.open(os.path.join(ROOT, rel)).convert('RGBA')
        W = 80; H = max(1, round(80 * im.height / max(1, im.width)))
        im = im.resize((W, H), Image.BILINEAR)
        x0, y0 = round(W * 0.38), round(H * 0.34); w, h = max(1, round(W * 0.24)), max(1, round(H * 0.18))
        R, G, B = [], [], []
        for y in range(y0, min(H, y0 + h)):
            for x in range(x0, min(W, x0 + w)):
                r, g, b, a = im.getpixel((x, y))
                if a < 200: continue
                R.append(r); G.append(g); B.append(b)
        if not R: return rel, None
        med = lambda v: sorted(v)[len(v) >> 1]
        return rel, '#%02x%02x%02x' % (med(R), med(G), med(B))
    except Exception:
        return rel, None

if __name__ == '__main__':
    M = json.load(open(os.path.join(ROOT, 'photos.json')))
    base = M.get('base', '')
    rels = set()
    for b, items in M['brands'].items():
        for code, cols in items.items():
            for c, urls in cols.items():
                u = [x for x in urls if x]
                if not u: continue
                f = [x for x in u if '-front.' in x] or [x for x in u if '-model.' not in x and '-back.' not in x] or u
                rel = f[0].replace(base, '') if f[0].startswith('http') else f[0]
                if os.path.exists(os.path.join(ROOT, rel)): rels.add(rel)
    out = {}
    with Pool() as p:
        for rel, hx in p.imap_unordered(one, sorted(rels), chunksize=40):
            if hx: out[rel] = hx
    json.dump({'v': time.strftime('%Y%m%d%H%M'), 'note': 'The garment colour read off each colour\'s main photo (the middle of the chest), keyed by the photo\'s path in photos.json.', 'hex': out},
              open(os.path.join(ROOT, 'colours.json'), 'w'), separators=(',', ':'))
    print('colours', len(out), 'of', len(rels))
