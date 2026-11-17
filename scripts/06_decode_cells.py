#!/usr/bin/env python3
"""Decode every cell from glyph-cluster ids and cluster labels.

For each cell the glyphs are put in left-to-right order and their cluster
labels are concatenated:
    2, 9, <dot>, 2, 5  ->  29.25

A decimal point is recognised by its glyph size (tiny component), not by OCR.
Any non-digit label (e.g. 缺 / 禁 / 考) marks the cell as ABSENT; it is not a
numeric result and downstream statistics count it as a failed attempt.

Output record:
    {"page": "s1_p1", "tag": "s1", "pno": 1, "row": 1,
     "id": "...", "credits": "...", "gpa": "...", "wavg": "...",
     "scores": {"6": "80", ..., "54": "ABSENT"}}
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glyphs", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--problems", default=None)
    ap.add_argument("--id-col", type=int, default=0)
    ap.add_argument("--credits-col", type=int, default=3)
    ap.add_argument("--gpa-col", type=int, default=4)
    ap.add_argument("--wavg-col", type=int, default=5)
    ap.add_argument("--score-start", type=int, default=6)
    ap.add_argument("--id-len", type=int, default=10,
                    help="expected number of digits in the id column; 0 disables")
    args = ap.parse_args()

    data = json.loads(Path(args.glyphs).read_text(encoding="utf-8"))
    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    glyphs = data["glyphs"]
    if not glyphs:
        raise SystemExit("no glyphs")

    # A decimal point is a tiny component.  Determine this from all glyphs in
    # the cluster, not from the OCR label.
    by_cid = defaultdict(list)
    for g in glyphs:
        by_cid[g["cid"]].append(g)
    dot_cids = set()
    for cid, gs in by_cid.items():
        ws = sorted(x["w"] for x in gs)
        hs = sorted(x["h"] for x in gs)
        if ws[len(ws) // 2] <= 11 and hs[len(hs) // 2] <= 12:
            dot_cids.add(cid)

    cells = defaultdict(list)
    for g in glyphs:
        cells[(g["page"], g["r"], g["c"])].append(g)

    raw = {}
    for (page, r, c), gs in cells.items():
        gs.sort(key=lambda x: x["k"])
        text = ""
        absent = False
        for g in gs:
            cid = g["cid"]
            if cid in dot_cids:
                text += "."
            elif labels[cid].isdigit():
                text += labels[cid]
            else:
                absent = True
        raw[(page, r, c)] = "ABSENT" if absent else text

    rows = defaultdict(dict)
    for (page, r, c), v in raw.items():
        rows[(page, r)][c] = v

    records, problems = [], []
    for (page, r), row in sorted(rows.items()):
        tag, pno = page.rsplit("_p", 1)
        rec = {
            "page": page, "tag": tag, "pno": int(pno), "row": r + 1,
            "id": row.get(args.id_col, ""),
            "credits": row.get(args.credits_col, ""),
            "gpa": row.get(args.gpa_col, ""),
            "wavg": row.get(args.wavg_col, ""),
            "scores": {str(c): v for c, v in row.items()
                       if c >= args.score_start},
        }
        records.append(rec)

        if args.id_len and not re.fullmatch(r"\d{%d}" % args.id_len, rec["id"]):
            problems.append([page, r + 1, "id", rec["id"]])
        if rec["credits"] and not re.fullmatch(r"\d{1,2}\.\d{2}", rec["credits"]):
            problems.append([page, r + 1, "credits", rec["credits"]])
        if rec["gpa"] and not re.fullmatch(r"\d\.\d{1,2}", rec["gpa"]):
            problems.append([page, r + 1, "gpa", rec["gpa"]])
        if rec["wavg"] and not re.fullmatch(r"\d{2,3}\.\d{1,2}", rec["wavg"]):
            problems.append([page, r + 1, "wavg", rec["wavg"]])
        for c, v in rec["scores"].items():
            if v == "ABSENT":
                continue
            if not re.fullmatch(r"\d{1,3}", v):
                problems.append([page, r + 1, "score c" + c, v])
            elif not (0 <= int(v) <= 100):
                problems.append([page, r + 1, "score range c" + c, v])

    Path(args.out).write_text(json.dumps(records, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print("students=%d problems=%d" % (len(records), len(problems)))
    for p in problems[:40]:
        print("  ", p)
    if args.problems:
        Path(args.problems).write_text(json.dumps(problems, ensure_ascii=False, indent=1),
                                       encoding="utf-8")


if __name__ == "__main__":
    main()
