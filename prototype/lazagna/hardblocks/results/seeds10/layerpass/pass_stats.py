#!/usr/bin/env python3
"""What layer_pass.py did in each run of a run_layerpass.sh sweep (from each run's layer_pass.log).

Writes OUT/layer_pass_stats.tsv (one row per run) and prints per set and design the mean share of
FLEs moved, the weighted crossing cost after over before, and the packer-critical (criticality
>= 0.9) connections that cross layers, before -> after, inside CLBs and between CLBs.
Usage: pass_stats.py OUT [TSV]
"""
import collections
import re
import statistics as st
import sys
from pathlib import Path

NAME = re.compile(r"_c[\d.]+_(.+)_(\d+)_hb")
out = Path(sys.argv[1])
rows = []
for log in sorted(out.glob("*/split/*_lp/layer_pass.log")):
    text = log.read_text()
    cost = re.search(r"weighted crossing cost ([\d.]+) -> ([\d.]+); (\d+) FLE moves, (\d+) of (\d+) CLBs rewritten"
                     r" \((\d+) left as packed", text)
    crit = re.search(r"criticality >= 0.9 crossing layers: in-CLB (\d+) -> (\d+), between CLBs (\d+) -> (\d+)", text)
    if not cost or not crit:
        continue
    bench, seed = NAME.search(log.parent.name).groups()
    rows.append(dict(set=log.parent.parent.parent.name, bench=bench, seed=seed,
                     cost_before=float(cost[1]), cost_after=float(cost[2]), moves=int(cost[3]),
                     clbs_rewritten=int(cost[4]), clbs=int(cost[5]), clbs_as_packed=int(cost[6]),
                     crit_in_before=int(crit[1]), crit_in_after=int(crit[2]),
                     crit_between_before=int(crit[3]), crit_between_after=int(crit[4])))
tsv = Path(sys.argv[2]) if len(sys.argv) > 2 else out / "layer_pass_stats.tsv"
with open(tsv, "w") as handle:
    handle.write("\t".join(rows[0]) + "\n")
    for r in rows:
        handle.write("\t".join(str(v) for v in r.values()) + "\n")
groups = collections.defaultdict(list)
for r in rows:
    groups[(r["set"], r["bench"])].append(r)
print(f"{'set':15}{'design':24}{'runs':>5}{'cost after/before':>19}{'FLE moves/CLB':>15}{'as packed':>10}"
      f"{'crit>=0.9 in-CLB':>19}{'between CLBs':>15}")
for (s, b), rs in sorted(groups.items()):
    m = lambda k: st.mean(r[k] for r in rs)
    print(f"{s:15}{b:24}{len(rs):5}{st.mean(r['cost_after'] / r['cost_before'] for r in rs):19.3f}"
          f"{st.mean(r['moves'] / r['clbs'] for r in rs):15.2f}{m('clbs_as_packed'):10.1f}"
          f"{m('crit_in_before'):9.0f} -> {m('crit_in_after'):4.0f}{m('crit_between_before'):8.0f} -> {m('crit_between_after'):4.0f}")
