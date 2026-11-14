#!/usr/bin/env python3
"""Compares crossbar delays from report_paths.tcl between two routed blocks.

Prints, for each kind of path, the mean and worst delay in each block and their
ratio. "Crossbar" runs from the start of the path to the crossbar mux output.
For CLB inputs it is shown with and without the delay of the wire-loaded pin
driver, which the tool reports separately as the drive adjustment.
Usage: compare_paths.py half.csv full.csv
"""
import csv
import statistics
import sys


def number(row, name):
    try:
        return float(row[name])
    except ValueError:
        return 0.0


def measures(rows, kind):
    rows = [r for r in rows if r["kind"] == kind and r["begin"]]
    with_mux = [r for r in rows if r["mid"]]
    return {
        "crossbar": [number(r, "mid") - number(r, "begin") for r in with_mux],
        "crossbar + pin driver": [number(r, "mid") - number(r, "edge") for r in with_mux] if kind == "pin" else [],
        "after crossbar": [number(r, "end") - number(r, "mid") for r in with_mux],
        "output path": [number(r, "end") - number(r, "begin") for r in rows if not r["mid"]],
    }


def main():
    half, full = [list(csv.DictReader(open(path))) for path in sys.argv[1:3]]
    print(f"{'path':34}{'half mean':>10}{'2D mean':>9}{'ratio':>7}{'half worst':>12}{'2D worst':>10}{'ratio':>7}")
    for kind in ("pin", "feedback", "crossing", "output"):
        a, b = measures(half, kind), measures(full, kind)
        for name in a:
            if a[name] and b[name]:
                mean_a, mean_b = statistics.mean(a[name]), statistics.mean(b[name])
                top_a, top_b = max(a[name]), max(b[name])
                print(f"{kind + ': ' + name:34}{mean_a:10.3f}{mean_b:9.3f}{mean_a / mean_b:7.3f}"
                      f"{top_a:12.3f}{top_b:10.3f}{top_a / top_b:7.3f}")
            elif a[name]:
                print(f"{kind + ': ' + name:34}{statistics.mean(a[name]):10.3f}{'-':>9}{'':7}{max(a[name]):12.3f}")


if __name__ == "__main__":
    main()
