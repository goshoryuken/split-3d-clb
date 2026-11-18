#!/usr/bin/env python3
"""Layer crossings on the critical paths of runs kept with --slim (report_timing.setup.rpt + arch.xml).

Per run, Path 1 and the mean over the report's top paths (10), from the launching element on:
  in-CLB   connections inside one CLB (no routing node between two atom pins) whose CLB-internal
           delay includes the crossbar's layer_crossing_delay: delay > out mux + feedback +
           half the crossing (all three read from that run's arch.xml; stacked has none);
  routing  layer changes along a connection's routing nodes (OPIN, CHAN, IPIN), as hb_paths.py.
With LABEL=GLOB::CSV it also checks each run's CPD against that results CSV (same design and
seed), so the reports are known to be the runs behind the committed rows, and leaves out runs
with no routed row there (VPR still writes a report when routing fails).
Without a run.log the report's Path 1 slack is checked instead (to its 3 decimals), and without an
arch.xml the one given after a second :: is used (the same fabric's).
Usage: path_xings.py LABEL=GLOB[::CSV[::ARCH]] ...   (GLOB matches run folders)
"""
import collections
import csv
import glob
import re
import statistics as st
import sys
from pathlib import Path

ROW = re.compile(r"^(.*?)\s+(-?[\d.]+)\s+(-?[\d.]+)$")
NODE_LAYER = re.compile(r"\((\d+),(\d+),(\d+)\)?")
ATOM = re.compile(r"^(\S+)\.(\w+)\[(\d+)\] \(([^ ]+) at ")
NAME = re.compile(r"_c[\d.]+_(.+)_(\d+)_hb")


def threshold(arch):
    xml = arch.read_text()
    cross = re.search(r'layer_crossing_delay="([^"]+)"', xml)
    if not cross:
        return None
    mux = float(re.search(r'<delay_constant max="([^"]+)" in_port="lut6.out" out_port="ble6.out"/>', xml).group(1))
    fb = float(re.search(r'<delay_constant max="([^"]+)" in_port="fle\[\d+:0\]\.out" out_port="fle\[\d+:\d+\]\.in"/>',
                         xml).group(1))
    return (mux + fb + float(cross.group(1)) / 2) * 1e9  # ns, as the report


def counts(block, limit):
    arrival = block.split("data arrival time", 1)[0]
    rows = []
    for line in arrival.splitlines():
        m = ROW.match(line.strip())
        if m and not line.startswith(("clock", "Point")):
            rows.append((m.group(1).strip(), float(m.group(2))))
    start = next(i for i, (t, _) in enumerate(rows) if "[clock-to-output]" in t
                 or "(.input" in t and "clk" not in t.split()[0])
    inside = routing = 0
    nodes, delay, open_src = [], 0.0, False
    for text, incr in rows[start:]:
        if text.startswith("|"):
            if open_src and not text.startswith("| (primitive"):
                nodes.append(text)
                delay += incr
            continue
        m = ATOM.match(text)
        if not m:
            continue
        is_src = m.group(2) in ("out", "Q") or "[clock-to-output]" in text or m.group(4) == ".input"
        if open_src and not is_src:
            routed = [t for t in nodes if t.startswith(("| (OPIN", "| (IPIN", "| (CHAN"))]
            if not routed:
                inside += limit is not None and delay > limit
            else:
                last = None
                for t in routed:
                    layers = [int(z) for _, _, z in NODE_LAYER.findall(t)]
                    if not layers:
                        continue
                    if t.startswith("| (OPIN"):
                        last = layers[0]
                    elif last is not None and layers[0] != last:
                        routing += 1
                    last = layers[-1]
            open_src = False
        if is_src:
            open_src, nodes, delay = True, [], 0.0
    return inside, routing


def run_counts(folder, arch=None):
    text = (folder / "report_timing.setup.rpt").read_text()
    limit = threshold(folder / "arch.xml" if (folder / "arch.xml").exists() else arch)
    blocks = re.split(r"\n#Path \d+\n", text)[1:]
    per = [counts(b, limit) for b in blocks]
    return per[0], (st.mean(p[0] for p in per), st.mean(p[1] for p in per))


def main():
    print(f"{'':34}{'runs':>5}{'path 1: in-CLB':>16}{'routing':>9}{'total':>7}{'top 10: in-CLB':>16}{'routing':>9}{'total':>7}"
          f"   CPD = CSV row")
    for arg in sys.argv[1:]:
        label, rest = arg.split("=", 1)
        pattern, _, table = rest.partition("::")
        table, _, arch = table.partition("::")
        arch = Path(arch) if arch else None
        check = {}
        if table:
            for r in csv.DictReader(open(table)):
                if r["fabric"] == "3d" and r["routed"] == "True":
                    check[(r["bench"], r["seed"])] = r["cpd_ns"]
        one, ten, matched, mismatched, skipped = [], [], 0, 0, 0
        for folder in sorted(map(Path, glob.glob(pattern))):
            log, report = folder / "run.log", folder / "report_timing.setup.rpt"
            if not report.exists():
                continue
            if log.exists():
                cpd = re.search(r"Final critical path delay \(least slack\): ([\d.]+) ns", log.read_text())
                if not cpd:
                    continue
                same = lambda row: row == cpd.group(1)
            else:  # only the report was kept: its Path 1 slack, 3 decimals
                slack = -float(re.search(r"slack \(\w+\)\s+(-?[\d.]+)", report.read_text()).group(1))
                same = lambda row: row is not None and abs(float(row) - slack) < 0.0006
            key = NAME.search(folder.name).groups()
            if table and key not in check:  # did not route: not in the comparison either
                skipped += 1
                continue
            if table:
                matched += same(check.get(key))
                mismatched += not same(check.get(key))
            p1, p10 = run_counts(folder, arch)
            one.append(p1)
            ten.append(p10)
        if not one:
            print(f"{label:34} no runs")
            continue
        m = lambda xs, i: st.mean(x[i] for x in xs)
        note = f"{matched} of {matched + mismatched}" if table else "-"
        note += f" ({skipped} not routed, left out)" if skipped else ""
        print(f"{label:34}{len(one):5}{m(one, 0):16.2f}{m(one, 1):9.2f}{m(one, 0) + m(one, 1):7.2f}"
              f"{m(ten, 0):16.2f}{m(ten, 1):9.2f}{m(ten, 0) + m(ten, 1):7.2f}   {note}")


if __name__ == "__main__":
    main()
