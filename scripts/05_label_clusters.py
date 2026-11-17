#!/usr/bin/env python3
"""Turn the OCR of the cluster contact sheet into cluster labels.

Run Windows OCR on cluster_sheet.png first:

    powershell -NoProfile -File scripts/ocr_windows.ps1 \
        -ImagePath work/cluster_sheet.png \
        -OutPath work/cluster_sheet_ocr.json

Then:

    python scripts/05_label_clusters.py \
        --ocr-json work/cluster_sheet_ocr.json \
        --sheet work/cluster_sheet.json \
        --glyphs work/glyphs.json \
        --out work/cluster_labels.json

Digits become their digit character.  Anything else (e.g. 缺, 禁, 考) is kept
as a non-digit label; the decoder treats such cells as "no result / absent".

Small decimal points are usually not recognised by OCR.  They are recovered
later from the glyph bounding-box size (see 06_decode_cells.py).
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ocr-json", required=True)
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--glyphs", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    geom = json.loads(Path(args.sheet).read_text(encoding="utf-8"))
    glyphs = json.loads(Path(args.glyphs).read_text(encoding="utf-8"))
    words = json.loads(Path(args.ocr_json).read_text(encoding="utf-8"))
    n = len(glyphs["clusters"])

    tw, th = geom["tile_w"], geom["tile_h"]
    cols = geom["cols"]
    margin = geom["margin"]
    tiles = defaultdict(list)
    for w in words:
        cx = w["x"] + w["w"] / 2
        cy = w["y"] + w["h"] / 2
        if cx < margin or cy < margin:
            continue
        c = int((cx - margin) // tw)
        r = int((cy - margin) // th)
        i = r * cols + c
        if 0 <= i < n:
            tiles[i].append(w)

    labels = []
    for i in range(n):
        ws = sorted(tiles.get(i, []), key=lambda w: (w["y"], w["x"]))
        labels.append("".join(w["text"] for w in ws))

    Path(args.out).write_text(json.dumps(labels, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    labeled = sum(1 for x in labels if x)
    print("labeled %d/%d clusters -> %s" % (labeled, n, args.out))
    missing = [i for i, x in enumerate(labels) if not x]
    if missing:
        print("unlabeled ids:", missing[:30])


if __name__ == "__main__":
    main()
