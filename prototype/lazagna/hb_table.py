#!/usr/bin/env python3
"""Tables for the hard-block study (run_hardblocks.sh): every placement against 2D and against each other.

Reads OUT/{split,stack}/results_<placement>.csv; the 2D rows of all of them are merged (the same
2D runs, by benchmark and seed), so each comparison uses the seeds both sides ran. A benchmark counts for a pair of
configurations only if it routed on every seed in both (as compare_configs.py); ratios are
mean over seeds per benchmark, then a geometric mean over benchmarks. Footprint is the grid's
interior cells, (grid - 2)^2; die cells multiply that by the layers (the third layer of the
layer placement included). Wirelength is VPR's total, in tiles, over all layers.

Usage: hb_table.py OUT [--per-bench] [--cost]
"""
import collections
import csv
import statistics
import sys
from pathlib import Path

PLACEMENTS = ["columns", "stacked", "span", "layer"]
FABRICS = ["split", "stack"]


def load(path, fabric):
    """bench -> seed -> row, for routed rows of this fabric; and the failed rows."""
    good, failed = collections.defaultdict(dict), []
    if not path.exists():
        return good, failed
    for row in csv.DictReader(open(path)):
        if row["fabric"] != fabric:
            continue
        if row["routed"] == "True":
            good[row["bench"]][row["seed"]] = row
        else:
            failed.append(row)
    return good, failed


def add_min_width(rows, folder):
    """Each run's minimum channel width (per layer), from width.txt of relaxed runs (--relax-w)."""
    for bench, runs in rows.items():
        for seed, row in runs.items():
            tag = "_hb" if row["fabric"] == "2d" else f"_hb{row['hard']}"
            found = list(folder.glob(f"{row['fabric']}_*_{bench}_{seed}{tag}/width.txt"))
            if len(found) == 1:
                row["min_width"] = found[0].read_text().split()[1]
                row["tracks"] = str(int(row["min_width"]) * int(row["layers"]))


def ratio(cand, base, key):
    """Geomean over common benchmarks (all common seeds routed) of mean(cand)/mean(base), and wins."""
    seeds = sorted({s for r in base.values() for s in r} & {s for r in cand.values() for s in r}, key=int)
    benches = sorted(b for b in base if b in cand and set(seeds) <= set(cand[b]) and set(seeds) <= set(base[b]))
    if not benches:
        return None, 0, 0, seeds, []
    per = {b: statistics.mean(float(cand[b][s][key]) for s in seeds) / statistics.mean(float(base[b][s][key]) for s in seeds)
           for b in benches}
    return statistics.geometric_mean(per.values()), sum(v < 1 for v in per.values()), len(benches), seeds, per


def area(rows, key):
    """Geomean over benchmarks of the (seed-independent) footprint or die cells."""
    out = {}
    for b, runs in rows.items():
        row = next(iter(runs.values()))
        out[b] = (int(row["grid"]) - 2) ** 2 * (int(row["layers"]) if key == "die_cells" else 1)
    return out


