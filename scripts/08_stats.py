#!/usr/bin/env python3
"""Compute fail rate, physical-education pass rate and class GPA.

Policy implemented here (adjust if your school uses a different rule):
  * A student with no scores and no credits in every semester is excluded from
    all denominators.
  * A score < 60 is a fail.
  * ABSENT (缺考 / 禁考) is counted as a failed attempt and as a fail for the
    student, but is reported separately.
  * PE pass rate counts PE scores >= 60; ABSENT is not a pass.
  * Class mean GPA = arithmetic mean of the per-student 学分绩点.
  * Credit-weighted GPA = sum(GPA * earned credits) / sum(earned credits).
    Note: earned credits exclude failed courses, so this can be slightly high.

Example:
    python scripts/08_stats.py --decoded work/decoded.json \
        --out work/stats.json --sport-cols '{"s1": 54, "s2": 28}'
"""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--decoded", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sport-cols", default="{}",
                    help='JSON map of semester tag -> PE column, e.g. {"s1":54}')
    args = ap.parse_args()

    data = json.loads(Path(args.decoded).read_text(encoding="utf-8"))
    sport = json.loads(args.sport_cols)
    by_tag = defaultdict(list)
    for rec in data:
        by_tag[rec["tag"]].append(rec)

    report = {}
    for tag, rs in by_tag.items():
        valid = [r for r in rs if r["scores"] or r["credits"]]
        attempts = fails = absent = 0
        fail_students = []
        fail_by_col = defaultdict(int)
        sport_total = sport_pass = sport_absent = 0
        for r in rs:
            f = 0
            for c, v in r["scores"].items():
                attempts += 1
                if v == "ABSENT":
                    absent += 1
                    f += 1
                    fail_by_col[int(c)] += 1
                elif int(v) < 60:
                    f += 1
                    fail_by_col[int(c)] += 1
            fails += f
            if f:
                fail_students.append([r["id"], f, len(r["scores"])])
            col = sport.get(tag)
            if col is not None:
                sv = r["scores"].get(str(col))
                if sv is not None:
                    sport_total += 1
                    if sv == "ABSENT":
                        sport_absent += 1
                    elif int(sv) >= 60:
                        sport_pass += 1

        gpas = [float(r["gpa"]) for r in valid if r["gpa"]]
        creds = [float(r["credits"]) for r in valid if r["credits"]]
        wavg = [float(r["wavg"]) for r in valid if r["wavg"]]
        pairs = [(float(r["gpa"]), float(r["credits"])) for r in valid
                 if r["gpa"] and r["credits"]]
        weighted = (sum(g * c for g, c in pairs) / sum(c for _, c in pairs)
                    if pairs else 0.0)

        report[tag] = {
            "students_total": len(rs),
            "students_valid": len(valid),
            "no_data": [r["id"] for r in rs if not (r["scores"] or r["credits"])],
            "attempts": attempts,
            "fails_incl_absent": fails,
            "absent_cells": absent,
            "fail_rate_attempts": fails / attempts if attempts else 0.0,
            "fail_students": fail_students,
            "fail_student_rate": len(fail_students) / len(valid) if valid else 0.0,
            "fail_by_col": dict(sorted(fail_by_col.items())),
            "sport_col": sport.get(tag),
            "sport_total": sport_total,
            "sport_pass": sport_pass,
            "sport_absent": sport_absent,
            "sport_pass_rate": sport_pass / sport_total if sport_total else 0.0,
            "gpa_mean": statistics.mean(gpas) if gpas else 0.0,
            "gpa_median": statistics.median(gpas) if gpas else 0.0,
            "gpa_weighted": weighted,
            "wavg_mean": statistics.mean(wavg) if wavg else 0.0,
            "credits_total": sum(creds),
        }

    valid_ids = set()
    for tag, rs in by_tag.items():
        valid_ids |= {r["id"] for r in rs if r["scores"] or r["credits"]}
    fail_map = defaultdict(int)
    for tag in report:
        for sid, f, _n in report[tag]["fail_students"]:
            fail_map[sid] += f
    attempts = sum(report[t]["attempts"] for t in report)
    fails = sum(report[t]["fails_incl_absent"] for t in report)
    sport_total = sum(report[t]["sport_total"] for t in report)
    sport_pass = sum(report[t]["sport_pass"] for t in report)
    gpa_all, wsum, csum = [], 0.0, 0.0
    for r in data:
        if r["gpa"] and r["credits"]:
            g, c = float(r["gpa"]), float(r["credits"])
            gpa_all.append(g)
            wsum += g * c
            csum += c

    report["combined"] = {
        "students_valid": len(valid_ids),
        "attempts": attempts,
        "fails_incl_absent": fails,
        "fail_rate_attempts": fails / attempts if attempts else 0.0,
        "students_with_fail": len(fail_map),
        "fail_student_rate": len(fail_map) / len(valid_ids) if valid_ids else 0.0,
        "sport_total": sport_total,
        "sport_pass": sport_pass,
        "sport_pass_rate": sport_pass / sport_total if sport_total else 0.0,
        "gpa_mean_all_semesters": statistics.mean(gpa_all) if gpa_all else 0.0,
        "gpa_weighted": wsum / csum if csum else 0.0,
        "credits_total": csum,
    }

    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
