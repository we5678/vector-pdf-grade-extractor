#!/usr/bin/env python3
"""Segment characters inside every data cell and cluster identical shapes.

The source PDFs draw text as vector outlines; Windows OCR is good at Chinese
headers but often mistakes the digit 0 for characters such as 刀 / 艺 / 生.
Clustering the actual glyph shapes sidesteps that: the same printed digit is
pixel-identical across the sheet, so a handful of clusters covers thousands of
cells.

Outputs (in --out-dir):
    glyphs.json          cluster list + one record per glyph
    reps.npy             one 32x48 bitmap per cluster
    cluster_sheet.png    contact sheet used to label clusters with OCR
    cluster_sheet.json   geometry of the contact sheet

Privacy note: this script only writes shape data, never the source PDF.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

GW, GH = 32, 48


def feat(binary):
    canvas = np.zeros((GH, GW), np.uint8)
    h, w = binary.shape[:2]
    h2, w2 = min(h, GH), min(w, GW)
    canvas[:h2, :w2] = binary[:h2, :w2]
    return canvas.astype(np.float32) / 255.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grids", required=True)
    ap.add_argument("--pages", required=True, help="rendered page PNG directory")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--dpi", type=int, default=400)
    ap.add_argument("--header-gap", type=float, default=60.0)
    ap.add_argument("--skip-cols", default="1,2",
                    help="comma-separated column indexes to ignore (name/sex)")
    ap.add_argument("--threshold", type=float, default=0.03,
                    help="greedy cluster distance; raise it if you get too many clusters")
    args = ap.parse_args()

    skip = {int(x) for x in args.skip_cols.split(",") if x.strip()}
    scale = args.dpi / 72.0
    grids = json.loads(Path(args.grids).read_text(encoding="utf-8"))
    pages_dir = Path(args.pages)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    glyphs = []
    clusters = []  # [representative, count]

    for tag, doc in grids.items():
        vs = doc["pages"][0]["v"]
        cols = len(vs) - 1
        for pno, page in enumerate(doc["pages"], 1):
            hs = page["h"]
            start = 1 if len(hs) > 1 and hs[1] - hs[0] > args.header_gap else 0
            rows = len(hs) - 1 - start
            if rows <= 0:
                continue
            img = cv2.imread(str(pages_dir / ("%s_p%d.png" % (tag, pno))),
                             cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise SystemExit("missing %s_p%d.png" % (tag, pno))
            for r in range(rows):
                y0 = int(round(hs[start + r] * scale)) + 4
                y1 = int(round(hs[start + r + 1] * scale)) - 4
                for c in range(cols):
                    if c in skip:
                        continue
                    x0 = int(round(vs[c] * scale)) + 1
                    x1 = int(round(vs[c + 1] * scale)) - 1
                    cell = img[y0:y1, x0:x1]
                    if cell.size == 0:
                        continue
                    bw = cv2.threshold(cell, 180, 255, cv2.THRESH_BINARY_INV)[1]
                    n, _, stats, _ = cv2.connectedComponentsWithStats(bw, 8)
                    comps = []
                    for st in stats[1:]:
                        x, y, w, h, area = st
                        if area < 15 or h < 4 or h > 55 or w < 2 or w > 45:
                            continue
                        if h <= 6 and w >= 12:      # horizontal rule remnant
                            continue
                        if w <= 6 and h >= 12:      # vertical rule remnant
                            continue
                        comps.append(st)
                    comps.sort(key=lambda t: t[0])
                    for k, st in enumerate(comps):
                        x, y, w, h, _ = st
                        vec = feat(bw[y:y + h, x:x + w])
                        best, best_d = -1, 1e9
                        for ci, (rep, _cnt) in enumerate(clusters):
                            d = float(np.mean(np.abs(rep - vec)))
                            if d < best_d:
                                best, best_d = ci, d
                        if best >= 0 and best_d < args.threshold:
                            clusters[best][1] += 1
                            cid = best
                        else:
                            clusters.append([vec, 1])
                            cid = len(clusters) - 1
                        glyphs.append({
                            "page": "%s_p%d" % (tag, pno), "r": r, "c": c,
                            "k": k, "cid": int(cid), "w": int(w), "h": int(h),
                        })

    print("glyphs=%d clusters=%d" % (len(glyphs), len(clusters)))
    (out_dir / "glyphs.json").write_text(json.dumps(
        {"clusters": [{"count": c[1]} for c in clusters], "glyphs": glyphs},
        ensure_ascii=False), encoding="utf-8")
    np.save(out_dir / "reps.npy", np.array([c[0] for c in clusters]))

    # Contact sheet: bigger clusters first? Keep original order so ids match.
    n = len(clusters)
    sheet_cols = 6
    rows = (n + sheet_cols - 1) // sheet_cols
    margin = 12
    tile_w = 200
    tile_h = min(260, max(120, (9800 - margin * 2) // max(rows, 1)))
    scale_px = 4
    while scale_px > 1 and GH * scale_px > tile_h - 16:
        scale_px -= 1
    sheet = np.full((margin * 2 + rows * tile_h,
                     margin * 2 + sheet_cols * tile_w, 3), 255, np.uint8)
    for i, (rep, _cnt) in enumerate(clusters):
        im = (255 - rep * 255).astype(np.uint8)  # dark glyph on white
        im = cv2.resize(im, (GW * scale_px, GH * scale_px),
                        interpolation=cv2.INTER_NEAREST)
        ox = margin + (i % sheet_cols) * tile_w + (tile_w - GW * scale_px) // 2
        oy = margin + (i // sheet_cols) * tile_h + (tile_h - GH * scale_px) // 2
        sheet[oy:oy + GH * scale_px, ox:ox + GW * scale_px] = cv2.cvtColor(
            im, cv2.COLOR_GRAY2BGR)
    if sheet.shape[0] > 9800:
        raise SystemExit(
            "Contact sheet is too tall (%d px). Raise --threshold or split the "
            "clusters into several sheets." % sheet.shape[0])
    cv2.imwrite(str(out_dir / "cluster_sheet.png"), sheet)
    (out_dir / "cluster_sheet.json").write_text(json.dumps({
        "cols": sheet_cols, "tile_w": tile_w, "tile_h": tile_h,
        "margin": margin, "n": n,
    }, indent=1), encoding="utf-8")
    print("wrote", out_dir / "cluster_sheet.png", sheet.shape)


if __name__ == "__main__":
    main()
