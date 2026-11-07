"""Measure a flat garment photo: where the garment sits, its centre line, the top of the collar at the centre,
and the chest width in pixels (just under the armpits), so a print can be laid on at its true size.
Returns fractions of the image (0..1000) so it works at any display size."""
import sys, json
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

S = 450  # measured on a copy this wide (or tall)

def load(path):
    im = Image.open(path).convert('RGB')
    W, H = im.size
    k = S / max(W, H)
    sm = im.resize((max(1, round(W * k)), max(1, round(H * k))), Image.BILINEAR)
    return np.asarray(sm).astype(np.int16), W, H

def mask_of(a):
    h, w, _ = a.shape
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    d = np.abs(a - bg).sum(axis=2)
    m = d > 24
    m = ndi.binary_closing(m, structure=np.ones((5, 5)), iterations=2)
    m = ndi.binary_fill_holes(m)
    lab, n = ndi.label(m)
    if n == 0:
        return None
    sizes = ndi.sum(m, lab, range(1, n + 1))
    keep = 1 + int(np.argmax(sizes))
    return lab == keep

def measure(path):
    a, W, H = load(path)
    m = mask_of(a)
    if m is None or m.sum() < 500:
        return None
    h, w = m.shape
    ys = np.where(m.any(axis=1))[0]
    xs = np.where(m.any(axis=0))[0]
    top, bot = int(ys[0]), int(ys[-1])
    left, right = int(xs[0]), int(xs[-1])
    GH = bot - top + 1
    # centre line from the lower body, where nothing but the body is
    lo = m[top + int(GH * 0.55): top + int(GH * 0.9)]
    cols = np.where(lo.any(axis=0))[0]
    cx = int(round((cols[0] + cols[-1]) / 2)) if len(cols) else (left + right) // 2
    # the run of garment through the centre line, row by row
    wid = np.zeros(h, dtype=int); L = np.zeros(h, dtype=int); R = np.zeros(h, dtype=int)
    for y in range(top, bot + 1):
        row = m[y]
        if not row[cx]:
            continue
        l = cx
        while l > 0 and row[l - 1]:
            l -= 1
        r = cx
        while r < w - 1 and row[r + 1]:
            r += 1
        L[y], R[y], wid[y] = l, r, r - l + 1
    # top of the collar on the centre line (the first garment row there)
    cy = np.where(m[:, cx])[0]
    ctop = int(cy[0]) if len(cy) else top
    # armpit: below the shoulders, the first place the width falls well under the widest above it and stays down
    flag = 'arm'
    arm = None
    run = 0
    start = top + int(GH * 0.08)
    for y in range(start, top + int(GH * 0.6)):
        run = max(run, wid[y])
        if run and wid[y] and wid[y] < 0.8 * run:
            seg = wid[y: y + max(3, int(GH * 0.05))]
            if len(seg) and (seg > 0).all() and (seg < 0.85 * run).all():
                arm = y
                break
    if arm is not None:
        a0, a1 = arm + int(GH * 0.01), arm + int(GH * 0.06)
    else:
        # no sleeves to step in from (a singlet), or sleeves hanging against the body: take the upper body
        flag = 'est'
        a0, a1 = top + int(GH * 0.38), top + int(GH * 0.5)
    seg = wid[a0:a1 + 1]
    seg = seg[seg > 0]
    if not len(seg):
        return None
    cw = int(np.median(seg))
    cyv = (a0 + a1) // 2
    # a long sleeve against the body makes the chest look much wider than the body below it: check against the hem
    hem = wid[top + int(GH * 0.8): top + int(GH * 0.92)]
    hem = hem[hem > 0]
    if flag == 'est' and len(hem):
        hw = int(np.median(hem))
        if cw > 1.12 * hw:
            cw = int(hw * 1.02); flag = 'hem'
    # where the arms hang apart from the body (3 or more runs across a row), the run through the centre is the body
    # alone: if the chest came out much wider than that, the arms were in it. Looked for on a lightly closed mask, so a
    # narrow gap under the arm isn't closed over, and above the hem rib, which pulls in narrower than the chest
    if flag != 'arm':
        raw = ndi.binary_fill_holes(ndi.binary_closing(np.abs(a - np.median(np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]), axis=0)).sum(axis=2) > 24, structure=np.ones((3, 3))))
        bw = []
        for y in range(top + int(GH * 0.42), top + int(GH * 0.82)):
            row = raw[y]
            if not row[cx]:
                continue
            d = np.diff(row.astype(np.int8))
            st = list(np.where(d == 1)[0] + 1); en = list(np.where(d == -1)[0])
            if row[0]: st = [0] + st
            if row[-1]: en = en + [w - 1]
            if len(st) >= 3:
                for s0, e0 in zip(st, en):
                    if s0 <= cx <= e0:
                        bw.append(e0 - s0 + 1)
        if len(bw) >= max(3, int(GH * 0.03)):
            b = int(np.median(bw))
            if cw > 1.06 * b:
                cw = b; flag = 'gap'
    # still no body edge found (sleeves flush against it): the hem band, just above the bottom, is close to the chest
    if flag in ('est', 'hem'):
        rib = wid[top + int(GH * 0.88): top + int(GH * 0.96)]
        rib = rib[rib > 0]
        if len(rib):
            rb = int(np.median(rib) * 1.05)
            if cw > 1.1 * rb:
                cw = rb; flag = 'rib'
    # the shoulder line beside the neck: the top of the garment 30% of the chest out from the centre each side
    # (clear of a hood or a collar). The collar and every print placement are measured down from here
    shs = []
    for xs_ in (int(cx - 0.30 * cw), int(cx + 0.30 * cw)):
        if 0 <= xs_ < w:
            col = np.where(m[:, xs_])[0]
            if len(col): shs.append(int(col[0]))
    sh = int(np.median(shs)) if shs else top
    f = lambda v, n: int(round(v / n * 1000))
    return {'cx': f(cx, w), 'top': f(top, h), 'bot': f(bot, h), 'ctop': f(ctop, h), 'cy': f(cyv, h),
            'cl': f(cx - cw / 2, w), 'cr': f(cx + cw / 2, w), 'cw': f(cw, w), 'l': f(left, w), 'r': f(right, w), 'sh': f(sh, h), 'k': flag}

if __name__ == '__main__':
    for p in sys.argv[1:]:
        print(p, json.dumps(measure(p)))
