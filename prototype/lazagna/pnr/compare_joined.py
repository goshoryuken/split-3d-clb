#!/usr/bin/env python3
"""Compares the joined two-layer CLB with the 2D CLB, path by path.

Both files come from join_timing.tcl and hold the same pairs of start and LUT
input, so each joined path is compared with the same path in the 2D CLB. Paths
are grouped by whether they stay on one layer or cross. The first half of the
CLB inputs and FLEs sit on layer 0, the rest on layer 1.

With FLES other than 10, the joined CLB has other paths than the 10-FLE 2D CLB,
so each group's mean is compared with the mean of all 2D paths of that kind.
Usage: compare_joined.py joined.csv flat.csv [FLES]
"""
import csv
import re
import statistics
import sys


def number(row, name):
    try:
        return float(row[name])
    except ValueError:
        return 0.0


def key(row):
    return row["kind"], re.sub(r"^layer\d/", "", row["start"]), re.sub(r"^layer\d/", "", row["mux"])


def delays(path):
    out = {}
    for row in csv.DictReader(open(path)):
        if row["mid"]:
            start = number(row, "edge") if row["kind"] == "pin" else number(row, "begin")
            out[key(row)] = (number(row, "mid") - start, number(row, "end") - number(row, "mid"))
    return out


def layer_of(kind, start, mux, fles=10):
    fle = int(re.search(r"fle_(\d+)", mux).group(1))
    target = fle >= fles // 2
    if kind == "pin":
        return int(start.replace("clb_I", "")) >= 2 * fles, target
    return int(re.search(r"fle_(\d+)", start).group(1)) >= fles // 2, target


def by_size(joined, flat, fles):
    """Group means of a CLB of another size against all 2D paths of each kind."""
    print(f"{'path':24}{'count':>7}{'3D mean':>9}{'2D mean':>9}{'ratio':>7}{'3D after':>10}{'2D after':>10}")
    groups = {}
    for pair in joined:
        source, target = layer_of(*pair, fles)
        groups.setdefault(pair[0] + (": same layer" if source == target else ": crossing"), []).append(pair)
    for name, pairs in sorted(groups.items()):
        kind = name.split(":")[0]
        flat_pairs = [p for p in flat if p[0] == kind]
        a, b = [joined[p][0] for p in pairs], [flat[p][0] for p in flat_pairs]
        c, d = [joined[p][1] for p in pairs], [flat[p][1] for p in flat_pairs]
        print(f"{name:24}{len(pairs):7d}{statistics.mean(a):9.3f}{statistics.mean(b):9.3f}{statistics.mean(a) / statistics.mean(b):7.3f}"
              f"{statistics.mean(c):10.3f}{statistics.mean(d):10.3f}")


def main():
    joined, flat = delays(sys.argv[1]), delays(sys.argv[2])
    fles = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    if fles != 10:
        by_size(joined, flat, fles)
        return
    print(f"missing from joined: {len(set(flat) - set(joined))}, from 2D: {len(set(joined) - set(flat))}")
    print(f"{'path':24}{'count':>7}{'3D mean':>9}{'2D mean':>9}{'ratio':>7}{'3D worst':>10}{'2D worst':>10}{'ratio':>7}")
    groups = {}
    for pair in set(joined) & set(flat):
        source, target = layer_of(*pair)
        name = pair[0] + (": same layer" if source == target else ": crossing")
        groups.setdefault(name, []).append(pair)
        groups.setdefault(pair[0] + ": all", []).append(pair)
    for name, pairs in sorted(groups.items()):
        a, b = [joined[p][0] for p in pairs], [flat[p][0] for p in pairs]
        print(f"{name:24}{len(pairs):7d}{statistics.mean(a):9.3f}{statistics.mean(b):9.3f}{statistics.mean(a) / statistics.mean(b):7.3f}"
              f"{max(a):10.3f}{max(b):10.3f}{max(a) / max(b):7.3f}")
    pairs = set(joined) & set(flat)
    a, b = [joined[p][1] for p in pairs], [flat[p][1] for p in pairs]
    print(f"{'after crossbar':24}{len(pairs):7d}{statistics.mean(a):9.3f}{statistics.mean(b):9.3f}{statistics.mean(a) / statistics.mean(b):7.3f}"
          f"{max(a):10.3f}{max(b):10.3f}{max(a) / max(b):7.3f}")


if __name__ == "__main__":
    main()
