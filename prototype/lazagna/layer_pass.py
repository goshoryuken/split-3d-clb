#!/usr/bin/env python3
"""Post-pack pass: choose which layer each FLE of a split CLB sits on, timing-aware.

VPR's packer fills a CLB's FLE slots without looking at their layers (fle[0-9] are on layer
0, fle[10-19] on layer 1), so which LUTs share a layer is close to arbitrary. This pass
permutes FLEs between the two layers inside each CLB of a packed netlist (.net) to cut
timing-weighted layer crossings, then rewrites the .net for VPR to place and route.

Cost, summed over atom connections between two FLEs:
    criticality ** EXPONENT  x  crossing delay  x  [the two FLEs are on different layers]
  - criticality: the packer's own setup criticality of the connection's sink pin, written
    by VPR's --pack_criticality_file (this branch);
  - crossing delay: inside one CLB, the crossbar's layer_crossing_delay; between CLBs, the
    routing crossing (Tdel of L4_inter_layer_driver minus L4_driver), both read from arch.xml.
  Connections to RAM, DSP and IO count nothing: their layer is chosen later, by the placer.

Legality kept per CLB and layer: at most as many FLEs as that layer has slots (10), and at
most as many distinct outside nets as that layer's input port has pins (40, clb.I0 / clb.I1,
from --local-inputs: each layer's crossbar reads only its own layer's pins). The crossbars
are full, so any FLE can sit in any slot of its layer. Feedback reaches every FLE.

A CLB where the packer ran a signal through an empty FLE (a LUT in wire mode, used when one
layer's pins are full) is left exactly as packed.

Search: per CLB, repeated best-gain moves (one FLE into a free slot) or swaps (one FLE from
each layer), every other CLB held fixed; sweeps over all CLBs until a sweep gains nothing.

Usage: layer_pass.py NET CRITICALITY ARCH [-o OUT] [--exponent 8]
"""
import argparse
import collections
import random
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

EXPONENT = 8  # VPR's placer ends at criticality ** 8 (--td_place_exp_last)
SWEEPS = 20
FEEDBACK = re.compile(r"fle\[(\d+)\]\.out\[0\]->(\w+)")
PIN = re.compile(r"clb\.(\w+)\[(\d+)\]->(\w+)")


def read_arch(path):
    """Slot layers, per-layer crossbar and input port, pins per port, the two crossing delays (ps)."""
    xml = Path(path).read_text()
    fle = re.search(r'<pb_type name="fle" num_pb="(\d+)"(?: instance_layer_offsets="([^"]+)")?', xml)
    slots = int(fle.group(1))
    if not fle.group(2):
        raise SystemExit("layer_pass: the CLB's FLEs are all on one layer (no instance_layer_offsets)")
    slot_layer = [int(x) for x in fle.group(2).split()]
    layer_of = {}
    for m in re.finditer(r'<complete name="(\w+)" input="clb\.(\w+) fle\[\d+:\d+\]\.out" '
                         r'output="fle\[(\d+):(\d+)\]\.in"(?: layer_crossing_delay="([^"]+)")?', xml):
        name, port, hi, lo, delay = m.groups()
        layers = {slot_layer[i] for i in range(int(lo), int(hi) + 1)}
        assert len(layers) == 1, f"crossbar {name} feeds FLEs on several layers"
        layer_of[layers.pop()] = (name, port, float(delay or 0) * 1e12)
    if sorted(layer_of) != sorted(set(slot_layer)):
        raise SystemExit("layer_pass: needs one crossbar per layer fed by its own input port (--local-inputs)")
    tile = re.search(r'<tile name="clb".*?</tile>', xml, re.S).group(0)
    pins = {m.group(1): int(m.group(2)) for m in re.finditer(r'<input name="(\w+)" num_pins="(\d+)"', tile)}
    tdel = {m.group(1): float(m.group(2)) for m in
            re.finditer(r'<switch type="\w+" name="(\w+)"[^>]*?Tdel="([^"]+)"', xml)}
    route = (tdel["L4_inter_layer_driver"] - tdel["L4_driver"]) * 1e12
    crossings = {layer_of[l][2] for l in layer_of}
    assert len(crossings) == 1, "different in-CLB crossing delays per layer"
    return dict(slots=slots, slot_layer=slot_layer, layers=layer_of, pins=pins,
                clb_crossing=crossings.pop(), route_crossing=route)


