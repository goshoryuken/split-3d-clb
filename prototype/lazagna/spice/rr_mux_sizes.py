#!/usr/bin/env python3
"""Mux sizes and loads of a fabric, read from VPR's routing graph (--write_rr_graph).

For fabrics LaZagna cannot generate RTL for (custom switch blocks with vertical links, a CLB
over four layers), spice/make_spice.py takes its mux sizes from here instead of the RTL.
Checked against the RTL-derived numbers of the fabrics that have RTL (SPICE_RESULTS.md).

Over the interior of the grid (2 tiles in from the edge), per tile and layer:
  sb          mean inputs of a routing-wire mux (edges into a CHANX/CHANY node)
  cb          mean inputs of a connection-block mux (edges into an IPIN that has any)
  sb_loads    switch-block mux inputs per tile over its 2W tracks
  cb_loads    connection-block mux inputs per tile over its 2W tracks
  opin_loads  mean wires an output pin drives
  vertical    share of wire-mux inputs that come from another layer
  extra       VPR's 3D switch-block nodes (custom switch blocks with vertical links): CHANX/CHANY
              nodes past the channel's tracks (ptc >= W), one mux each between a wire and a wire
              on another layer, delayless in VPR (the destination wire's inter-layer driver
              carries the crossing). sb and sb_loads count each vertical link once, as the
              destination mux's input, as the RTL does.

Usage: rr_mux_sizes.py RR_GRAPH.xml TRACKS
"""
import collections
import statistics
import sys
import xml.etree.ElementTree as ET


def main():
    path, tracks = sys.argv[1], int(sys.argv[2])
    kind, loc = {}, {}
    fan_in = collections.Counter()
    from_other_layer = collections.Counter()
    from_3d = collections.Counter()
    fan_out = collections.Counter()
    switch_names, edge_kinds = {}, collections.Counter()
    width = height = 0
    for _, el in ET.iterparse(path):
        tag = el.tag
        if tag == "switch" and el.get("id") is not None:
            switch_names[el.get("id")] = el.get("name")
        elif tag == "grid_loc":
            width = max(width, int(el.get("x")) + 1)
            height = max(height, int(el.get("y")) + 1)
        elif tag == "node":
            i = int(el.get("id"))
            kind[i] = el.get("type")
            l = el.find("loc")
            loc[i] = (int(l.get("layer", 0)), int(l.get("xlow")), int(l.get("ylow")),
                      int(l.get("xhigh")), int(l.get("yhigh")), el.get("direction"), int(l.get("ptc")))
            el.clear()
        elif tag == "edge":
            src, sink = int(el.get("src_node")), int(el.get("sink_node"))
            if kind[sink] in ("CHANX", "CHANY", "IPIN") and kind[src] in ("CHANX", "CHANY", "OPIN"):
                fan_in[sink] += 1
                if loc[src][0] != loc[sink][0]:
                    from_other_layer[sink] += 1
                if kind[src] in ("CHANX", "CHANY") and loc[src][6] >= tracks:
                    from_3d[sink] += 1
            if kind[src] == "OPIN" and kind[sink] in ("CHANX", "CHANY"):
                fan_out[src] += 1
            if kind[sink] in ("CHANX", "CHANY", "IPIN") and kind[src] in ("CHANX", "CHANY", "OPIN"):
                cat = lambda n: ("3D node" if loc[n][6] >= tracks else "wire") if kind[n].startswith("CHAN") else kind[n]
                edge_kinds[(cat(src), cat(sink), loc[src][0] != loc[sink][0], el.get("switch_id"))] += 1
            el.clear()

    def fan_in_from_3d(i):
        return from_3d[i]

    def inside(x, y):
        return 2 <= x <= width - 3 and 2 <= y <= height - 3

    layers = 1 + max(l[0] for l in loc.values())
    tiles = sum(inside(x, y) for x in range(width) for y in range(height)) * layers
    wires, extra, ipins, sb_inputs, cb_inputs, vertical = [], [], [], 0, 0, 0
    for i, t in kind.items():
        layer, xl, yl, xh, yh, direction, ptc = loc[i]
        if t in ("CHANX", "CHANY") and fan_in[i]:
            # Count each wire at the tile its driving mux sits in.
            dec = direction == "DEC_DIR"
            sx, sy = (xh, yh) if dec else (xl, yl)
            if inside(sx, sy):
                if ptc >= tracks:
                    extra.append(fan_in[i])
                else:
                    # A vertical link is wire -> 3D node -> 3D node on the other layer -> wire mux;
                    # count it once, as the destination mux's input (as the RTL counts it).
                    wires.append(fan_in[i])
                    sb_inputs += fan_in[i]
                    vertical += from_other_layer[i] + fan_in_from_3d(i)
        elif t == "IPIN" and fan_in[i] and inside(xl, yl):
            ipins.append(fan_in[i])
            cb_inputs += fan_in[i]
    opins = [fan_out[i] for i, t in kind.items() if t == "OPIN" and fan_out[i] and inside(loc[i][1], loc[i][2])]
    print(f"grid {width}x{height}, {layers} layers, {tiles} interior tile-layers, W={tracks}")
    print(f"sb {statistics.mean(wires):.2f}  cb {statistics.mean(ipins):.2f}  "
          f"sb_loads {sb_inputs / tiles / (2 * tracks):.3f}  cb_loads {cb_inputs / tiles / (2 * tracks):.3f}  "
          f"opin_loads {statistics.mean(opins):.2f}  vertical {vertical / sb_inputs:.3f}")
    print(f"per tile-layer: {len(wires) / tiles:.1f} wire muxes, {sb_inputs / tiles:.0f} SB inputs, "
          f"{len(ipins) / tiles:.1f} IPIN muxes, {cb_inputs / tiles:.0f} CB inputs")
    print("edges: from -> to, crosses layers, switch: count")
    for (a, b, cross, sw), n in edge_kinds.most_common():
        print(f"  {a:8} -> {b:8} {'cross' if cross else 'same ':5} {switch_names.get(sw, sw):26} {n}")
    if extra:
        print(f"3D switch-block nodes: {len(extra) / tiles:.1f} per tile-layer, mean inputs "
              f"{statistics.mean(extra):.2f}, {sum(extra) / tiles:.0f} inputs per tile-layer")


if __name__ == "__main__":
    main()
