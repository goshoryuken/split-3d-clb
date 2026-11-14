#!/usr/bin/env python3
"""Delay sets for VPR with the CLB's layer crossing measured in layout instead of in SPICE.

From a joined 20-LUT layout (pnr/clb_paths_*.csv), r = (crossing - same layer) / same layer,
each the mean FLE output to crossbar mux output of a feedback path (pnr/compare_joined.py
groups). In SPICE units the crossing is r times the matching SPICE path:
  low:  r * xbar_fb            the crossbar path alone
  high: r * (ble + xbar_fb)    also the whole FLE output stage, whose driver the layout path holds
Routing crossings keep SPICE's value with a driver and receiver, since no routing crossing was
laid out with the bond as a via. The rest comes from the SPICE direct set (FLE output driver
also loaded by the crossing driver).
Usage: layout_delays.py DELAYS.json CLB_PATHS.csv FABRIC OUT.json
Writes every set of DELAYS.json plus FABRIC_layout_low and FABRIC_layout_high to OUT.json.
"""
import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pnr"))
from compare_joined import delays, layer_of  # noqa: E402


def feedback_means(path, fles=20):
    same, cross = [], []
    for key, (to_mux, _) in delays(path).items():
        if key[0] == "feedback":
            source, target = layer_of(*key, fles)
            (same if source == target else cross).append(to_mux)
    return statistics.mean(same), statistics.mean(cross)


def main():
    source, paths, fabric, output = sys.argv[1:]
    sets = json.loads(Path(source).read_text())
    same, cross = feedback_means(paths)
    r = (cross - same) / same
    base = sets[fabric + "_direct"]
    route = sets[fabric]["route_crossing"]
    for name, path_ps in (("low", base["xbar_fb"]), ("high", base["ble"] + base["xbar_fb"])):
        sets[f"{fabric}_layout_{name}"] = dict(
            base, clb_crossing=round(r * path_ps, 2), route_crossing=route,
            crossing_over_l4=round(route / base["l4"], 3), layout_paths=Path(paths).name, layout_ratio=round(r, 4))
        print(f"{fabric}_layout_{name}: same layer {same:.3f} ns, crossing {cross:.3f} ns, r {r:.3f}, "
              f"clb_crossing {r * path_ps:.1f} ps, route_crossing {route} ps")
    Path(output).write_text(json.dumps(sets, indent=1) + "\n")


if __name__ == "__main__":
    main()
