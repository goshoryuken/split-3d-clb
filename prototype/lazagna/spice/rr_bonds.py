#!/usr/bin/env python3
"""Bonds a two-layer fabric's routing needs per footprint tile, read from VPR's routing graph.

A bond carries one signal from one layer to the other at one place, so the routing needs one bond
per distinct (source node, place, direction) among the graph's edges that change layer. The place
is the tile of the mux the edge feeds: a wire's driving mux, or an input pin's tile. In-CLB
crossings are not in the routing graph (the split CLB adds one bond per FLE output).

Over the interior of the grid (2 tiles in from the edge), mean per footprint tile, split by kind
(OPIN -> wire, wire -> wire, wire -> IPIN), plus the busiest tile.

Usage: rr_bonds.py RR_GRAPH.xml   (a file, or a fifo VPR writes with --write_rr_graph)
"""
import collections
import sys
import xml.etree.ElementTree as ET


def main():
    kind, loc = {}, {}
    width = height = 0
    bonds, sinks = set(), set()
    type_name, grid = {}, collections.defaultdict(dict)
    for _, el in ET.iterparse(sys.argv[1]):
        tag = el.tag
        if tag == "block_type":
            type_name[el.get("id")] = el.get("name")
        elif tag == "grid_loc":
            x, y = int(el.get("x")), int(el.get("y"))
            width, height = max(width, x + 1), max(height, y + 1)
            if el.get("width_offset", "0") == "0" and el.get("height_offset", "0") == "0":
                grid[(x, y)][int(el.get("layer", 0))] = type_name.get(el.get("block_type_id"), "?")
        elif tag == "node":
            i = int(el.get("id"))
            kind[i] = el.get("type")
            l = el.find("loc")
            x, y = int(l.get("xlow")), int(l.get("ylow"))
            if el.get("direction") == "DEC_DIR":
                x, y = int(l.get("xhigh")), int(l.get("yhigh"))
            loc[i] = (int(l.get("layer", 0)), x, y)
            el.clear()
        elif tag == "edge":
            src, sink = int(el.get("src_node")), int(el.get("sink_node"))
            if loc[src][0] != loc[sink][0]:
                k = "opin" if kind[src] == "OPIN" else "ipin" if kind[sink] == "IPIN" else "wire"
                bonds.add((src, loc[sink][1], loc[sink][2], loc[src][0], k))
                sinks.add((sink, loc[sink][1], loc[sink][2], loc[src][0], k))
            el.clear()

    def inside(x, y):
        return 2 <= x <= width - 3 and 2 <= y <= height - 3

    tiles = sum(inside(x, y) for x in range(width) for y in range(height))
    # Two ways to wire a crossing, chosen per tile, kind and direction (whichever needs fewer):
    #   source: one bond per signal sent across, fanning out to every mux it feeds there;
    #   sink:   the receiving mux's other-layer inputs muxed on their own layer first, one bond
    #           per receiving mux (its output) -- e.g. one per input pin, however many tracks.
    groups = collections.defaultdict(lambda: [0, 0])
    for _, x, y, layer, k in bonds:
        groups[(x, y, layer, k)][0] += 1
    for _, x, y, layer, k in sinks:
        groups[(x, y, layer, k)][1] += 1
    print(f"grid {width}x{height}, {tiles} interior footprint tiles; routing bonds per tile, "
          f"by source / by receiving mux / fewer of the two per group")
    by_type = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0, 0]))
    for x in range(width):
        for y in range(height):
            if inside(x, y):
                key = " / ".join(grid[(x, y)].get(l, "-") for l in sorted(grid[(x, y)]))
                by_type[key]["tiles"][0] += 1
    for (x, y, layer, k), (s, r) in groups.items():
        if inside(x, y):
            key = " / ".join(grid[(x, y)].get(l, "-") for l in sorted(grid[(x, y)]))
            for kk in (k, "all"):
                c = by_type[key][kk]
                c[0], c[1], c[2] = c[0] + s, c[1] + r, c[2] + min(s, r)
    for key, d in sorted(by_type.items(), key=lambda kv: -kv[1]["tiles"][0]):
        n = d["tiles"][0]
        print(f"  {key:28} {n:4} tiles  " + "  ".join(
            f"{kk} {c[0] / n:.0f}/{c[1] / n:.0f}/{c[2] / n:.0f}" for kk, c in sorted(d.items()) if kk != "tiles"))


if __name__ == "__main__":
    main()
