#!/usr/bin/env python3
"""The laid-out in-CLB crossing, stage by stage, from the Tempus path reports and path CSVs.

1. Mean crossing over same layer (the "+760 ps"), overall and per sending FLE, from the joined
   path CSVs (compare_joined.py's paths: FLE output mux out to crossbar mux out).
2. The worst crossing path (crossing_path_*.txt, Tempus report_timing of the joined CLB) split into
   stages: each cell's delay plus the wire delay into it, with the load it drives and its input
   slew, from the FLE's output driver to the far crossbar mux's input. Each stage is labelled as
   the FLE output driver (shared with same-layer paths), a buffer Innovus inserted (FE_*), the
   crossing driver (xd_*), the receiver (xr_*), or the far crossbar mux.
   Where a path CSV has the mux_in column (retime_joined.sh), the means are also split at the
   crossbar mux's first pin: the part before the mux and the mux itself.
3. SPICE beside Tempus on pnr_local20c's worst crossing path, and SPICE one change at a time, from
   ../spice/crossing_stages_3d20own_w100_tt.json (crossing_stages.py).
Its output is the body of crossing_stages_results.txt (below a hand-written header).
Usage: crossing_stages_layout.py [PNR_DIR]   (default: this folder)
"""
import csv
import json
import re
import statistics as st
import sys
from pathlib import Path

PNR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
LAYOUTS = [("driver + receiver (pnr_local20c)", "center"),
           ("bond as a via, driver after the FLE (pnr_local20g)", "center_direct"),
           ("bond as a via, driver inside the FLE (pnr_local20i, tap)", "center_tap"),
           # run_crossing_fix.sh, listed once their files are copied here
           ("driver + receiver, real bond loads (pnr_local20s)", "center_loaded"),
           ("same, no inserted buffers on crossing nets (pnr_local20t)", "center_nobuf"),
           ("real bond loads + bond-port timing budgets (pnr_local20u)", "center_budget")]


