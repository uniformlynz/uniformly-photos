# Uniformly photos

Garment colour photos for the Uniformly workshop tool, served by GitHub Pages at
https://uniformlynz.github.io/uniformly-photos/

- `photos.json` lists every photo by brand, style code and colour, as `[front, back, model]`.
  The workshop tool reads it when it opens and puts the photos on each garment's card.
- `cloke/...`, `thread-project/...`, `aussie-pacific/...` and `c-force/...`: `<style>/<colour>-front.webp`, `-back.webp`, `-model.webp`, the suppliers' own product photos shrunk for the screen.

The images belong to the supplier and are used under their reseller image guidelines
(no recolouring or other changes to the pictures themselves).

## Garment measurements for mockups (7 Nov 2026)

- `fits.json` says where the garment sits in every front and back photo, as thousandths of the image:
  `[centre x, chest line y, chest width, top y, bottom y]`. The chest line is just under the armpits.
- The workshop's Garments and artwork tab uses it to lay the logo on the photo at its real size: a print
  `P` mm wide on a garment whose size M is `C` cm across the chest (half chest, laid flat) is
  `chest width x P / (C x 10)` of the photo wide. The website's flat mockups can use the same numbers.
- After adding photos, run `python3 tools/measure_all.py` (needs numpy, scipy and Pillow) and commit `fits.json`.