class Clb:
    def __init__(self, index, block):
        self.index = index
        self.block = block
        self.fles = {}  # slot -> element
        for child in block.findall("block"):
            m = re.fullmatch(r"fle\[(\d+)\]", child.get("instance", ""))
            if m:
                self.fles[int(m.group(1))] = child
        self.used = sorted(i for i, f in self.fles.items() if f.get("name") != "open")
        # An empty FLE can still carry a signal: the packer's cluster router sometimes runs a pin's
        # net through an unused LUT ("wire" mode) to reach the other layer when that layer's pins are
        # full. Such a CLB is left exactly as packed.
        self.frozen = any(f.get("name") == "open" and any(t != "open" for p in in_ports(f) for t in p.text.split())
                          for f in self.fles.values())
        self.ports = {p.get("name"): p for p in block.find("inputs").findall("port")}
        self.pin_nets = {name: p.text.split() for name, p in self.ports.items()}


def in_ports(fle):
    inputs = fle.find("inputs")
    return [] if inputs is None else [p for p in inputs.findall("port") if p.get("name") == "in"]


def outside_nets(clb, slot):
    """Nets an FLE reads through the CLB's input pins (not feedback)."""
    nets = set()
    for port in in_ports(clb.fles[slot]):
        for token in port.text.split():
            m = PIN.fullmatch(token)
            if m:
                net = clb.pin_nets[m.group(1)][int(m.group(2))]
                if net != "open":
                    nets.add(net)
    return nets


def load(net_file):
    tree = ET.parse(net_file)
    clbs = [Clb(c, b) for c, b in enumerate(b for b in tree.getroot().findall("block")
                                            if b.get("instance", "").startswith("clb[") and b.get("name") != "open")]
    atom = {}  # atom block name -> (clb, slot)
    for clb in clbs:
        for slot in clb.used:
            for leaf in clb.fles[slot].iter("block"):
                if leaf.get("name") != "open" and leaf.find("block") is None:
                    atom[leaf.get("name")] = (clb.index, slot)
    return tree, clbs, atom


def neighbours(crit_file, atom, arch, exponent):
    """Weighted FLE adjacency: {fle: {fle: weight}}, weight = sum of crit**exp x crossing ps."""
    adj = collections.defaultdict(lambda: collections.defaultdict(float))
    for line in Path(crit_file).read_text().splitlines():
        if line.startswith("#"):
            continue
        src, dst, crit = line.split("\t")
        a, b = atom.get(src), atom.get(dst)
        if a is None or b is None or a == b:
            continue
        cost = arch["clb_crossing"] if a[0] == b[0] else arch["route_crossing"]
        w = float(crit) ** exponent * cost
        if w > 0:
            adj[a][b] += w
            adj[b][a] += w
    return adj


def total_cost(adj, layer):
    return sum(w for a, nbrs in adj.items() for b, w in nbrs.items() if layer[a] != layer[b]) / 2


def optimise(clbs, adj, arch, layer):
    """Greedy move/swap improvement per CLB; returns the number of moves made."""
    slot_cap = collections.Counter(arch["slot_layer"])
    port_of = {l: arch["layers"][l][1] for l in arch["layers"]}
    outside = {(clb.index, s): outside_nets(clb, s) for clb in clbs for s in clb.used}
    moves = 0
    for sweep in range(SWEEPS):
        gained = 0.0
        for clb in clbs:
            members = [(clb.index, s) for s in clb.used]
            if len(members) < 2 or clb.frozen:
                continue
            for _ in range(4 * len(members)):
                gain = {m: sum(w if layer[o] != layer[m] else -w for o, w in adj.get(m, {}).items()) for m in members}
                count = collections.Counter(layer[m] for m in members)
                options = []
                for m in members:
                    if gain[m] > 1e-9 and count[1 - layer[m]] < slot_cap[1 - layer[m]]:
                        options.append((gain[m], (m,)))
                lower = [m for m in members if layer[m] == 0]
                upper = [m for m in members if layer[m] == 1]
                for a in lower:
                    for b in upper:
                        g = gain[a] + gain[b] - 2 * adj.get(a, {}).get(b, 0.0)
                        if g > 1e-9:
                            options.append((g, (a, b)))
                done = False
                for g, move in sorted(options, key=lambda o: -o[0]):
                    for m in move:
                        layer[m] = 1 - layer[m]
                    pins_ok = all(len(set().union(*([outside[m] for m in members if layer[m] == l] or [set()])))
                                  <= arch["pins"][port_of[l]] for l in (0, 1))
                    if pins_ok:
                        gained += g
                        moves += len(move)
                        done = True
                        break
                    for m in move:
                        layer[m] = 1 - layer[m]
                if not done:
                    break
        print(f"  sweep {sweep + 1}: gained {gained:.1f}", file=sys.stderr)
        if gained < 1e-6:
            break
    return moves


