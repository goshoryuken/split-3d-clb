#!/usr/bin/env python3
"""Assign FLEs and input nets to layers in a packed netlist of two-layer CLBs.

The crossbar connects every input to every FLE, so any arrangement of a CLB's
FLEs is legal. This chooses one for each CLB, trying all splits and repeating
across the design so that timing-critical chains stay on one layer. Each input
net then gets a pin on the layer of the FLEs reading it, through the separate
I0 and I1 input ports. Criticality comes from logic depth, as this runs before
placement.
"""
import argparse
from itertools import combinations
from pathlib import Path
import re
import xml.etree.ElementTree as ET

FLES = 10
HALF = FLES // 2
PORT_PINS = 20
FEEDBACK = re.compile(r"fle\[(\d+)\]\.out\[0\]->crossbar")
INPUT = re.compile(r"clb\.I([01])\[(\d+)\]->crossbar")
PASSES = 6


class Clb:
    def __init__(self, block):
        self.block = block
        self.fles = {}
        for child in block.findall("block"):
            match = re.fullmatch(r"fle\[(\d+)\]", child.get("instance", ""))
            if match:
                self.fles[int(match.group(1))] = child
        self.used = [i for i, f in self.fles.items() if f.get("name") != "open"]
        ports = {p.get("name"): p for p in block.find("inputs").findall("port")}
        self.pins = {layer: ports[f"I{layer}"].text.split() for layer in (0, 1)}
        self.ports = ports


def in_ports(fle):
    inputs = fle.find("inputs")
    return [] if inputs is None else [p for p in inputs.findall("port") if p.get("name") == "in"]


def is_registered(fle):
    return any(b.get("instance") == "ff[0]" and b.get("name") != "open" for b in fle.iter("block"))


def build_graph(clbs):
    """Returns the FLE each net comes from, and each FLE's source nets."""
    drivers, sources = {}, {}
    for c, clb in enumerate(clbs):
        for i in clb.used:
            drivers[clb.fles[i].get("name")] = (c, i)
    for c, clb in enumerate(clbs):
        for i in clb.used:
            fle = clb.fles[i]
            nets = []
            for port in in_ports(fle):
                for token in port.text.split():
                    match = FEEDBACK.fullmatch(token)
                    if match:
                        nets.append(clb.fles[int(match.group(1))].get("name"))
                    match = INPUT.fullmatch(token)
                    if match:
                        nets.append(clb.pins[int(match.group(1))][int(match.group(2))])
            sources[(c, i)] = [n for n in nets if n != "open"]
    return drivers, sources


def criticalities(clbs, drivers, sources):
    """Returns a weight per (driver, sink) connection from logic depth."""
    registered = {(c, i): is_registered(clb.fles[i]) for c, clb in enumerate(clbs) for i in clb.used}
    fanins = {f: [drivers[n] for n in nets if n in drivers] for f, nets in sources.items()}
    fanouts = {f: [] for f in fanins}
    for sink, drive in fanins.items():
        for f in drive:
            fanouts[f].append(sink)

    def walk(start, step, stop):
        depth = {}
        for root in fanins:
            stack = [(root, False)]
            while stack:
                node, done = stack.pop()
                if done:
                    edges = [e for e in step[node] if not stop(e, node)]
                    depth[node] = 1 + max((depth.get(e, 0) for e in edges), default=0)
                    continue
                if node in depth:
                    continue
                depth.setdefault(node, 0)
                stack.append((node, True))
                stack += [(e, False) for e in step[node] if e not in depth and not stop(e, node)]
        return depth

    arrival = walk(fanins, fanins, lambda e, n: registered[e])
    remain = walk(fanouts, fanouts, lambda e, n: registered[n])
    longest = max(arrival.values(), default=1)
    weights = {}
    for sink, drive in fanins.items():
        for source in drive:
            path = arrival[source] + remain[sink]
            weights[(source, sink)] = max(weights.get((source, sink), 0), (path / longest) ** 8 + 0.01)
    return weights


def assign_layers(clbs, weights):
    layer = {(c, i): int(i >= HALF) for c, clb in enumerate(clbs) for i in clb.used}
    neighbours = {}
    for (a, b), w in weights.items():
        neighbours.setdefault(a, []).append((b, w))
        neighbours.setdefault(b, []).append((a, w))
    for _ in range(PASSES):
        for c, clb in enumerate(clbs):
            members = [(c, i) for i in clb.used]
            inside = set(members)
            # Weight this FLE gains from outside neighbours by sitting on layer 0 rather than 1.
            pull = {m: sum(w if layer[o] == 0 else -w for o, w in neighbours.get(m, []) if o not in inside)
                    for m in members}
            edges = [(a, o, w) for a in members for o, w in neighbours.get(a, [])
                     if o in inside and a < o]
            best, best_value = None, None
            low = max(0, len(members) - HALF)
            for size in range(low, min(HALF, len(members)) + 1):
                for lower in combinations(members, size):
                    lower = set(lower)
                    value = sum(pull[m] for m in lower) - sum(w for a, o, w in edges if (a in lower) != (o in lower))
                    if best_value is None or value > best_value:
                        best, best_value = lower, value
            for m in members:
                layer[m] = 0 if m in best else 1
    return layer


