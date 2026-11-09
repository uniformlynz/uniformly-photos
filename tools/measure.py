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

def bg_model(a):
    """The backdrop as a shade across the photo (10 Nov 2026): some suppliers shoot on grey that darkens towards the
    edges. Fits a plane per channel to the border pixels, dropping the ones that are garment."""
    h, w, _ = a.shape
    yy, xx = np.mgrid[0:h, 0:w]
    b = np.zeros((h, w), bool); t = 3
    b[:t] = b[-t:] = True; b[:, :t] = b[:, -t:] = True
    X, Y, P = xx[b].astype(float), yy[b].astype(float), a[b].astype(float)
    A = np.stack([np.ones_like(X), X / w, Y / h], axis=1)
    lum = P.sum(axis=1); keep = lum >= np.median(lum)
    coef = None
    for _ in range(4):
        if keep.sum() < 20:
            break
        coef, *_ = np.linalg.lstsq(A[keep], P[keep], rcond=None)
        res = np.abs(A @ coef - P).sum(axis=1)
        keep = res < max(18.0, np.percentile(res[keep], 80) * 1.5)
    if coef is None:
        return np.median(P, axis=0)[None, None, :]
    return np.stack([np.ones((h, w)), xx / w, yy / h], axis=2) @ coef

def flat_bg(a):
    return np.median(np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]), axis=0)

def mask_of(a, shaded=False):
    h, w, _ = a.shape
    if not shaded:
        d = np.abs(a - flat_bg(a)).sum(axis=2)
        m = d > 24
    else:
        # a shaded backdrop: modelled as a shade, with a cut-off that scales with how far the garment sits from it,
        # so a black tee isn't joined to the shadow around it
        bg = bg_model(a)
        d = np.abs(a - bg).sum(axis=2)
        gc = np.median(a[int(h * 0.35):int(h * 0.65), int(w * 0.4):int(w * 0.6)].reshape(-1, 3), axis=0)
        sep = float(np.abs(gc - np.median(np.broadcast_to(bg, a.shape).reshape(-1, 3), axis=0)).sum())
        m = d > min(120.0, max(24.0, 0.3 * sep))
    m = ndi.binary_closing(m, structure=np.ones((5, 5)), iterations=2)
    m = ndi.binary_fill_holes(m)
    lab, n = ndi.label(m)
    if n == 0:
        return None
    sizes = ndi.sum(m, lab, range(1, n + 1))
    keep = 1 + int(np.argmax(sizes))
    return lab == keep

def measure(path):
    """Measures with a plain backdrop first. A shaded backdrop (grey darkening to the edges) can join the shadow to the
    garment and push the centre line off to one side, so the shaded way is measured too. It wins only when it reads
    sensibly and sits clearly nearer the middle (every photo in the library is centred when it's made). 10 Nov 2026"""
    a, W, H = load(path)
    r0 = _measure(a, mask_of(a), False)
    m2 = mask_of(a, True)
    r1 = _measure(a, m2, True) if m2 is not None else None
    if r1 and r1['cw'] >= 150 and (not r0 or (abs(r1['cx'] - 500) + 20 < abs(r0['cx'] - 500) and r1['cw'] >= 0.7 * r0['cw'])):
        return r1
    if r0 and r0['cw'] >= 150:
        return r0
    # a white garment on a white or pale grey backdrop: neither reads, so look again with a finer cut-off
    for thr in (14, 10, 8):
        m = np.abs(a - flat_bg(a)).sum(axis=2) > thr
        m = ndi.binary_fill_holes(ndi.binary_closing(m, structure=np.ones((5, 5)), iterations=2))
        lab, n = ndi.label(m)
        if not n:
            continue
        sizes = ndi.sum(m, lab, range(1, n + 1))
        r = _measure(a, lab == (1 + int(np.argmax(sizes))), False)
        if r and r['cw'] >= 150 and abs(r['cx'] - 500) <= 60:
            return r
    return r0

def _measure(a, m, shaded):
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
        raw = ndi.binary_fill_holes(ndi.binary_closing(np.abs(a - (bg_model(a) if shaded else flat_bg(a))).sum(axis=2) > 24, structure=np.ones((3, 3))))
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
    # the top of the shoulder where it meets the neck: follow the slope of the shoulder in from the sleeve (36% to 48%
    # of the chest out from the centre, clear of a hood) and carry it in to 30% out, about where a hood sits. A hood or collar sitting higher in the
    # middle doesn't move it, so it's the same point on a tee and a hoodie
    hp = []
    for sd in (-1, 1):
        ts, yv = [], []
        for t_ in np.linspace(0.36, 0.48, 8):
            xx = int(round(cx + sd * t_ * cw))
            if 0 <= xx < w:
                col = np.where(m[:, xx])[0]
                if len(col):
                    ts.append(t_); yv.append(col[0])
        if len(ts) >= 4:
            b_, a_ = np.polyfit(ts, yv, 1)
            hp.append(a_ + b_ * 0.30)
    hps = int(round(np.median(hp))) if hp else sh
    hps = max(top, min(hps, sh + int(0.12 * GH)))
    f = lambda v, n: int(round(v / n * 1000))
    return {'cx': f(cx, w), 'top': f(top, h), 'bot': f(bot, h), 'ctop': f(ctop, h), 'cy': f(cyv, h),
            'cl': f(cx - cw / 2, w), 'cr': f(cx + cw / 2, w), 'cw': f(cw, w), 'l': f(left, w), 'r': f(right, w), 'sh': f(sh, h), 'hps': f(hps, h), 'k': flag}

if __name__ == '__main__':
    for p in sys.argv[1:]:
        print(p, json.dumps(measure(p)))