def rewrite(clb, layer, arch, rng=None):
    """Renumber the CLB's FLEs so each sits in a slot of its chosen layer, and fix every token.
    With rng, every FLE gets a random slot of its layer (the control: no FLE changes layer)."""
    if clb.frozen:
        return False
    slot_layer = arch["slot_layer"]
    xbar = {l: arch["layers"][l][0] for l in arch["layers"]}
    port = {l: arch["layers"][l][1] for l in arch["layers"]}
    want = {s: layer[(clb.index, s)] for s in clb.used}
    new = {s: s for s in clb.used if slot_layer[s] == want[s]}  # stayers keep their slot
    if rng is not None:
        new = {}
        for l in (0, 1):
            mine = [s for s in clb.used if want[s] == l]
            new.update(zip(mine, rng.sample([i for i in range(arch["slots"]) if slot_layer[i] == l], len(mine))))
    free = {l: [i for i in range(arch["slots"]) if slot_layer[i] == l and i not in new.values()] for l in (0, 1)}
    for s in clb.used:
        if s not in new:
            new[s] = free[want[s]].pop(0)
    spare = iter(sorted(set(range(arch["slots"])) - set(new.values())))
    full = {s: (new[s] if s in new else next(spare)) for s in clb.fles}
    if all(full[s] == s for s in full):
        return False

    # Outside nets per layer, keeping each net's pin index when it stays on the same port.
    reads = {0: set(), 1: set()}
    for s in clb.used:
        reads[want[s]] |= outside_nets(clb, s)
    pins = {}
    for l in (0, 1):
        old = clb.pin_nets[port[l]]
        size = arch["pins"][port[l]]
        kept = ["open"] * size
        for i, net in enumerate(old):
            if net in reads[l]:
                kept[i] = net
        rest = iter(sorted(reads[l] - set(kept)))
        for i in range(size):
            if kept[i] == "open":
                kept[i] = next(rest, "open")
        assert len(reads[l]) <= size and not list(rest), "pin limit"
        pins[l] = kept

    for s in clb.used:
        l = want[s]
        for p in in_ports(clb.fles[s]):
            tokens = []
            for token in p.text.split():
                fb, pin = FEEDBACK.fullmatch(token), PIN.fullmatch(token)
                if fb:
                    tokens.append(f"fle[{full[int(fb.group(1))]}].out[0]->{xbar[l]}")
                elif pin:
                    net = clb.pin_nets[pin.group(1)][int(pin.group(2))]
                    tokens.append(f"clb.{port[l]}[{pins[l].index(net)}]->{xbar[l]}")
                else:
                    tokens.append(token)
            p.text = " ".join(tokens)
    for l in (0, 1):
        clb.ports[port[l]].text = " ".join(pins[l])
    for p in clb.block.find("outputs").findall("port"):
        old = p.text.split()
        out = ["open"] * len(old)
        for i, token in enumerate(old):
            if token != "open":
                m = re.fullmatch(r"fle\[(\d+)\]\.out\[0\]->(\w+)", token)
                out[full[int(m.group(1))]] = f"fle[{full[int(m.group(1))]}].out[0]->{m.group(2)}"
        p.text = " ".join(out)
    for s, fle in clb.fles.items():
        fle.set("instance", f"fle[{full[s]}]")
    children = sorted(clb.fles.values(), key=lambda f: int(f.get("instance")[4:-1]))
    position = min(list(clb.block).index(f) for f in children)
    for f in children:
        clb.block.remove(f)
    for k, f in enumerate(children):
        clb.block.insert(position + k, f)
    return True