def main():
    out = Path(sys.argv[1])
    per_bench = "--per-bench" in sys.argv
    configs = {}
    base = (collections.defaultdict(dict), [])  # 2D rows of every file (the same 2D runs, by bench and seed)
    for fabric in FABRICS:
        for p in PLACEMENTS:
            path = out / fabric / f"results_{p}.csv"
            if path.exists():
                configs[f"{fabric}/{p}"] = load(path, "3d")
                add_min_width(configs[f"{fabric}/{p}"][0], out / fabric)
                rows, failed = load(path, "2d")
                add_min_width(rows, out / fabric)
                for bench, runs in rows.items():
                    base[0][bench].update(runs)
                base[1].extend(r for r in failed if r["seed"] not in base[0].get(r["bench"], {})
                               and r not in base[1])
    if not configs:
        sys.exit("no results")
    print(f"2D runs: {sum(len(r) for r in base[0].values())} routed, {len(base[1])} failed")
    print("\nCapacity at each run's grid (mean over benchmarks): LUTs per RAM site, LUTs per DSP site")
    for name, (rows, failed) in [("2d", base)] + list(configs.items()):
        caps = {}
        for row in [r for runs in rows.values() for r in runs.values()] + failed:
            caps[row["bench"]] = (int(row["lut_cap"]) / int(row["ram_cap"]), int(row["lut_cap"]) / int(row["dsp_cap"]))
        if caps:
            print(f"  {name:16} {statistics.mean(c[0] for c in caps.values()):6.1f} {statistics.mean(c[1] for c in caps.values()):6.1f}"
                  f"  ({len(caps)} benchmarks)")
    print(f"\n{'vs 2D (10-LUT)':18}{'CPD':>7}{'faster':>8}{'wire':>7}{'Wmin':>6}{'tracks':>7}{'footprint':>10}{'die cells':>10}  failed  seeds")
    print("  (Wmin: minimum tracks per channel per layer; tracks: Wmin times layers, per footprint cell)")
    relaxed = all("min_width" in r for runs in base[0].values() for r in runs.values()) and base[0]
    for name, (rows, failed) in configs.items():
        cpd, wins, n, seeds, _ = ratio(rows, base[0], "cpd_ns")
        wire, *_ = ratio(rows, base[0], "wirelength")
        wmin, *_ = ratio(rows, base[0], "min_width") if relaxed else (None,)
        tracks, *_ = ratio(rows, base[0], "tracks") if relaxed else (None,)
        fp = [area(rows, "fp")[b] / area(base[0], "fp")[b] for b in rows if b in base[0]]
        dc = [area(rows, "die_cells")[b] / area(base[0], "die_cells")[b] for b in rows if b in base[0]]
        fmt = lambda v: f"{v:.3f}" if v else "  -  "
        print(f"{name:18}{fmt(cpd):>7}{f'{wins}/{n}':>8}{fmt(wire):>7}{fmt(wmin):>6}{fmt(tracks):>7}"
              f"{fmt(statistics.geometric_mean(fp) if fp else None):>10}{fmt(statistics.geometric_mean(dc) if dc else None):>10}"
              f"  {len(failed):>6}  {','.join(seeds)}")
    print("\nSplit over stacked CLBs, same placement (CPD, wire):")
    for p in PLACEMENTS:
        a, b = configs.get(f"split/{p}"), configs.get(f"stack/{p}")
        if a and b:
            cpd, wins, n, seeds, _ = ratio(a[0], b[0], "cpd_ns")
            wire, *_ = ratio(a[0], b[0], "wirelength")
            if cpd:
                print(f"  {p:10} {cpd:.3f} (faster on {wins}/{n})  wire {wire:.3f}")
    for fabric in FABRICS:
        print(f"\n{fabric}: each placement over columns (CPD, wire):")
        ref = configs.get(f"{fabric}/columns")
        for p in PLACEMENTS[1:]:
            cand = configs.get(f"{fabric}/{p}")
            if ref and cand:
                cpd, wins, n, seeds, _ = ratio(cand[0], ref[0], "cpd_ns")
                wire, *_ = ratio(cand[0], ref[0], "wirelength")
                if cpd:
                    print(f"  {p:10} {cpd:.3f} (faster on {wins}/{n})  wire {wire:.3f}")
    if per_bench:
        print("\nPer benchmark: mean CPD (ns) over routed seeds [routed/total]; grid")
        benches = sorted({b for b in base[0]} | {r["bench"] for r in base[1]}
                         | {b for rows, _ in configs.values() for b in rows} | {r["bench"] for _, f in configs.values() for r in f})
        names = ["2d"] + list(configs)
        print(f"{'bench':24}" + "".join(f"{n:>17}" for n in names))
        for b in benches:
            cells = []
            for n in names:
                rows, failed = base if n == "2d" else configs[n]
                ok = rows.get(b, {})
                total = len(ok) + sum(r["bench"] == b for r in failed)
                grid = next(iter(ok.values()))["grid"] if ok else next((r["grid"] for r in failed if r["bench"] == b), "-")
                cpd = f"{statistics.mean(float(r['cpd_ns']) for r in ok.values()):.2f}" if ok else "-"
                cells.append(f"{cpd} [{len(ok)}/{total}] g{grid}")
            print(f"{b:24}" + "".join(f"{c:>17}" for c in cells))
    if "--cost" in sys.argv:
        cost(out)


def cost(out):
    """Wall time (minimum-width search plus final route) and peak memory per run, from the
    /usr/bin/time -l lines that run_hardblocks.sh TIMED=1 appends to min_width.log and run.log."""
    import re
    groups = collections.defaultdict(list)
    for run in sorted(out.glob("*/*/run.log")):
        name = run.parent.name
        config = "2d" if name.startswith("2d_") else f"{run.parent.parent.name}/" + re.search(r"_hb(\w+?)(_clk\w+)?$", name).group(1)
        seconds, rss = 0.0, 0
        for log in (run.parent / "min_width.log", run):
            if log.exists():
                text = log.read_text()
                seconds += sum(float(t) for t in re.findall(r"([\d.]+) real", text))
                rss = max([rss] + [int(b) for b in re.findall(r"(\d+)  maximum resident set size", text)])
        bench = re.search(r"_c[\d.]+_(.+)_\d+_hb", name).group(1)
        groups[config].append((bench, seconds, rss))
    print(f"\n{'cost per run':16}{'runs':>5}{'mean min':>9}{'max min':>8}{'max GB':>7}  slowest")
    for config, items in sorted(groups.items()):
        slow = max(items, key=lambda i: i[1])
        print(f"{config:16}{len(items):>5}{statistics.mean(i[1] for i in items) / 60:9.1f}{slow[1] / 60:8.1f}"
              f"{max(i[2] for i in items) / 2**30:7.2f}  {slow[0]}")
    every = [i for items in groups.values() for i in items]
    if every:
        print(f"all: {len(every)} runs, {sum(i[1] for i in every) / 3600:.1f} CPU hours (one VPR process per run)")


if __name__ == "__main__":
    main()
