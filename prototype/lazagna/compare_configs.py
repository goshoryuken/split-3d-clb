#!/usr/bin/env python3
"""Compare sweep results of different CLB configurations against one baseline.

Each argument after the baseline is LABEL=FILE:FABRIC, where FILE is a results
CSV from compare_2d_3d.py and FABRIC is its 2d or 3d rows. Ratios are candidate
delay over baseline delay, averaged over seeds per benchmark, then a geometric
mean over benchmarks that routed for every seed in both. --column compares another
column the same way, e.g. chan_width for the routed widths of --relax-w runs.

Usage: compare_configs.py [--column NAME] BASE_FILE:FABRIC LABEL=FILE:FABRIC...
"""
import collections
import csv
import statistics
import sys


COLUMN = "cpd_ns"


def load(spec):
    path, fabric = spec.rsplit(":", 1)
    delays = collections.defaultdict(dict)
    failed = 0
    for row in csv.DictReader(open(path)):
        if row["fabric"] != fabric:
            continue
        if row["routed"] == "True":
            delays[row["bench"]][row["seed"]] = float(row[COLUMN])
        else:
            failed += 1
    return delays, failed


def main():
    global COLUMN
    args = sys.argv[1:]
    if args[0] == "--column":
        COLUMN, args = args[1], args[2:]
    base, _ = load(args[0])
    lower = "faster on" if COLUMN == "cpd_ns" else "lower on"
    print(f"{'configuration':34}{'geomean':>9}{lower:>11}  per seed")
    for arg in args[1:]:
        label, spec = arg.split("=", 1)
        cand, failed = load(spec)
        # Compare on the seeds both files ran.
        seeds = sorted({s for runs in base.values() for s in runs} & {s for runs in cand.values() for s in runs}, key=int)
        benches = [b for b in base if b in cand and set(seeds) <= set(cand[b]) and set(seeds) <= set(base[b])]
        ratios = [statistics.mean(cand[b][s] for s in seeds) / statistics.mean(base[b][s] for s in seeds) for b in benches]
        per_seed = [statistics.geometric_mean([cand[b][s] / base[b][s] for b in benches]) for s in seeds]
        note = f"  ({failed} runs failed)" if failed else ""
        print(f"{label:34}{statistics.geometric_mean(ratios):9.3f}{sum(r < 1 for r in ratios):>6}/{len(ratios):<4}"
              f"  {' '.join(f'{x:.3f}' for x in per_seed)}{note}")


if __name__ == "__main__":
    main()
