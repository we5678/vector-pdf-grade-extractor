#!/usr/bin/env python3
"""Cross-check the glyph decode against a second, independent OCR pass.

Run Windows OCR on every cell sheet produced by 03_build_cell_sheets.py:

    powershell -NoProfile -File scripts/ocr_windows.ps1 \
        -ImagePath work/cells/s1_p1.png \
        -OutPath work/cells/s1_p1_ocr.json

Then:

    python scripts/07_cross_check.py \
        --decoded work/decoded.json \
        --meta work/cells/meta.json \
        --ocr-dir work/cells \
        --out work/ocr_mismatches.json

Mismatches are not automatically errors: OCR often garbles decimals (0 -> 刀)
or misses a cell entirely.  The value of this pass is the opposite direction --
it finds cells where the glyph decoder produced nothing but OCR saw digits.
Review the short mismatch list, especially any low scores near 60.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def norm(s):
    if not s:
        return ""
    if "缺" in s or "禁" in s:  # 缺 / 禁
        return "ABSENT"
    return "".join(ch for ch in s if ch.isdigit())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decoded", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--ocr-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    decoded = json.loads(Path(args.decoded).read_text(encoding="utf-8"))
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    ocr_dir = Path(args.ocr_dir)

    dmap = {}
    for rec in decoded:
        page = rec["page"]
        for c, v in rec["scores"].items():
            dmap[(page, rec["row"] - 1, int(c))] = v
        dmap[(page, rec["row"] - 1, 0)] = rec["id"]
        dmap[(page, rec["row"] - 1, 3)] = rec["credits"]
        dmap[(page, rec["row"] - 1, 4)] = rec["gpa"]
        dmap[(page, rec["row"] - 1, 5)] = rec["wavg"]

    ocr = {}
    for pm in meta["pages"]:
        page = pm["page"]
        fn = ocr_dir / (page + "_ocr.json")
        if not fn.exists():
            print("missing OCR:", fn)
            continue
        words = json.loads(fn.read_text(encoding="utf-8"))
        tw, th, gap, margin = pm["tw"], pm["th"], pm["gap"], pm["margin"]
        cells = defaultdict(list)
        for w in words:
            cx = w["x"] + w["w"] / 2
            cy = w["y"] + w["h"] / 2
            if cx < margin or cy < margin:
                continue
            c = int((cx - margin) // (tw + gap))
            r = int((cy - margin) // (th + gap))
            if c < pm["cols"] and r < pm["rows"]:
                cells[(r, c)].append(w)
        for (r, c), ws in cells.items():
            ws.sort(key=lambda w: (w["y"], w["x"]))
            ocr[(page, r, c)] = "".join(w["text"] for w in ws)

    mismatches, ocr_only = [], []
    for key, dv in dmap.items():
        ov = ocr.get(key, "")
        if norm(dv) != norm(ov):
            mismatches.append({"page": key[0], "row": key[1] + 1,
                               "col": key[2], "decoded": dv, "ocr": ov})
    for key, ov in ocr.items():
        if key not in dmap and norm(ov):
            ocr_only.append({"page": key[0], "row": key[1] + 1,
                             "col": key[2], "ocr": ov})

    print("decoded cells=%d  ocr cells=%d" % (len(dmap), len(ocr)))
    print("mismatches=%d  ocr-only=%d" % (len(mismatches), len(ocr_only)))
    for m in ocr_only[:20]:
        print("  OCR-only:", m)
    Path(args.out).write_text(json.dumps(
        {"mismatches": mismatches, "ocr_only": ocr_only},
        ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
