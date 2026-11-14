#!/usr/bin/env python3
"""Joins the routed netlists of both layers into one netlist of the whole CLB.

Each layer was synthesized alone, so both define modules with the same names and
different contents. This gives every module of a layer a prefix, keeps each
layer's top module, and adds the wrapper that connects the layers. It also writes
the top-level parasitics Tempus needs to read each layer's own: every net between
the layers gets the resistance and capacitance of one bond, per layer it touches.
Usage: join_netlist.py <clb_split.v> <output folder> <layer netlist>...
"""
from pathlib import Path
import re
import sys

WRAPPER = "logical_tile_clb_mode_clb_"
BOND_OHMS = 0.5
BOND_FF = 1.0
HEADER = """*SPEF "IEEE 1481-1998"
*DESIGN "{design}"
*DATE "0"
*VENDOR "0"
*PROGRAM "0"
*VERSION "0"
*DESIGN_FLOW "0"
*DIVIDER /
*DELIMITER :
*BUS_DELIMITER [ ]
*T_UNIT 1 PS
*C_UNIT 1 FF
*R_UNIT 1 OHM
*L_UNIT 1 HENRY

"""


def direct_wrapper(body):
    """Connects the layers straight to the CLB ports, so each port is one net."""
    alias = {}
    for left, right in re.findall(r"^\s*assign\s+(\S+)\s*=\s*(\S+?)\s*;", body, re.M):
        if left.startswith("n_"):
            alias[left] = right
        else:
            alias[right] = left
    body = re.sub(r"^\s*assign\s.*\n", "", body, flags=re.M)
    body = re.sub(r"^\s*wire\s+(n_\w+)\s*;\n", lambda m: "" if m.group(1) in alias else m.group(0), body, flags=re.M)
    return re.sub(r"\(\s*(n_\w+)\s*\)", lambda m: f"({alias.get(m.group(1), m.group(1))})", body), alias


def top_parasitics(wrapper, layer_netlists):
    directions = {}
    for number, text in enumerate(layer_netlists):
        top = text[text.index(f"module clb_layer{number}"):]
        top = top[:top.index("endmodule")]
        for direction, name in re.findall(r"^\s*(input|output)\s+(\w+)\s*;", top, re.M):
            directions[number, name] = direction
    nets = {}
    for number in (0, 1):
        start = wrapper.index(f"clb_layer{number} layer{number}")
        call = wrapper[start:wrapper.index(");", start)]
        for port, net in re.findall(r"\.(\w+)\(\s*([^)\s]+)\s*\)", call):
            nets.setdefault(net, []).append((number, port))
    ports = dict((name, d) for d, name in re.findall(r"^\s*(input|output)\s+(?:\[[^]]*\]\s*)?(\w+)\s*;", wrapper, re.M))
    text = [HEADER.format(design=WRAPPER)]
    for net, pins in sorted(nets.items()):
        is_port = net.split("[")[0] in ports
        conn = []
        if is_port:
            conn.append(f"*P {net} {'I' if ports[net.split('[')[0]] == 'input' else 'O'}")
        nodes = [f"layer{n}:{p}" for n, p in pins]
        conn += [f"*I {node} {'I' if directions[n, p] == 'input' else 'O'}" for node, (n, p) in zip(nodes, pins)]
        root = net if is_port else nodes[0]
        others = [node for node in nodes if node != root]
        caps = [f"{i} {node} {BOND_FF}" for i, node in enumerate(others, 1)] or [f"1 {root} {BOND_FF}"]
        res = [f"{i} {root} {node} {BOND_OHMS}" for i, node in enumerate(others, 1)]
        text += [f"*D_NET {net} {BOND_FF * len(caps)}", "*CONN", *conn, "*CAP", *caps]
        if res:
            text += ["*RES", *res]
        text += ["*END", ""]
    return "\n".join(text)


def main():
    split, output, *layers = sys.argv[1:]
    output = Path(output)
    text = Path(split).read_text()
    start = text.index(f"module {WRAPPER}")
    wrapper, _ = direct_wrapper(text[start:text.index("endmodule", start)])
    wrapper += "endmodule\n"
    parts = [wrapper]
    netlists = [Path(path).read_text() for path in layers]
    for number, netlist in enumerate(netlists):
        names = set(re.findall(r"^\s*module\s+(\w+)", netlist, re.M)) - {f"clb_layer{number}"}

        def rename(match):
            name = match.group(2)
            return match.group(1) + (f"l{number}_{name}" if name in names else name)
        parts.append(re.sub(r"^(\s*(?:module\s+)?)(\w+)", rename, netlist, flags=re.M))
    (output / "joined.v").write_text("\n".join(parts))
    (output / "top.spef").write_text(top_parasitics(wrapper, netlists))
    print(f"{output}: joined {len(layers)} layers")


if __name__ == "__main__":
    main()
