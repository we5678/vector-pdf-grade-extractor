#!/usr/bin/env python3
"""Cut every data cell and pack the cells into one "sheet" per page.

Why: running OCR on the full table makes adjacent numbers bleed into each
other, and small decimal points are easily lost.  Packing each cell into its
own fixed-size tile with white padding gives OCR an isolated sample.

Header handling
---------------
The first page of each PDF has a tall header row (vertical course names).
Continuation pages usually repeat no header.  We detect the header by the
height of the first horizontal band: if it is larger than --header-gap, the
band is treated as the header and skipped.  Data rows are everything after it.

Output
------
work/cells/s1_p1.png, ... and work/cells/meta.json
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

MAX_OCR_DIM = 9800  # Windows OCR refuses images larger than 10,000 px


def fit_tile(tw: int, th: int, cols: int, rows: int, gap: int, margin: int):
    """Shrink tiles until the whole sheet fits in the OCR dimension limit."""
    width = margin * 2 + cols * (tw + gap) - gap
    height = margin * 2 + rows * (th + gap) - gap
    if width > MAX_OCR_DIM:
        tw = max(60, (MAX_OCR_DIM - margin * 2 + gap) // cols - gap)
    if height > MAX_OCR_DIM:
        th = max(90, (MAX_OCR_DIM - margin * 2 + gap) // rows - gap)
    width = margin * 2 + cols * (tw + gap) - gap
    height = margin * 2 + rows * (th + gap) - gap
    if width > MAX_OCR_DIM or height > MAX_OCR_DIM:
        raise SystemExit(
            "Sheet is still %dx%d after shrinking. Reduce --tile-w/--tile-h "
            "or split the page." % (width, height)
        )
    return tw, th


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", required=True, help="rendered page PNG directory")
    ap.add_argument("--grids", required=True, help="grids.json from 01_extract_grids.py")
    ap.add_argument("--out", required=True, help="output directory for cell sheets")
    ap.add_argument("--dpi", type=int, default=400)
    ap.add_argument("--header-gap", type=float, default=60.0,
                    help="first band taller than this (pt) is a header")
    ap.add_argument("--tile-w", type=int, default=150)
    ap.add_argument("--tile-h", type=int, default=320)
    ap.add_argument("--gap", type=int, default=12)
    ap.add_argument("--margin", type=int, default=12)
    args = ap.parse_args()

    pages_dir = Path(args.pages)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    grids = json.loads(Path(args.grids).read_text(encoding="utf-8"))
    scale = args.dpi / 72.0

    meta = {"pages": []}

    for tag, doc in grids.items():
        vs = doc["pages"][0]["v"]
        if len(vs) < 2:
            print("skip %s: no vertical rules" % tag)
            continue
        cols = len(vs) - 1
        for pno, page in enumerate(doc["pages"], 1):
            hs = page["h"]
            start = 1 if len(hs) > 1 and hs[1] - hs[0] > args.header_gap else 0
            rows = len(hs) - 1 - start
            if rows <= 0:
                continue
            tw, th = fit_tile(args.tile_w, args.tile_h, cols, rows, args.gap, args.margin)
            img = cv2.imread(str(pages_dir / ("%s_p%d.png" % (tag, pno))))
            if img is None:
                raise SystemExit("missing page image %s_p%d.png" % (tag, pno))
            canvas = np.full(
                (args.margin * 2 + rows * (th + args.gap),
                 args.margin * 2 + cols * (tw + args.gap)),
                255, np.uint8,
            )
            for r in range(rows):
                y0 = int(round(hs[start + r] * scale)) + 3
                y1 = int(round(hs[start + r + 1] * scale)) - 3
                for c in range(cols):
                    x0 = int(round(vs[c] * scale)) + 2
                    x1 = int(round(vs[c + 1] * scale)) - 2
                    cell = img[max(0, y0):y1, max(0, x0):x1]
                    if cell.size == 0:
                        continue
                    h, w = cell.shape[:2]
                    ar = w / h
                    inner_w, inner_h = tw - 16, th - 16
                    if ar > inner_w / inner_h:
                        nw, nh = inner_w, max(1, int(inner_w / ar))
                    else:
                        nh, nw = inner_h, max(1, int(inner_h * ar))
                    cell = cv2.resize(cell, (nw, nh), interpolation=cv2.INTER_CUBIC)
                    ox = args.margin + c * (tw + args.gap) + (tw - nw) // 2
                    oy = args.margin + r * (th + args.gap) + (th - nh) // 2
                    canvas[oy:oy + nh, ox:ox + nw] = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
            fn = out_dir / ("%s_p%d.png" % (tag, pno))
            cv2.imwrite(str(fn), canvas)
            meta["pages"].append({"page": "%s_p%d" % (tag, pno), "tag": tag,
                                  "pno": pno, "rows": rows, "cols": cols,
                                  "tw": tw, "th": th,
                                  "gap": args.gap, "margin": args.margin})
            print(fn, rows, "x", cols, canvas.shape)

    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", out_dir / "meta.json")


if __name__ == "__main__":
    main()