def crossing_weight(weights, layer):
    return sum(w for (a, b), w in weights.items() if layer[a] != layer[b])


def rewrite_clb(c, clb, layer, weights, drivers):
    slots = {0: list(range(HALF)), 1: list(range(HALF, FLES))}
    mapping = {}
    for i in sorted(clb.used, key=lambda i: layer[(c, i)]):
        mapping[i] = slots[layer[(c, i)]].pop(0)
    spare = iter(slots[0] + slots[1])
    full = {i: (mapping[i] if i in mapping else next(spare)) for i in clb.fles}

    # Every input net gets one pin, on the layer where it matters most. A second
    # pin for the other layer would not help: OpenFPGA's repacker reads one pin per net.
    readers = {}
    for i in clb.used:
        for port in in_ports(clb.fles[i]):
            for token in port.text.split():
                match = INPUT.fullmatch(token)
                if match:
                    net = clb.pins[int(match.group(1))][int(match.group(2))]
                    weight = weights.get((drivers.get(net), (c, i)), 0.5)
                    side = readers.setdefault(net, {0: 0.0, 1: 0.0})
                    side[layer[(c, i)]] = max(side[layer[(c, i)]], weight)
    new_pins = {0: [], 1: []}
    order = sorted(readers, key=lambda n: (-max(readers[n].values()), n))
    for net in order:
        want = int(readers[net][1] > readers[net][0])
        new_pins[want if len(new_pins[want]) < PORT_PINS else 1 - want].append(net)

    def pin_for(net, want):
        for side in (want, 1 - want):
            if net in new_pins[side]:
                return f"clb.I{side}[{new_pins[side].index(net)}]->crossbar"
        raise ValueError(net)

    for i in clb.used:
        fle = clb.fles[i]
        want = layer[(c, i)]
        for port in in_ports(fle):
            tokens = []
            for token in port.text.split():
                feedback = FEEDBACK.fullmatch(token)
                incoming = INPUT.fullmatch(token)
                if feedback:
                    tokens.append(f"fle[{full[int(feedback.group(1))]}].out[0]->crossbar")
                elif incoming:
                    tokens.append(pin_for(clb.pins[int(incoming.group(1))][int(incoming.group(2))], want))
                else:
                    tokens.append(token)
            port.text = " ".join(tokens)
    for side in (0, 1):
        clb.ports[f"I{side}"].text = " ".join(new_pins[side] + ["open"] * (PORT_PINS - len(new_pins[side])))
    for port in clb.block.find("outputs").findall("port"):
        if port.get("name") == "O":
            old = port.text.split()
            new = ["open"] * len(old)
            for index, token in enumerate(old):
                if token != "open":
                    new[full[index]] = f"fle[{full[index]}].out[0]->clbouts1"
            port.text = " ".join(new)
    for old, fle in clb.fles.items():
        fle.set("instance", f"fle[{full[old]}]")
    children = sorted(clb.fles.values(), key=lambda f: int(f.get("instance")[4:-1]))
    position = min(list(clb.block).index(f) for f in children)
    for fle in children:
        clb.block.remove(fle)
    for offset, fle in enumerate(children):
        clb.block.insert(position + offset, fle)


def rearrange(source, output):
    tree = ET.parse(source)
    clbs = [Clb(b) for b in tree.getroot().findall("block") if b.get("instance", "").startswith("clb[")
            and b.get("name") != "open"]
    drivers, sources = build_graph(clbs)
    weights = criticalities(clbs, drivers, sources)
    start = {(c, i): int(i >= HALF) for c, clb in enumerate(clbs) for i in clb.used}
    before = crossing_weight(weights, start)
    layer = assign_layers(clbs, weights)
    after = crossing_weight(weights, layer)
    for c, clb in enumerate(clbs):
        rewrite_clb(c, clb, layer, weights, drivers)
    tree.write(output, encoding="unicode", xml_declaration=True)
    return before, after


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    before, after = rearrange(args.source, args.output)
    print(f"weighted crossings before: {before:.1f}  after: {after:.1f}")


if __name__ == "__main__":
    main()