def increments(csv_path, fles=20):
    paths, pins = {}, []
    for row in csv.DictReader(open(csv_path)):
        if row["kind"] == "pin" and row["mid"]:
            pins.append(float(row["mid"]) - float(row["edge"]))
        if row["kind"] != "feedback" or not row["mid"]:
            continue
        src = int(re.search(r"fle_(\d+)", row["start"]).group(1))
        dst = int(re.search(r"fle_(\d+)", row["mux"]).group(1))
        cross = (src >= fles // 2) != (dst >= fles // 2)
        paths.setdefault(src, {}).setdefault(cross, []).append(float(row["mid"]) - float(row["begin"]))
    same = st.mean(v for p in paths.values() for v in p[False])
    cross = st.mean(v for p in paths.values() for v in p[True])
    per_fle = [st.mean(p[True]) - st.mean(p[False]) for _, p in sorted(paths.items())]
    return same, cross, per_fle, st.mean(pins)


def mux_split(csv_path, fles=20):
    """Mean crossing and same-layer path, split at the crossbar mux's first pin (mux_in column):
    {cross: (before, inside), False: ...}, ns, or None for a CSV without that column."""
    parts = {True: [], False: []}
    for row in csv.DictReader(open(csv_path)):
        if row["kind"] != "feedback" or not row["mid"] or not row.get("mux_in"):
            continue
        src = int(re.search(r"fle_(\d+)", row["start"]).group(1))
        dst = int(re.search(r"fle_(\d+)", row["mux"]).group(1))
        cross = (src >= fles // 2) != (dst >= fles // 2)
        begin, mux_in, mid = float(row["begin"]), float(row["mux_in"]), float(row["mid"])
        parts[cross].append((mux_in - begin, mid - mux_in))
    if not parts[True] or not parts[False]:
        return None
    return {k: (st.mean(b for b, _ in v), st.mean(i for _, i in v), len(v)) for k, v in parts.items()}


def report_rows(report):
    """(instance, cell, fanout, load pF, slew ns, delay ns, arrival ns, is_arc) for path 1."""
    rows = []
    for line in report.read_text().splitlines():
        if line.startswith("Path 2"):
            break
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 6 or not re.match(r"^[0-9.]+$", parts[-1]):
            continue
        numbers = parts[-1].split() if " " in parts[-1] else None
        tail = " ".join(parts[3:]).split()
        if len(tail) < 5:
            continue
        inst, cell, arc = parts[0], parts[1], parts[2]
        fanout, load, slew, delay, arrival = tail[-5:]
        rows.append((inst, cell, arc, fanout, load, slew, delay, float(arrival)))
    return rows


def label(inst):
    if "/FE_" in inst or inst.split("/")[1].startswith("FE_"):
        return "inserted buffer (Innovus)"
    if "/xd_" in inst or "/buffer" in inst and "direct_interc" not in inst and "mux_" not in inst:
        return "crossing driver"
    if "/xr_" in inst:
        return "receiver"
    if "direct_interc_0_" in inst and "fle_mode" not in inst:
        return "FLE output driver"
    if "/mux_fle_" in inst:
        return "far crossbar mux"
    return "other"


def stages(report):
    """Cells from the FLE's output driver to the far crossbar mux's first cell, with wire delay into each."""
    rows = report_rows(report)
    out, wire_in = [], 0.0
    started = False
    for inst, cell, arc, fanout, load, slew, delay, arrival in rows:
        is_arc = "->" in arc
        if not is_arc:
            # an input pin row: the wire delay into this cell, the driving net's fanout and load
            wire_in = float(delay) if delay != "-" else 0.0
            net = (fanout, load, slew)
            continue
        if not started and ("direct_interc_0_" in inst and "fle_mode" not in inst or "/buffer" in inst
                            or "FE_OCPC" in inst and "fle_0" in inst and "fle_out" not in inst):
            started = True
        if not started:
            continue
        kind = label(inst)
        out.append(dict(kind=kind, cell=cell, delay_ps=round(float(delay) * 1e3), wire_in_ps=round(wire_in * 1e3),
                        load_pf=float(load), slew_in_ns=float(net[2]), arrival=arrival))
        if kind == "far crossbar mux":
            break
    return out


def main():
    print("Laid-out in-CLB crossing (Tempus, sky130 standard cells, both layers joined, 2 ns clock).")
    print("Mean of 1,200 paths each, FLE output mux out to crossbar mux out (compare_joined.py's paths);")
    print("pins: mean of the 4,800 CLB input pin to crossbar mux out paths, for what a change costs elsewhere.\n")
    print(f"{'layout':58}{'same':>7}{'cross':>7}{'+ns':>7}  per sending FLE: min / median / max  {'pins':>5}")
    layouts = [(n, t) for n, t in LAYOUTS if (PNR / f"clb_paths_local20_{t}_2ns.csv").exists()]
    for name, tag in layouts:
        same, cross, per, pin = increments(PNR / f"clb_paths_local20_{tag}_2ns.csv")
        print(f"{name:58}{same:7.3f}{cross:7.3f}{cross - same:7.3f}  {min(per):.3f} / {st.median(per):.3f} / {max(per):.3f}"
              f"{pin:20.3f}")
    split = [(n, t, mux_split(PNR / f"clb_paths_local20_{t}_2ns.csv")) for n, t in layouts]
    if any(s for _, _, s in split):
        print("\nThe same means split at the crossbar mux's first pin (mux_in, retime_joined.sh), ns:")
        print(f"{'layout':58}{'before the mux':>22}{'inside the mux':>22}")
        print(f"{'':58}{'same  cross     +':>22}{'same  cross     +':>22}")
        for name, _, s in split:
            if s:
                (cb, ci, _), (sb, si, _) = s[True], s[False]
                print(f"{name:58}{sb:6.3f}{cb:7.3f}{cb - sb:7.3f}  {si:6.3f}{ci:7.3f}{ci - si:7.3f}")
    for name, tag in layouts:
        if not (PNR / f"crossing_path_local20_{tag}.txt").exists():
            continue
        print(f"\n== {name}: worst crossing path, crossing_path_local20_{tag}.txt (FLE 0 to layer 1)")
        print(f"{'stage':28}{'cell':14}{'wire in':>8}{'cell':>7}{'drives pF':>11}{'slew in':>9}")
        total = 0
        for s in stages(PNR / f"crossing_path_local20_{tag}.txt"):
            if s["kind"] == "far crossbar mux":
                print(f"{'far crossbar mux input':28}{s['cell']:14}{s['wire_in_ps']:8d}{'':>7}{'':>11}{s['slew_in_ns'] * 1e3:8.0f}p")
                total += s["wire_in_ps"]
                break
            print(f"{s['kind']:28}{s['cell']:14}{s['wire_in_ps']:8d}{s['delay_ps']:7d}{s['load_pf']:11.3f}{s['slew_in_ns'] * 1e3:8.0f}p")
            total += s["wire_in_ps"] + s["delay_ps"]
        print(f"{'sum, ps':28}{'':14}{total:15d}")
    spice(PNR.parent / "spice/crossing_stages_3d20own_w100_tt.json", PNR / "crossing_path_local20_center.txt")


# The worst crossing path of pnr_local20c in groups whose ends are the same nodes in both: Tempus
# kinds (from stages()) against crossing_stages.py's SPICE stages.
GROUPS = [("inserted buffer before the driver", ["inserted buffer (Innovus)#0"], ["s_ins1"]),
          ("crossing driver (INVX1 -> INVX2)", ["crossing driver"], ["s_driver"]),
          ("pad wire, bond, receiver, its net,", ["receiver", "inserted buffer (Innovus)#1"],
           ["s_padwire", "s_bond", "s_receiver", "s_far_net", "s_ins2"]),
          ("  and the inserted buffer after it", [], [])]


def spice(json_path, report):
    """SPICE (crossing_stages.py) beside Tempus on the same path, and SPICE one change at a time."""
    if not json_path.exists() or not report.exists():
        return
    v = json.loads(json_path.read_text())["variants"]
    print(f"\n== SPICE beside Tempus: the same worst crossing path, {json_path.name}")
    print("SPICE 'cells+ins' has the layout's cells (INVX1 -> INVX2 driver, BUFX16_HS receiver and FLE")
    print("driver, the two inserted buffers) and its loads; 'base' is make_spice.py's model (339 ps).")
    print("Stages from the FLE output net to the far crossbar mux's input; ps, worst edge in SPICE.")
    tempus, seen = {}, {}
    for s in stages(report):
        if s["kind"] == "far crossbar mux":
            break
        key = s["kind"]
        if key == "inserted buffer (Innovus)":
            key += f"#{seen.setdefault(key, 0)}"
            seen["inserted buffer (Innovus)"] += 1
        tempus[key] = tempus.get(key, 0) + s["wire_in_ps"] + s["delay_ps"]
    print(f"{'stage':38}{'Tempus':>8}{'SPICE cells+ins':>17}{'SPICE base':>12}")
    sums = [0, 0.0, 0.0]
    for name, tk, sk in GROUPS:
        if not tk:
            print(name)
            continue
        t = sum(tempus.get(k, 0) for k in tk)
        c = sum(v["cells+ins"]["stages_worst_edge"].get(k, 0) for k in sk)
        b = sum(v["base"]["stages_worst_edge"].get(k, 0) for k in sk)
        sums = [sums[0] + t, sums[1] + c, sums[2] + b]
        print(f"{name:38}{t:8d}{c:17.0f}{b:12.0f}")
    print(f"{'sum':38}{sums[0]:8d}{sums[1]:17.0f}{sums[2]:12.0f}")
    print(f"{'SPICE over Tempus':38}{'':8}{sums[1] / sums[0]:17.2f}")
    print("\nSPICE, one change at a time (crossing minus same layer, worst edges, as make_spice.py):")
    def load(name, stage):
        return v[name]["loads"][stage].get("drives_fF", v[name]["loads"][stage].get("total_fF"))
    notes = {"base": f"make_spice.py's model: bond net {load('base', 's_driver'):.0f} fF, both crossbar nets "
                     f"{load('base', 's_far_net'):.0f} fF",
             "bondnet": f"the layout's bond net ({load('bondnet', 's_driver'):.0f} fF), crossing driver sized for it",
             "farnet": f"+ the receiver's net as laid out ({load('farnet', 's_receiver'):.0f} fF), receiver sized for it",
             "ownnet": f"+ the FLE output net as laid out ({load('ownnet', 'fle_driver'):.0f} fF), FLE driver sized for it",
             "cells": "the same loads with the layout's cells instead of sized chains",
             "cells+ins": "+ the two buffers Innovus inserted, with their loads"}
    print(f"{'variant':11}{'cross':>8}{'same':>8}{'crossing':>10}  what changed")
    for name, note in notes.items():
        if "clb_crossing" in v.get(name, {}):
            r = v[name]
            print(f"{name:11}{r['cross']:8.1f}{r['same']:8.1f}{r['clb_crossing']:10.1f}  {note}")


if __name__ == "__main__":
    main()
