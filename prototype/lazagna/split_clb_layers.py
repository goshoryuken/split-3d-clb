#!/usr/bin/env python3
"""Split OpenFPGA's CLB module into one Verilog module per layer.

The split uses only the layer label OpenFPGA puts on each child instance, and
stops if any child has none. Pin layers come from the architecture file. The
output keeps the CLB's module name and ports, so it drops into the fabric in
place of the original. Its two layer instances meet only through the wires
listed in the crossings file.
"""
import argparse
import csv
from pathlib import Path
import re
import xml.etree.ElementTree as ET

MODULE = "logical_tile_clb_mode_clb_"
LAYER_ATTR = re.compile(r"\(\*\s*vtr_parent_relative_layer_offset\s*=\s*(\d+)\s*\*\)\s*$")
INSTANCE = re.compile(r"^\s*(\w+)\s+(\w+)\s*\(\s*$", re.M)


def module_text(text, name):
    start = re.search(rf"^\s*module\s+{name}\s*\(", text, re.M)
    return None if not start else text[start.start():text.index("endmodule", start.start())]


def declarations(body, kinds):
    found = {}
    for kind, msb, lsb, name in re.findall(rf"^\s*({kinds})\s+\[(\d+):(\d+)\]\s+(\w+)\s*;", body, re.M):
        low, high = sorted((int(msb), int(lsb)))
        found[name] = (kind, list(range(low, high + 1)))
    return found


def child_ports(source, wanted):
    ports = {}
    files = [p.read_text() for p in source.rglob("*.v")]
    for name in wanted:
        for text in files:
            body = module_text(text, name)
            if body:
                ports[name] = {port: kind for port, (kind, _) in declarations(body, "input|output").items()}
                break
        else:
            raise SystemExit(f"no definition found for module {name}")
    return ports


def expand(expr, widths):
    expr = expr.strip()
    if expr.startswith("{"):
        return [bit for part in expr[1:-1].split(",") for bit in expand(part, widths)]
    match = re.fullmatch(r"(\w+)(?:\[(\d+)(?::(\d+))?\])?", expr)
    if not match:
        raise SystemExit(f"cannot read connection {expr!r}")
    base, first, last = match.groups()
    if first is None:
        return [(base, i) for i in widths[base]]
    last = first if last is None else last
    step = 1 if int(last) >= int(first) else -1
    return [(base, i) for i in range(int(first), int(last) + step, step)]


def parse(body):
    instances = []
    for match in INSTANCE.finditer(body):
        kind, name = match.groups()
        if kind == "module":
            continue
        close = body.index(");", match.end())
        before = body[:match.start()].rstrip()
        label = LAYER_ATTR.search(before)
        if not label:
            raise SystemExit(f"instance {name} has no layer label")
        conns = re.findall(r"\.(\w+)\(([^()]*)\)", body[match.end():close])
        instances.append((kind, name, int(label.group(1)), conns))
    return instances


def pin_layers(arch):
    layers = {}
    tile = next(t for t in ET.parse(arch).getroot().iter("tile") if t.get("name") == "clb")
    for loc in tile.iter("loc"):
        layer = int(loc.get("pin_layer", "0"))
        for token in loc.text.split():
            match = re.fullmatch(r"clb\.(\w+)(?:\[(\d+)(?::(\d+))?\])?", token)
            port, first, last = match.groups()
            first = int(first or 0)
            last = int(last) if last is not None else first
            for i in range(min(first, last), max(first, last) + 1):
                layers[(f"clb_{port}", i)] = layer
    return layers


def scalar(bit):
    return f"n_{bit[0]}_{bit[1]}"


