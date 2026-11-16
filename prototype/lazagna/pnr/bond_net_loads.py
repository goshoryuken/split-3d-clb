#!/usr/bin/env python3
"""What each bond output port really drives on the other layer, from a finished bonded layout.

A layer is laid out alone, so synthesis and Innovus see only the set_load on its bond output ports
(setup_pnr.py's 6 fF by default). The real load is the bond net's wire on the other layer (that
layer's SPEF), the joined top-level net (join3d/top.spef, if it has one) and the input pins it
reaches there (cells from the other layer's routed netlist, pin capacitance from the liberty files).
Writes a CSV for setup_pnr.py --bond-loads (port, load_pf, and the parts) and prints a summary.
The sending layer's own wire is left out: each layer's tools see their own wire.

Usage: bond_net_loads.py --layout DIR --lib LIB [LIB...] > loads.csv
  DIR is a run_bond.sh output folder (clb_half{0,1}/outputs/paths/clb_layer{0,1}.{spef,routed.v},
  join3d/top.spef).
"""
import argparse
import csv
import re
import statistics as st
import sys
from pathlib import Path

UNITS = {"F": 1e12, "PF": 1.0, "NF": 1e3, "FF": 1e-3}   # to pF


def spef_caps(path):
    """Total capacitance (pF) of each net in a SPEF file, by name."""
    caps, names, scale, in_map = {}, {}, 1.0, False
    if not path.exists():
        return caps
    for line in path.open(errors="replace"):
        if re.match(r"\*[A-Z_]+", line):    # a section or header keyword (*PORTS lines also start *<n>)
            in_map = line.startswith("*NAME_MAP")
        if line.startswith("*C_UNIT"):
            value, unit = line.split()[1:3]
            scale = float(value) * UNITS[unit.upper()]
        elif in_map and re.match(r"\*\d+\s", line):
            index, name = line.split()[:2]
            names[index] = name
        elif line.startswith("*D_NET"):
            _, net, total = line.split()[:3]
            caps[names.get(net, net).replace("\\", "")] = float(total) * scale
    return caps


def lib_pin_caps(paths):
    """{(cell, pin): pF} from liberty files: each pin's first plain capacitance attribute."""
    caps = {}
    for path in paths:
        text = Path(path).read_text(errors="replace")
        unit = re.search(r"capacitive_load_unit\s*\(\s*([\d.]+)\s*,\s*(\w+)\s*\)", text)
        scale = float(unit.group(1)) * UNITS[unit.group(2).upper()] if unit else 1.0
        marks = list(re.finditer(r'\b(cell|pin)\s*\(\s*"?(\w+)"?\s*\)\s*\{', text))
        cell = None
        for i, mark in enumerate(marks):
            if mark.group(1) == "cell":
                cell = mark.group(2)
                continue
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            found = re.search(r"^\s*capacitance\s*:\s*([\d.eE+-]+)", text[mark.end():end], re.M)
            if cell and found:
                caps.setdefault((cell, mark.group(2)), float(found.group(1)) * scale)
    return caps


def modules(path):
    """{module: (outputs, [(type, name, {port: net})])} from a structural Verilog netlist."""
    text = re.sub(r"//.*", "", Path(path).read_text(errors="replace"))
    out = {}
    for m in re.finditer(r"^\s*module\s+(\S+)\s*\((.*?)\);(.*?)^\s*endmodule", text, re.M | re.S):
        body = m.group(3)
        outputs = set(re.findall(r"^\s*output\s+(?:\[[^\]]*\]\s*)?([^\s;]+)\s*;", body, re.M))
        insts = []
        for i in re.finditer(r"^\s*(\w+)\s+(\\?\S+)\s*\((.*?)\)\s*;", body, re.M | re.S):
            if i.group(1) in ("input", "output", "wire", "assign", "inout", "module"):
                continue
            pins = {p: n.strip() for p, n in re.findall(r"\.(\w+)\s*\(\s*([^()]*?)\s*\)", i.group(3))}
            insts.append((i.group(1), i.group(2), pins))
        out[m.group(1)] = (outputs, insts)
    return out


def sinks(mods, module, net, seen=0):
    """Library-cell input pins a net reaches inside a module, through any submodules."""
    found = []
    for kind, name, pins in mods[module][1]:
        for pin, other in pins.items():
            if other != net:
                continue
            if kind in mods:
                if pin not in mods[kind][0] and seen < 10:   # into a submodule's input port
                    found += sinks(mods, kind, pin, seen + 1)
            else:
                found.append((kind, pin))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--layout", type=Path, required=True)
    parser.add_argument("--lib", nargs="+", required=True)
    args = parser.parse_args()
    pins = lib_pin_caps(args.lib)
    top = spef_caps(args.layout / "join3d/top.spef")
    layers = []
    for n in (0, 1):
        paths = args.layout / f"clb_half{n}/outputs/paths"
        mods = modules(paths / f"clb_layer{n}.routed.v")
        top_module = f"clb_layer{n}" if f"clb_layer{n}" in mods else next(iter(mods))
        layers.append((spef_caps(paths / f"clb_layer{n}.spef"), mods, top_module))
    rows = []
    for n in (0, 1):
        own_caps, mods, top_module = layers[n]
        other_caps, other_mods, other_top = layers[1 - n]
        for port in sorted(p for p in mods[top_module][0] if p.startswith("x_")):
            cells = sinks(other_mods, other_top, port)
            missing = [c for c in cells if c not in pins]
            pin_pf = sum(pins.get(c, 0.0) for c in cells)
            wire = other_caps.get(port, 0.0)
            load = wire + top.get(port, 0.0) + pin_pf
            rows.append(dict(port=port, sending_layer=n, load_pf=round(load, 5), other_wire_pf=round(wire, 5),
                             top_pf=round(top.get(port, 0.0), 5), pins=" ".join(f"{c}/{p}" for c, p in cells),
                             pin_pf=round(pin_pf, 5), own_wire_pf=round(own_caps.get(port, 0.0), 5),
                             missing=" ".join(f"{c}/{p}" for c, p in missing)))
    if not rows:
        raise SystemExit(f"no x_ output ports in {args.layout}")
    writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    for kind, test in (("FLE outputs", lambda r: "fle_out" in r["port"]), ("other", lambda r: "fle_out" not in r["port"])):
        loads = [r["load_pf"] for r in rows if test(r)]
        if loads:
            print(f"{kind}: {len(loads)} ports, load pF mean {st.mean(loads):.4f}, min {min(loads):.4f}, "
                  f"max {max(loads):.4f}", file=sys.stderr)
    if any(r["missing"] for r in rows):
        print("WARNING: pins without a liberty capacitance (counted as 0): "
              + " ".join(sorted({m for r in rows for m in r["missing"].split()})), file=sys.stderr)


if __name__ == "__main__":
    main()
