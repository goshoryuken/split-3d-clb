#!/usr/bin/env python3
"""Adds a CLB and its routing into a whole tile, and compares it with the 2D tile.

Reads the result lines of run_tile.sh. A layer's tile is its CLB plus one switch
block and two connection blocks, each scaled to the typical tile. The 3D tile's
footprint is its larger layer. Wire spans and tracks that keep the same physical
wire length and track pitch follow from the tile's width.
Usage: tile_area.py <results> <2D CLB core> <layer 0 CLB core> <layer 1 CLB core>
"""
import math
import re
import sys


def main():
    results, flat_clb, *clbs = sys.argv[1:]
    routing, scales = {}, {}
    for line in open(results):
        scale = re.match(r"(\w+) scale (\d) ([\d.]+)", line)
        block = re.match(r"(\w+) (\d) \w+ \S+ .*core=([\d.]+)", line)
        if scale:
            scales[scale.group(1), int(scale.group(2))] = float(scale.group(3))
        elif block:
            key = block.group(1), int(block.group(2))
            routing[key] = routing.get(key, 0) + float(block.group(3))
    flat = float(flat_clb) + routing["2d", 0] * scales["2d", 0]
    tiles = [float(clb) + routing["3d", z] * scales["3d", z] for z, clb in enumerate(clbs)]
    area = max(tiles) / flat
    width = math.sqrt(area)
    print(f"2D tile {flat:.0f}: routing {routing['2d', 0] * scales['2d', 0] / flat:.3f} of it")
    print(f"3D layer tiles {[round(t) for t in tiles]}: routing {[round(routing['3d', z]) for z in range(len(clbs))]}")
    print(f"tile area {area:.4f}, width {width:.4f}")
    print(f"same wires: L4 spans {4 / width:.2f} tiles, L16 spans {16 / width:.2f}, same pitch: {100 * width:.1f} tracks")


if __name__ == "__main__":
    main()
