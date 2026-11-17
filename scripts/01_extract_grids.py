#!/usr/bin/env python3
"""Extract table rule coordinates from vector drawings in PDF files.

The input PDFs are expected to have been produced by a spreadsheet program and
printed with the table rules kept as vector strokes (not as raster images).
Each PDF gets a stable tag ``s1``, ``s2`` ... based on the sorted file order.

Output JSON:
    {
      "s1": {
        "file": "semester-1.pdf",
        "pages": [{"h": [y0, ...], "v": [x0, ...]}, ...]
      }
    }

Coordinates are in PDF points (72 per inch).
"""

import argparse
import json
from pathlib import Path

import pymupdf


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", required=True, help="directory containing the PDFs")
    ap.add_argument("--out", required=True, help="output grids.json")
    ap.add_argument("--min-h-len", type=float, default=50.0,
                    help="minimum width (pt) for a horizontal rule")
    ap.add_argument("--min-v-len", type=float, default=30.0,
                    help="minimum height (pt) for a vertical rule")
    ap.add_argument("--max-thickness", type=float, default=1.5,
                    help="maximum rule thickness (pt)")
    args = ap.parse_args()

    pdf_dir = Path(args.pdf_dir)
    pdfs = sorted(p for p in pdf_dir.glob("*.pdf") if p.is_file())
    if not pdfs:
        raise SystemExit("No PDFs found in %s" % pdf_dir)

    result = {}
    for idx, pdf in enumerate(pdfs, 1):
        tag = "s%d" % idx
        doc = pymupdf.open(pdf)
        pages = []
        for page in doc:
            hs, vs = set(), set()
            for item in page.get_drawings():
                r = item["rect"]
                if r.height < args.max_thickness and r.width > args.min_h_len:
                    hs.add(round(r.y0, 2))
                if r.width < args.max_thickness and r.height > args.min_v_len:
                    vs.add(round(r.x0, 2))
            pages.append({"h": sorted(hs), "v": sorted(vs)})
        result[tag] = {"file": pdf.name, "pages": pages}
        counts = [(len(p["h"]), len(p["v"])) for p in pages]
        print("%s <- %s  pages=%d  grid=%s" % (tag, pdf.name, len(pages), counts))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