def category(bit):
    base = bit[0]
    if base.startswith("clb_I"):
        return "input pin"
    if base == "clb_clk":
        return "clock pin"
    if "fle_out" in base:
        return "FLE output"
    if "ccff" in base:
        return "config chain"
    if base in ("pReset", "prog_clk", "set", "reset", "clk"):
        return "global"
    return "other"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="OpenFPGA Verilog folder")
    parser.add_argument("--arch", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    path = args.source / "lb" / f"{MODULE}.v"
    body = module_text(path.read_text(), MODULE)
    if re.search(r"^\s*assign\b", body, re.M):
        raise SystemExit("module has assign statements this tool does not handle")
    instances = parse(body)
    top_ports = declarations(body, "input|output")
    wires = declarations(body, "wire")
    widths = {n: bits for n, (_, bits) in {**top_ports, **wires}.items()}
    ports = child_ports(args.source, sorted({kind for kind, *_ in instances}))
    pins = pin_layers(args.arch)

    driver, loads, driven_by_instance = {}, {}, set()
    for kind, name, layer, conns in instances:
        for port, expr in conns:
            for bit in expand(expr, widths):
                if ports[kind][port] == "output":
                    if bit in driver:
                        raise SystemExit(f"{bit} has two drivers")
                    driver[bit] = layer
                    driven_by_instance.add(bit)
                else:
                    loads.setdefault(bit, set()).add(layer)
    for port, (kind, bits) in top_ports.items():
        for i in bits:
            bit = (port, i)
            if kind == "input":
                driver[bit] = pins.get(bit, 0)
            else:
                loads.setdefault(bit, set()).add(pins.get(bit, driver.get(bit, 0)))

    layers = sorted({layer for *_, layer, _ in instances})
    crossings = [(b, driver[b], sorted(loads[b] - {driver[b]})) for b in sorted(driver)
                 if b in loads and loads[b] - {driver[b]}]
    used = {layer: set() for layer in layers}
    for kind, name, layer, conns in instances:
        for port, expr in conns:
            used[layer].update(expand(expr, widths))

    out = [f"// Generated by split_clb_layers.py from {MODULE}. One module per layer.\n"]
    for layer in layers:
        inputs, outputs = layer_ports(layer, used, driver, driven_by_instance, loads, top_ports)
        names = [scalar(b) for b in inputs + outputs]
        out.append(f"module clb_layer{layer}({', '.join(names)});\n")
        out += [f"input {scalar(b)};\n" for b in inputs] + [f"output {scalar(b)};\n" for b in outputs]
        internal = sorted(used[layer] - set(inputs) - set(outputs))
        out += [f"wire {scalar(b)};\n" for b in internal]
        for kind, name, label, conns in instances:
            if label != layer:
                continue
            text = ", ".join(f".{p}({{{', '.join(scalar(b) for b in expand(e, widths))}}})" for p, e in conns)
            out.append(f"{kind} {name} ({text});\n")
        out.append("endmodule\n\n")

    header = body[:body.index(";") + 1]
    out.append(header + "\n")
    for port, (kind, bits) in top_ports.items():
        out.append(f"{kind} [{bits[0]}:{bits[-1]}] {port};\n")
    every = sorted(set(driver) | set(loads))
    out += [f"wire {scalar(b)};\n" for b in every]
    for port, (kind, bits) in top_ports.items():
        for i in bits:
            left, right = (scalar((port, i)), f"{port}[{i}]") if kind == "input" else (f"{port}[{i}]", scalar((port, i)))
            out.append(f"assign {left} = {right};\n")
    for layer in layers:
        names = sorted(sum(layer_ports(layer, used, driver, driven_by_instance, loads, top_ports), []))
        out.append(f"clb_layer{layer} layer{layer} ({', '.join(f'.{scalar(b)}({scalar(b)})' for b in names)});\n")
    out.append("endmodule\n")

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "clb_split.v").write_text("".join(out))
    with open(args.output / "clb_crossings.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["signal", "bit", "type", "from_layer", "to_layer"])
        for bit, source, sinks in crossings:
            for sink in sinks:
                writer.writerow([bit[0], bit[1], category(bit), source, sink])
    with open(args.output / "instance_layers.csv", "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["instance", "module", "layer"])
        writer.writerows((name, kind, layer) for kind, name, layer, _ in instances)
    counts = {}
    for bit, _, sinks in crossings:
        counts[category(bit)] = counts.get(category(bit), 0) + len(sinks)
    print(f"instances per layer: { {l: sum(i[2] == l for i in instances) for l in layers} }")
    print(f"crossing signals: {sum(counts.values())}  {counts}")


def layer_ports(layer, used, driver, driven_by_instance, loads, top_ports):
    """Returns one layer module's input and output bits.

    A bit is an output only when an instance on this layer drives it. The CLB's
    own inputs come from outside, even on the layer their pin sits on.
    """
    mine = {b for b in used[layer] if b in driven_by_instance and driver[b] == layer}
    inputs = sorted(used[layer] - mine)
    outputs = sorted(b for b in mine if b in top_ports_bits(top_ports, "output") or loads.get(b, set()) - {layer})
    return inputs, outputs


def top_ports_bits(top_ports, wanted):
    return {(port, i) for port, (kind, bits) in top_ports.items() if kind == wanted for i in bits}


if __name__ == "__main__":
    main()
