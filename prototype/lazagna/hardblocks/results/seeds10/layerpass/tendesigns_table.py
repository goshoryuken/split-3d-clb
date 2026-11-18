#!/usr/bin/env python3
"""Experiment E tables: all 10 designs (the 7 and experiment C's 3) at every setting, and the 3 alone.
Same ratios and columns as layerpass_table.py (per design, mean CPD over the seeds routed in both
files; geomean over designs). The 7 designs' rows are the committed CSVs (pass-off and stacked as
layerpass_table.py; pass-on from k<NNN>_* here; 2D rows of ../route and ../ideal; ../ablation;
../equal_tracks). The 3 designs' rows are in newdesigns/: C (run_newdesigns.sh: k100, k162pin) and
E (run_newdesigns_e.sh: k162, k224, k272, k300, 2d, abl, eq). At k = 1.62 the 3 designs' stacked runs
are C's (newdesigns/k162pin_*/stack, the same delay set 3d10stack_w100_k162), just as the 7 designs'
k = 1.62 + pins rows use crossings/k162_*/stack.
Usage: tendesigns_table.py [--fill]   (--fill: failed runs take their reruns at 200 router iterations
where iter200/ has one, as layerpass_table.py)
"""
import os
import sys

import layerpass_table as lt

HERE, S10 = lt.HERE, lt.S10
N = os.path.join(HERE, "newdesigns")
NEW_STACK = {"k100": "k100", "k162": "k162pin", "k162pin": "k162pin", "k224": "k224", "k272": "k272", "k300": "k300"}


def path(p):
    return p[0] if isinstance(p, tuple) else p


def rows(old, new, pairs):
    """pairs: (label, candidate key, base key); prints the 7, the 3 new designs, then all 10."""
    missing = [path(p) for p in new.values() if not os.path.exists(path(p))]
    if missing:
        print(f"{'':30}not run yet: {', '.join(os.path.relpath(m, HERE) for m in missing)}")
        return
    for name, files in (("the 7", old), ("new 3", new), ("all 10", {k: [old[k], new[k]] for k in new})):
        for label, cand, base in pairs:
            lt.row(f"{name}: {label}", files[cand], files[base])
    for key, p in new.items():
        failed = lt.load(p)[1]
        if failed:
            print(f"{'':30}new designs, {key} runs that failed: {', '.join(failed)}")


def table(sub):
    print(lt.HEAD)
    trio = (("off / stacked", "off", "stack"), ("on / stacked", "on", "stack"), ("on / off", "on", "off"))
    for label, tag, off7, stack7 in lt.POINTS:
        print(f"-- {label}")
        old = {"off": off7.format(S10=S10, sub=sub), "stack": stack7.format(S10=S10, sub=sub),
               "on": f"{HERE}/{tag}_{sub}/split/results_columns.csv"}
        new = {"off": f"{N}/{tag}_{sub}/split/results_columns.csv",
               "stack": f"{N}/{NEW_STACK[tag]}_{sub}/stack/results_columns.csv",
               "on": f"{N}/on/{tag}_{sub}/split/results_columns.csv"}
        rows(old, new, trio)
    old = {"2d": (f"{S10}/{sub}/split/results_columns.csv", "2d"), "off": f"{S10}/{sub}/split/results_columns.csv",
           "stack": f"{S10}/{sub}/stack/results_columns.csv", "on": f"{HERE}/k100_{sub}/split/results_columns.csv",
           "abl": f"{S10}/ablation/strict_{sub}/results_columns.csv",
           "eq": f"{S10}/equal_tracks/eq_{sub}/results_columns.csv"}
    new = {"2d": (f"{N}/2d_{sub}/split/results_columns.csv", "2d"), "off": f"{N}/k100_{sub}/split/results_columns.csv",
           "stack": f"{N}/k100_{sub}/stack/results_columns.csv", "on": f"{N}/on/k100_{sub}/split/results_columns.csv",
           "abl": f"{N}/abl_{sub}/split/results_columns.csv", "eq": f"{N}/eq_{sub}/stack/results_columns.csv"}
    print("-- k = 1.00 against the 2D fabric (10-LUT CLBs)")
    keys = ("2d", "off", "stack", "on")
    rows({k: old[k] for k in keys}, {k: new[k] for k in keys},
         (("off / 2D", "off", "2d"), ("stacked / 2D", "stack", "2d"), ("on / 2D", "on", "2d")))
    print("-- k = 1.00 ablation: split CLB on stacked's exact routing (strict)")
    keys = ("2d", "off", "stack", "abl")
    rows({k: old[k] for k in keys}, {k: new[k] for k in keys},
         (("strict / stacked", "abl", "stack"), ("off / strict", "off", "abl"), ("strict / 2D", "abl", "2d")))
    print("-- k = 1.00 equal tracks: stacked at the split's track count (stacked eq)")
    keys = ("off", "stack", "on", "eq")
    rows({k: old[k] for k in keys}, {k: new[k] for k in keys},
         (("stacked eq / stacked", "eq", "stack"), ("off / stacked eq", "off", "eq"), ("on / stacked eq", "on", "eq")))


def main():
    lt.FILL = "--fill" in sys.argv[1:]
    for clock, sub in (("ideal", "ideal"), ("routed", "route")):
        print(f"== {clock} clocks" + (" (failed runs rerun at 200 router iterations, --fill)" if lt.FILL else ""))
        table(sub)
        print()


if __name__ == "__main__":
    main()
