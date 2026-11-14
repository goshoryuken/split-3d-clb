#!/usr/bin/env python3
"""Summarize every compare_results*.csv in a folder as a Markdown table.

For each file: rows, designs, seeds, each fabric's CLB size (N), channel width (W),
wire scale and crossing cost, how many runs routed, and the 3D over 2D critical path
delay within the file (per design, mean over the seeds both fabrics routed; then a
geometric mean over designs). A file whose 3D rows hold several settings gets one
ratio per setting. The 2D rows are the file's own baseline, which is not always the
10-LUT 2D CLB: read the N column.

Usage: ledger.py [FOLDER]   (default: this script's folder)
"""
import collections
import csv
import statistics
import sys
from pathlib import Path


def ratio(cand, base):
    """Geomean over designs of mean 3D delay / mean 2D delay, on shared seeds."""
    ratios = []
    for bench, runs in cand.items():
        seeds = sorted(set(runs) & set(base.get(bench, {})))
        if seeds:
            ratios.append(statistics.mean(runs[s] for s in seeds) / statistics.mean(base[bench][s] for s in seeds))
    if not ratios:
        return "-"
    return f"{statistics.geometric_mean(ratios):.3f} ({sum(r < 1 for r in ratios)}/{len(ratios)} faster)"


def summarize(path):
    rows = list(csv.DictReader(open(path)))
    by = collections.defaultdict(list)
    for r in rows:
        by[r["fabric"]].append(r)
    desc = []
    for fabric, rs in sorted(by.items()):
        fles = sorted({r.get("fles") or "10" for r in rs}, key=int)
        widths = sorted({int(r["chan_width"]) for r in rs})
        width = str(widths[0]) if len(widths) == 1 else f"{widths[0]}-{widths[-1]}"
        desc.append(f"{fabric}: N={'/'.join(fles)}, W={width}, scale={'/'.join(sorted({r['wire_scale'] for r in rs}))}, "
                    f"cross={'/'.join(sorted({r['crossing_ps'] for r in rs}))} ps, "
                    f"{sum(r['routed'] == 'True' for r in rs)}/{len(rs)} routed")
    base = collections.defaultdict(dict)
    settings = collections.defaultdict(lambda: collections.defaultdict(dict))
    for r in rows:
        if r["routed"] != "True":
            continue
        if r["fabric"] == "2d":
            base[r["bench"]][r["seed"]] = float(r["cpd_ns"])
        else:
            key = (r["wire_scale"], r["crossing_ps"])
            settings[key][r["bench"]][r["seed"]] = float(r["cpd_ns"])
    if len(settings) == 1:
        result = ratio(next(iter(settings.values())), base)
    else:
        result = "; ".join(f"scale {s}, cross {c}: {ratio(runs, base)}" for (s, c), runs in sorted(settings.items()))
    benches = {r["bench"] for r in rows}
    seeds = sorted({r["seed"] for r in rows}, key=int)
    return f"| `{path.name}` | {len(rows)} | {len(benches)} | {','.join(seeds)} | {'; '.join(desc)} | {result} |"


def main():
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    print("| File | Rows | Designs | Seeds | Contents per fabric | 3D/2D in file |")
    print("|---|---:|---:|---|---|---|")
    for path in sorted(folder.glob("compare_results*.csv")):
        print(summarize(path))


if __name__ == "__main__":
    main()
