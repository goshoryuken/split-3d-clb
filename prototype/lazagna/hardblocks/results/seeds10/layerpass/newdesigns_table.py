#!/usr/bin/env python3
"""Experiment C table: the layer pass on Koios designs it has never seen (run_newdesigns.sh), on
their own and together with the 7 designs of the main table. Same ratios and columns as
layerpass_table.py (per design, mean CPD over seeds routed in both files; geomean over designs).
The 7 designs' rows are the committed CSVs: pass-off and stacked as layerpass_table.py, pass-on
from k100_* and k162pin_* here.
Usage: newdesigns_table.py [OUT] [--fill]   (OUT: run_newdesigns.sh's output; default: newdesigns/)
--fill: the 7 designs' failed runs take their reruns at 200 router iterations (layerpass_table.py).
"""
import os
import sys

import layerpass_table as lt

HERE, S10 = lt.HERE, lt.S10
POINTS = [  # label, tag (used as the row label), the 7 designs' pass-off split and stacked CSVs
    ("k = 1.00 (SPICE)", "k100", "{S10}/{sub}/split/results_columns.csv", "{S10}/{sub}/stack/results_columns.csv"),
    ("k = 1.62 + pins", "k162pin", "{S10}/crossings/k162pin_{sub}/split/results_columns.csv",
     "{S10}/crossings/k162_{sub}/stack/results_columns.csv"),
]


def main():
    args = [a for a in sys.argv[1:] if a != "--fill"]
    lt.FILL = "--fill" in sys.argv[1:]
    out = args[0] if args else os.path.join(HERE, "newdesigns")
    for clock, sub in (("ideal", "ideal"), ("routed", "route")):
        print(f"== {clock} clocks" + (" (the 7 designs' failed runs rerun at 200 router iterations)" if lt.FILL else ""))
        print(lt.HEAD)
        for label, tag, off7, stack7 in POINTS:
            new = {"off": f"{out}/{tag}_{sub}/split/results_columns.csv",
                   "stack": f"{out}/{tag}_{sub}/stack/results_columns.csv",
                   "on": f"{out}/on/{tag}_{sub}/split/results_columns.csv"}
            if not all(os.path.exists(p) for p in new.values()):
                continue
            old = {"off": off7.format(S10=S10, sub=sub), "stack": stack7.format(S10=S10, sub=sub),
                   "on": f"{HERE}/{tag}_{sub}/split/results_columns.csv"}
            both = {k: [old[k], new[k]] for k in new}
            for name, files in (("new", new), ("all", both)):
                lt.row(f"{tag} {name}: off / stacked", files["off"], files["stack"])
                lt.row(f"{tag} {name}: on / stacked", files["on"], files["stack"])
                lt.row(f"{tag} {name}: on / off", files["on"], files["off"])
            for kind in ("off", "stack", "on"):
                failed = lt.load(new[kind])[1]
                if failed:
                    print(f"{'':30}new designs, {kind} runs that failed: {', '.join(failed)}")
        print()


if __name__ == "__main__":
    main()
