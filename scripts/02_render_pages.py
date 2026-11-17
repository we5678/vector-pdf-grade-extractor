#!/usr/bin/env python3
"""Render every PDF page to a high-resolution PNG.

400 dpi is enough to keep printed digits crisp while staying below the
Windows OCR maximum image dimension (10,000 px).
"""

import argparse
from pathlib import Path

import pymupdf


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--dpi", type=int, default=400)
    args = ap.parse_args()

    pdfs = sorted(p for p in Path(args.pdf_dir).glob("*.pdf") if p.is_file())
    if not pdfs:
        raise SystemExit("No PDFs found")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    for idx, pdf in enumerate(pdfs, 1):
        tag = "s%d" % idx
        doc = pymupdf.open(pdf)
        for pno, page in enumerate(doc, 1):
            pix = page.get_pixmap(dpi=args.dpi)
            fn = out_dir / ("%s_p%d.png" % (tag, pno))
            pix.save(fn)
            print(fn, pix.width, pix.height)


if __name__ == "__main__":
    main()
