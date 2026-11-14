#!/usr/bin/env python3
"""Picks a typical CLB tile of a fabric and lists its routing modules.

Wires start at different tiles, so routing varies a little from tile to tile.
This takes the tiles with CLBs on all four sides and picks the one closest to
their median size. It prints one "block" line per routing module, and one
"scale" line per layer: the mean size over those tiles divided by the size of
the tile picked. Size is counted in routing mux inputs.
Usage: tile_blocks.py <OpenFPGA Verilog folder>
"""
import pathlib
import re
import statistics
import sys

ROUTING = re.compile(r"^\s*((?:sb|cbx|cby)_\w+)\s+(sb|cbx|cby)_(\d+)_(\d+)_(\d+)_\s*\(", re.M)
CLB = re.compile(r"^\s*grid_clb\s+grid_clb_\d+_(\d+)_(\d+)_\s*\(", re.M)
MUX = re.compile(r"^\s*mux\w*?_size(\d+)\s+\S+\s*\(", re.M)


def main():
    source = pathlib.Path(sys.argv[1])
    top = (source / "fpga_top.v").read_text()
    blocks = {(kind, int(z), int(x), int(y)): module for module, kind, z, x, y in ROUTING.findall(top)}
    clbs = {(int(x), int(y)) for x, y in CLB.findall(top)}
    layers = sorted({key[1] for key in blocks})
    sizes = {}

    def size(key):
        module = blocks.get(key)
        if module is None:
            return 0
        if module not in sizes:
            sizes[module] = sum(map(int, MUX.findall((source / "routing" / f"{module}.v").read_text())))
        return sizes[module]

    def tile(x, y, z):
        return [size((kind, z, x, y)) for kind in ("sb", "cbx", "cby")]

    inner = [(x, y) for x, y in sorted(clbs)
             if {(x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)} <= clbs
             and all(min(tile(x, y, z)) > 0 for z in layers)]
    totals = {t: sum(sum(tile(*t, z)) for z in layers) for t in inner}
    middle = statistics.median(totals.values())
    x, y = min(inner, key=lambda t: abs(totals[t] - middle))
    print(f"tile {x} {y} out of {len(inner)}")
    for z in layers:
        for kind in ("sb", "cbx", "cby"):
            print(f"block {z} {kind} {blocks[(kind, z, x, y)]} {size((kind, z, x, y))}")
        mean = statistics.mean(sum(tile(*t, z)) for t in inner)
        print(f"scale {z} {mean / sum(tile(x, y, z)):.4f}")


if __name__ == "__main__":
    main()