def connectivity(clb, arch):
    """What each FLE (by name) reads at each input, the FLEs driving CLB outputs, and whether every
    token uses the crossbar and input port of its FLE's layer: must not change in a rewrite."""
    slot_layer = arch["slot_layer"]
    xbar = {l: arch["layers"][l][0] for l in arch["layers"]}
    port = {l: arch["layers"][l][1] for l in arch["layers"]}
    pins = {p.get("name"): p.text.split() for p in clb.block.find("inputs").findall("port")}
    slots = {int(f.get("instance")[4:-1]): f for f in clb.block.findall("block") if f.get("instance", "").startswith("fle[")}
    reads, legal = {}, True
    for s, fle in slots.items():
        if fle.get("name") == "open":
            continue
        l = slot_layer[s]
        sources = []
        for p in in_ports(fle):
            for token in p.text.split():
                fb, pin = FEEDBACK.fullmatch(token), PIN.fullmatch(token)
                if fb:
                    sources.append(("fle", slots[int(fb.group(1))].get("name")))
                    legal &= fb.group(2) == xbar[l]
                elif pin:
                    sources.append(("net", pins[pin.group(1)][int(pin.group(2))]))
                    legal &= pin.group(1) == port[l] and pin.group(3) == xbar[l]
                else:
                    sources.append(token)
        reads[fle.get("name")] = sources
    outs = sorted(slots[int(re.match(r"fle\[(\d+)\]", tok).group(1))].get("name")
                  for p in clb.block.find("outputs").findall("port") for tok in p.text.split() if tok != "open")
    counts = collections.Counter(slot_layer[s] for s, f in slots.items() if f.get("name") != "open")
    legal &= all(counts[l] <= collections.Counter(slot_layer)[l] for l in counts)
    legal &= all(sum(n != "open" for n in pins[port[l]]) <= arch["pins"][port[l]] for l in port)
    return reads, outs, legal


def crossing_counts(adj, layer, atom_pairs, threshold):
    """Connections with criticality >= threshold that cross layers, inside / between CLBs."""
    inside = between = 0
    for a, b, crit in atom_pairs:
        if crit >= threshold and layer[a] != layer[b]:
            if a[0] == b[0]:
                inside += 1
            else:
                between += 1
    return inside, between


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("net", type=Path)
    parser.add_argument("criticality", type=Path)
    parser.add_argument("arch", type=Path)
    parser.add_argument("-o", "--output", type=Path, help="default: overwrite NET")
    parser.add_argument("--exponent", type=float, default=EXPONENT)
    parser.add_argument("--control", action="store_true",
                        help="control run: no FLE changes layer; each gets a random slot of its own layer (seed 1)")
    args = parser.parse_args()
    arch = read_arch(args.arch)
    tree, clbs, atom = load(args.net)
    adj = neighbours(args.criticality, atom, arch, args.exponent)
    layer = {(clb.index, s): arch["slot_layer"][s] for clb in clbs for s in clb.used}
    pairs = []
    for line in args.criticality.read_text().splitlines():
        if not line.startswith("#"):
            src, dst, crit = line.split("\t")
            a, b = atom.get(src), atom.get(dst)
            if a is not None and b is not None and a != b:
                pairs.append((a, b, float(crit)))
    before = total_cost(adj, layer)
    counts_before = [crossing_counts(adj, layer, pairs, t) for t in (0.9, 0.99)]
    moves = 0 if args.control else optimise(clbs, adj, arch, layer)
    after = total_cost(adj, layer)
    counts_after = [crossing_counts(adj, layer, pairs, t) for t in (0.9, 0.99)]
    before_conn = {clb.index: connectivity(clb, arch) for clb in clbs}
    chosen = {clb.fles[s].get("name"): layer[(clb.index, s)] for clb in clbs for s in clb.used}
    rng = random.Random(1) if args.control else None
    changed = sum(rewrite(clb, layer, arch, rng) for clb in clbs)
    for clb in clbs:
        reads, outs, legal = connectivity(clb, arch)
        old_reads, old_outs, old_legal = before_conn[clb.index]
        assert reads == old_reads and outs == old_outs, f"rewrite changed what {clb.block.get('instance')} connects"
        assert legal or not old_legal, f"rewrite broke layer legality in {clb.block.get('instance')}"
        for f in clb.block.findall("block"):
            if f.get("instance", "").startswith("fle[") and f.get("name") != "open":
                assert arch["slot_layer"][int(f.get("instance")[4:-1])] == chosen[f.get("name")], "FLE not on its layer"
    tree.write(args.output or args.net, encoding="unicode", xml_declaration=True)
    if args.control:
        print("layer_pass: CONTROL: every FLE kept on its layer, random slot within it")
    print(f"layer_pass: in-CLB crossing {arch['clb_crossing']:.2f} ps, routing crossing {arch['route_crossing']:.2f} ps, "
          f"exponent {args.exponent:g}")
    print(f"layer_pass: weighted crossing cost {before:.1f} -> {after:.1f}; {moves} FLE moves, {changed} of {len(clbs)} CLBs rewritten"
          f" ({sum(c.frozen for c in clbs)} left as packed: an empty FLE carries a signal)")
    for t, b, a in zip((0.9, 0.99), counts_before, counts_after):
        print(f"layer_pass: connections with criticality >= {t} crossing layers: in-CLB {b[0]} -> {a[0]}, between CLBs {b[1]} -> {a[1]}")


if __name__ == "__main__":
    main()
