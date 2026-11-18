#!/usr/bin/env python3
"""Router iterations of every run in run_layerpass.sh / run_failed.sh outputs (the last row of
VPR's router iteration table in each run.log), and whether the run routed.
Usage: router_iterations.py OUT...   (prints one line per run, then a summary per OUT)"""
import glob
import re
import sys

ROW = re.compile(r"^\s{0,4}(\d+)\s+[\d.]+\s+[\d.e+]+\s", re.M)
for out in sys.argv[1:]:
    routed, failed = [], []
    for log in sorted(glob.glob(f"{out}/**/run.log", recursive=True)):
        text = open(log).read()
        rows = ROW.findall(text)
        if not rows:
            continue
        name = log[len(out):].lstrip("/").rsplit("/", 1)[0]
        ok = "Routing failed" not in text and "Final critical path delay" in text
        (routed if ok else failed).append((int(rows[-1]), name))
        print(f"{int(rows[-1]):4d}  {'routed' if ok else 'FAILED'}  {name}")
    its = [i for i, _ in routed]
    print(f"# {out}: {len(routed)} routed in {min(its)}-{max(its)} iterations; "
          f"{len(failed)} failed: " + ", ".join(f"{n} ({i})" for i, n in failed))
