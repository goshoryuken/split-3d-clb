#!/usr/bin/env python3
"""Split over stacked critical-path delay with every layer crossing scaled by k (run_crossings.sh).

Per design: mean CPD over the seeds that routed in both fabrics, split over stacked; then the
geometric mean over designs. A run that did not route drops only that seed of that design.
"drop design" is compare_configs.py's rule instead (a design with any failed run is left out).
"seed sd": standard deviation over seeds of the per-seed geomean. k = 1 is the headline sweep.
Usage: crossings_table.py [DIR]   (DIR holds k<NNN>_{route,ideal}/ and abl224_*; default: here)
"""
import collections
import csv
import glob
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SEEDS10 = os.path.dirname(HERE)
DIR = sys.argv[1] if len(sys.argv) > 1 else HERE


def load(path):
    cpd = collections.defaultdict(dict)
    for row in csv.DictReader(open(path)):
        if row["fabric"] == "3d" and row["routed"] == "True":
            cpd[row["bench"]][row["seed"]] = float(row["cpd_ns"])
    return cpd


def compare(cand_path, base_path, drop=()):
    cand, base = load(cand_path), load(base_path)
    per = {}
    for bench in sorted(set(cand) & set(base) - set(drop)):
        seeds = sorted(set(cand[bench]) & set(base[bench]), key=int)
        per[bench] = (st.mean(cand[bench][s] for s in seeds) / st.mean(base[bench][s] for s in seeds), len(seeds))
    full = [r for r, n in per.values() if n == 10]
    per_seed = [st.geometric_mean([cand[b][s] / base[b][s] for b in per if s in cand[b] and s in base[b]])
                for s in map(str, range(1, 11))]
    return st.geometric_mean([r for r, _ in per.values()]), st.geometric_mean(full), len(full), per, st.stdev(per_seed)


def row(label, cand, base):
    g, g_drop, n_drop, per, sd = compare(cand, base)
    g_noconv = compare(cand, base, drop=("conv_layer",))[0]
    faster = sum(r < 1 for r, _ in per.values())
    designs = " ".join(f"{b.split('_')[0][:6]} {r:.3f}" + (f"[{n}]" if n < 10 else "") for b, (r, n) in per.items())
    print(f"{label:22}{g:8.3f}{g_noconv:9.3f}{faster:>5}/{len(per)}{g_drop:9.3f} ({n_drop}){sd:8.3f}  {designs}")


def k_label(k):
    return f"k = {int(k) / 100:.2f}"


ks = sorted(int(p.split(os.sep)[-3][1:-6]) for p in glob.glob(os.path.join(DIR, "k*_ideal", "stack", "results_columns.csv")))
head = (f"{'':22}{'geomean':>8}{'no conv':>9}{'faster':>8}{'drop design':>13}{'seed sd':>8}"
        "  per design (seeds used, if fewer than 10)")
for clock, sub in (("ideal", "ideal"), ("routed", "route")):
    print(f"== {clock} clocks: split over stacked, every crossing times k")
    print(head)
    row("k = 1.00 (SPICE)", f"{SEEDS10}/{sub}/split/results_columns.csv", f"{SEEDS10}/{sub}/stack/results_columns.csv")
    for k in ks:
        row(k_label(k), f"{DIR}/k{k}_{sub}/split/results_columns.csv", f"{DIR}/k{k}_{sub}/stack/results_columns.csv")
    if os.path.exists(f"{DIR}/abl224_ideal/split/results_columns.csv"):
        print("-- ablation fabric (split CLB on stacked's routing) over stacked")
        row("k = 1.00 (SPICE)", f"{SEEDS10}/ablation/strict_{sub}/results_columns.csv", f"{SEEDS10}/{sub}/stack/results_columns.csv")
        row("k = 2.24", f"{DIR}/abl224_{sub}/split/results_columns.csv", f"{DIR}/k224_{sub}/stack/results_columns.csv")
    print()
