#!/usr/bin/env python3
"""Split with the layer pass vs without it, and each vs stacked (run_layerpass.sh).

Ratios as crossings_table.py: per design, mean CPD over the seeds that routed in both files,
candidate over base; then the geometric mean over designs. "no conv" leaves out conv_layer;
"drop design" leaves out any design with a failed run (compare_configs.py's rule); "seed sd" is
the standard deviation over seeds of the per-seed geomean. Pass-off and stacked rows are the
committed CSVs (k = 1: ../route, ../ideal; k = 1.62, 1.62 + pins, 2.24, 2.72, 3.0: ../crossings).
--fill: the runs that did not route within VPR's 50 router iterations take their rerun at 200
(run_failed.sh; iter200/ holds those rows under each CSV's path below seeds10/). Only failed rows are
replaced.
Usage: layerpass_table.py [OUT] [--fill]   (OUT holds k<NNN>_{route,ideal}/split/; default: here)
"""
import collections
import csv
import os
import statistics as st
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
S10 = os.path.dirname(HERE)
FILL = False


def filled(path, rows):
    """rows with each failed run replaced by its rerun at 200 router iterations, if there is one."""
    fill = os.path.join(HERE, "iter200", os.path.relpath(os.path.realpath(path), S10))
    if not FILL or not os.path.exists(fill):
        return rows
    new = {(r["fabric"], r["bench"], r["seed"]): r for r in csv.DictReader(open(fill))}
    out = []
    for row in rows:
        key = (row["fabric"], row["bench"], row["seed"])
        if key in new:
            assert row["routed"] != "True", f"{path}: {key} routed already"
            row = new[key]
        out.append(row)
    return out


def load(paths):
    """paths: a CSV path, a (path, fabric) pair (fabric "2d" reads the 2D rows), or a list of them."""
    cpd, failed = collections.defaultdict(dict), []
    for path in [paths] if isinstance(paths, (str, tuple)) else paths:
        path, fabric = path if isinstance(path, tuple) else (path, "3d")
        for row in filled(path, list(csv.DictReader(open(path)))):
            add(row, cpd, failed, fabric)
    return cpd, failed


def add(row, cpd, failed, fabric="3d"):
    if row["fabric"] == fabric:
        if row["routed"] == "True":
            cpd[row["bench"]][row["seed"]] = float(row["cpd_ns"])
        else:
            failed.append(f"{row['bench']} s{row['seed']}")


def compare(cand_path, base_path, drop=()):
    cand, base = load(cand_path)[0], load(base_path)[0]
    per = {}
    for bench in sorted(set(cand) & set(base) - set(drop)):
        seeds = sorted(set(cand[bench]) & set(base[bench]), key=int)
        per[bench] = (st.mean(cand[bench][s] for s in seeds) / st.mean(base[bench][s] for s in seeds), len(seeds))
    full = [r for r, n in per.values() if n == 10]
    per_seed = [st.geometric_mean([cand[b][s] / base[b][s] for b in per if s in cand[b] and s in base[b]])
                for s in map(str, range(1, 11))]
    return st.geometric_mean([r for r, _ in per.values()]), st.geometric_mean(full), len(full), per, per_seed


def short(bench):
    """A design's short name; tpu_like.small.ws (experiment C) is told apart from tpu_like.small.os."""
    return bench.split("_")[0][:6] + (".ws" if bench.endswith(".ws") else "")


def row(label, cand, base):
    g, g_drop, n_drop, per, per_seed = compare(cand, base)
    g_noconv = compare(cand, base, drop=("conv_layer",))[0]
    faster = sum(r < 1 for r, _ in per.values())
    designs = " ".join(f"{short(b)} {r:.3f}" + (f"[{n}]" if n < 10 else "") for b, (r, n) in per.items())
    print(f"{label:30}{g:8.3f}{g_noconv:9.3f}{faster:>5}/{len(per)}{g_drop:9.3f} ({n_drop}){st.stdev(per_seed):8.3f}"
          f"{min(per_seed):7.3f}{max(per_seed):7.3f}  {designs}")


POINTS = [  # label, pass-on dir, pass-off split CSV, stacked CSV (sub = route / ideal)
    ("k = 1.00 (SPICE)", "k100", "{S10}/{sub}/split/results_columns.csv", "{S10}/{sub}/stack/results_columns.csv"),
    ("k = 1.62", "k162", "{S10}/crossings/k162_{sub}/split/results_columns.csv",
     "{S10}/crossings/k162_{sub}/stack/results_columns.csv"),
    ("k = 1.62 + pins", "k162pin", "{S10}/crossings/k162pin_{sub}/split/results_columns.csv",
     "{S10}/crossings/k162_{sub}/stack/results_columns.csv"),
    ("k = 2.24", "k224", "{S10}/crossings/k224_{sub}/split/results_columns.csv",
     "{S10}/crossings/k224_{sub}/stack/results_columns.csv"),
    ("k = 2.72", "k272", "{S10}/crossings/k272_{sub}/split/results_columns.csv",
     "{S10}/crossings/k272_{sub}/stack/results_columns.csv"),
    ("k = 3.00", "k300", "{S10}/crossings/k300_{sub}/split/results_columns.csv",
     "{S10}/crossings/k300_{sub}/stack/results_columns.csv"),
]
HEAD = (f"{'':30}{'geomean':>8}{'no conv':>9}{'faster':>8}{'drop design':>13}{'seed sd':>8}{'min':>7}{'max':>7}"
        "  per design (seeds used, if fewer than 10)")


def main():
    global FILL
    args = [a for a in sys.argv[1:] if a != "--fill"]
    FILL = "--fill" in sys.argv[1:]
    out = args[0] if args else HERE
    for clock, sub in (("ideal", "ideal"), ("routed", "route")):
        table(out, clock, sub)


def table(OUT, clock, sub):
    print(f"== {clock} clocks" + (" (failed runs rerun at 200 router iterations, --fill)" if FILL else ""))
    print(HEAD)
    for label, tag, off, stack in POINTS:
        off, stack = off.format(S10=S10, sub=sub), stack.format(S10=S10, sub=sub)
        on = f"{OUT}/{tag}_{sub}/split/results_columns.csv"
        if not os.path.exists(on):
            continue
        row(f"{label}: off / stacked", off, stack)
        row(f"{label}: on / stacked", on, stack)
        row(f"{label}: on / off", on, off)
        for kind, path in (("pass-off", off), ("pass-on", on)):
            failed = load(path)[1]
            if failed:
                print(f"{'':30}{kind} runs that failed: {', '.join(failed)}")
        control = f"{OUT}/control_{tag}_{sub}/split/results_columns.csv"
        if os.path.exists(control):
            row(f"{label}: control / off", control, off)
            row(f"{label}: on / control", on, control)
            failed = load(control)[1]
            if failed:
                print(f"{'':30}control runs that failed: {', '.join(failed)}")
    print()


if __name__ == "__main__":
    main()
