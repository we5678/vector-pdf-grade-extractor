#!/usr/bin/env python3
"""Export decoded records and statistics to Excel-friendly CSV files.

Files are written with a UTF-8 BOM so Excel opens Chinese correctly.

Names and course titles are optional and deliberately not part of this repo:

    --names-json  {"2024000001": "Example Name", ...}
    --courses-json {"s1": {"8": "Course name", ...}, ...}

Keep both files outside version control (the default .gitignore does this).
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decoded", required=True)
    ap.add_argument("--stats", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--names-json", default=None)
    ap.add_argument("--courses-json", default=None)
    ap.add_argument("--absent-label", default="缺考/禁考")
    args = ap.parse_args()

    data = json.loads(Path(args.decoded).read_text(encoding="utf-8"))
    stats = json.loads(Path(args.stats).read_text(encoding="utf-8"))
    names = (json.loads(Path(args.names_json).read_text(encoding="utf-8"))
             if args.names_json else {})
    courses = (json.loads(Path(args.courses_json).read_text(encoding="utf-8"))
               if args.courses_json else {})
    tags = sorted(t for t in stats if t != "combined")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    by_id = defaultdict(dict)
    for r in data:
        by_id[r["id"]][r["tag"]] = r

    headers = ["id", "name"]
    for t in tags:
        headers += ["%s_credits" % t, "%s_gpa" % t, "%s_wavg" % t]
    headers += ["credits_total", "gpa_cumulative", "fail_count"]

    student_rows = []
    for sid, sem in sorted(by_id.items()):
        row = {"id": sid, "name": names.get(sid, "")}
        gsum = csum = 0.0
        fails = 0
        for t in tags:
            r = sem.get(t)
            if not r:
                for k in ("credits", "gpa", "wavg"):
                    row["%s_%s" % (t, k)] = ""
                continue
            row["%s_credits" % t] = r["credits"]
            row["%s_gpa" % t] = r["gpa"]
            row["%s_wavg" % t] = r["wavg"]
            if r["gpa"] and r["credits"]:
                g, c = float(r["gpa"]), float(r["credits"])
                gsum += g * c
                csum += c
            for v in r["scores"].values():
                if v == "ABSENT" or int(v) < 60:
                    fails += 1
        row["credits_total"] = round(csum, 2) if csum else ""
        row["gpa_cumulative"] = round(gsum / csum, 3) if csum else ""
        row["fail_count"] = fails
        student_rows.append(row)

    with open(out_dir / "students_summary.csv", "w", encoding="utf-8-sig",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(student_rows)

    fail_rows = []
    for r in data:
        for c, v in sorted(r["scores"].items(), key=lambda x: int(x[0])):
            if v == "ABSENT" or int(v) < 60:
                course = courses.get(r["tag"], {}).get(c, "col%s" % c)
                fail_rows.append({
                    "id": r["id"], "name": names.get(r["id"], ""),
                    "semester": r["tag"], "course": course,
                    "result": args.absent_label if v == "ABSENT" else v,
                    "page": r["page"], "row": r["row"], "col": c,
                })
    with open(out_dir / "fails_detail.csv", "w", encoding="utf-8-sig",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "name", "semester", "course",
                                          "result", "page", "row", "col"])
        w.writeheader()
        w.writerows(fail_rows)

    cb = stats["combined"]
    metrics = [
        ("students_valid", cb["students_valid"]),
        ("attempts", cb["attempts"]),
        ("fails_incl_absent", cb["fails_incl_absent"]),
        ("fail_rate_attempts", "%.2f%%" % (cb["fail_rate_attempts"] * 100)),
        ("students_with_fail", cb["students_with_fail"]),
        ("fail_student_rate", "%.2f%%" % (cb["fail_student_rate"] * 100)),
        ("sport_total", cb["sport_total"]),
        ("sport_pass", cb["sport_pass"]),
        ("sport_pass_rate", "%.2f%%" % (cb["sport_pass_rate"] * 100)),
        ("gpa_mean_all_semesters", "%.2f" % cb["gpa_mean_all_semesters"]),
        ("gpa_weighted", "%.2f" % cb["gpa_weighted"]),
    ]
    with open(out_dir / "metrics.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerows(metrics)

    print("wrote 3 CSV files ->", out_dir)


if __name__ == "__main__":
    main()
