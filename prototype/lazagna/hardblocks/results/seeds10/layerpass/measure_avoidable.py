#!/usr/bin/env python3
"""Layer crossings on the top paths of one routed run (split 20-FLE CLB or stacked 10-FLE CLB).

Reads RUN/report_timing.setup.rpt (--timing_report_detail detailed) and RUN/<bench>.net.
For each of the top N paths, every connection between two atoms is either
  intra: inside one CLB (no OPIN/IPIN between the two atom pins), crossing if the two FLEs
         sit on different layers (split: fle[0-9] layer 0, fle[10-19] layer 1);
  inter: through the routing, crossing count = layer changes along OPIN/CHAN/IPIN nodes.
For split runs it also says whether each crossing could have been avoided by changing
which layer an FLE sits on inside its CLB, holding every other CLB fixed:
  free : the CLB has a free FLE slot on the layer that would remove the crossing;
  swap : the CLB is full there, but an FLE on that layer is on none of the top N paths
         and could trade places (its own connections are not on the top paths);
  no   : neither (the other FLEs on that layer are all on top paths, or the end is a
         hard block / IO whose layer the packer does not choose).
With "joint" (measure_avoidable.py RUN N joint) it instead re-picks, per CLB, the layers of all its
top-path FLEs at once (10 per layer, the CLB's other FLEs filling the rest), other CLBs held fixed,
and reports how many top-path crossings that removes: an upper bound for these paths, since it
ignores every connection off them and placement and routing would change.
Step 1 of the layer-pass study (layerpass_results.txt); runs kept without --slim.
Usage: measure_avoidable.py RUN [N] [joint]
"""
import collections
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROW = re.compile(r"^(.*?)\s+(-?[\d.]+)\s+(-?[\d.]+)$")
NODE_LAYER = re.compile(r"\((\d+),(\d+),(\d+)\)?")
ATOM = re.compile(r"^(\S+)\.(\w+)\[(\d+)\] \(([^ ]+) at \((\d+), (\d+), (\d+)\)\)")


def load_net(net):
    """atom name -> (clb index, fle index); and per CLB the used FLE indices."""
    where, used = {}, {}
    root = ET.parse(net).getroot()
    for clb in root.findall("block"):
        inst = clb.get("instance", "")
        if not inst.startswith("clb[") or clb.get("name") == "open":
            continue
        c = int(inst[4:-1])
        used[c] = []
        for fle in clb.findall("block"):
            m = re.fullmatch(r"fle\[(\d+)\]", fle.get("instance", ""))
            if not m or fle.get("name") == "open":
                continue
            i = int(m.group(1))
            used[c].append(i)
            for leaf in fle.iter("block"):
                if leaf.get("instance") in ("lut6[0]", "ff[0]") and leaf.get("name") != "open":
                    where[leaf.get("name")] = (c, i)
    return where, used


def paths(report, n):
    text = report.read_text()
    blocks = re.split(r"\n#Path \d+\n", text)[1:n + 1]
    for block in blocks:
        arrival = block.split("data arrival time", 1)[0]
        rows = []
        for line in arrival.splitlines():
            m = ROW.match(line.strip())
            if m and not line.startswith(("clock", "Point")):
                rows.append((m.group(1).strip(), float(m.group(2))))
        start = next(i for i, (t, _) in enumerate(rows) if "[clock-to-output]" in t
                     or "(.input" in t and "clk" not in t.split()[0])
        slack = float(re.search(r"slack \(\w+\)\s+(-?[\d.]+)", block).group(1))
        yield rows[start:], slack


def connections(rows):
    """Split a data path into atom-to-atom connections: (src, dst, kind, nodes, delay)."""
    out, src, nodes, delay = [], None, [], 0.0
    for text, incr in rows:
        if text.startswith("|"):
            if src is not None and not text.startswith("| (primitive"):
                nodes.append(text)
                delay += incr
            continue
        m = ATOM.match(text)
        if not m:
            continue
        name, port, kind = m.group(1), m.group(2), m.group(4)
        if src is not None and port not in ("out", "Q") and "[clock-to-output]" not in text:
            routed = any(t.startswith(("| (OPIN", "| (IPIN", "| (CHAN")) for t in nodes)
            out.append((src, (name, kind), "inter" if routed else "intra", nodes, delay))
            src = None
        if port in ("out", "Q") or "[clock-to-output]" in text or kind == ".input":
            src, nodes, delay = (name, kind), [], 0.0
    return out


def route_crossings(nodes):
    count, last = 0, None
    for text in nodes:
        if not text.startswith(("| (OPIN", "| (IPIN", "| (CHAN")):
            continue
        layers = [int(z) for _, _, z in NODE_LAYER.findall(text)]
        if not layers:
            continue
        if text.startswith("| (OPIN"):
            last = layers[0]
        elif last is not None and layers[0] != last:
            count += 1
        last = layers[-1]
    return count


def main():
    run = Path(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    split = "instance_layer_offsets" in (run / "arch.xml").read_text()
    half = 10 if split else None
    net = next(run.glob("*.net"))
    where, used = load_net(net)
    layer = (lambda fle: int(fle >= half)) if split else (lambda fle: 0)
    all_paths = list(paths(run / "report_timing.setup.rpt", n))
    on_path = set()
    conns = []
    for rows, slack in all_paths:
        cs = connections(rows)
        conns.append((cs, slack))
        for src, dst, *_ in cs:
            on_path.update(x[0] for x in (src, dst) if x[0] in where)
    totals = collections.Counter()
    print(f"{run.name}: top {len(all_paths)} paths")
    print(f"{'path':>4} {'slack':>7} {'conns':>5} {'intra':>5} {'ixing':>5} {'inter':>5} {'rxing':>5}  avoidable(in-CLB/route): free swap no  hard/io-ends")
    for p, (cs, slack) in enumerate(conns, 1):
        c = collections.Counter()
        for src, dst, kind, nodes, delay in cs:
            c[kind] += 1
            if kind == "intra":
                a, b = where.get(src[0]), where.get(dst[0])
                if a is None or b is None or not split:
                    continue
                if layer(a[1]) != layer(b[1]):
                    c["ixing"] += 1
                    c["ixing_ps"] += delay
                    clb = a[0]
                    fles = used[clb]
                    free = {l: 10 - sum(layer(f) == l for f in fles) for l in (0, 1)}
                    # move dst to src's layer or src to dst's layer
                    if free[layer(a[1])] > 0 or free[layer(b[1])] > 0:
                        c["i_free"] += 1
                    else:
                        partners = [f for f in fles if f not in (a[1], b[1])]
                        names = {f: [k for k, v in where.items() if v == (clb, f)] for f in partners}
                        ok = any(layer(f) == layer(a[1]) and not any(x in on_path for x in names[f]) for f in partners) \
                            or any(layer(f) == layer(b[1]) and not any(x in on_path for x in names[f]) for f in partners)
                        c["i_swap" if ok else "i_no"] += 1
            else:
                x = route_crossings(nodes)
                c["rxing"] += x
                if x == 0:
                    continue
                a, b = where.get(src[0]), where.get(dst[0])
                if a is None and b is None:
                    c["r_hard"] += 1
                    continue
                if not split:
                    continue
                avoid = None
                for end, other in ((b, a), (a, b)):
                    if end is None:
                        continue
                    target = 1 - layer(end[1])  # moving this end to the other layer
                    fles = used[end[0]]
                    if sum(layer(f) == target for f in fles) < 10:
                        avoid = "free"
                        break
                    partners = [f for f in fles if layer(f) == target]
                    if any(not any(where.get(k) == (end[0], f) and k in on_path for k in on_path) for f in partners):
                        avoid = avoid or "swap"
                c["r_" + (avoid or "no")] += 1
                if a is None or b is None:
                    c["r_hardend"] += 1
        totals.update(c)
        print(f"{p:>4} {slack:7.3f} {c['intra'] + c['inter']:>5} {c['intra']:>5} {c['ixing']:>5} {c['inter']:>5} {c['rxing']:>5}"
              f"   {c['i_free']}/{c['r_free']} {c['i_swap']}/{c['r_swap']} {c['i_no']}/{c['r_no']}  {c['r_hard']}/{c['r_hardend']}")
    k = len(conns)
    print(f"mean per path: conns {(totals['intra'] + totals['inter']) / k:.1f}  intra {totals['intra'] / k:.1f}  in-CLB crossings {totals['ixing'] / k:.2f}"
          f"  inter {totals['inter'] / k:.1f}  routing crossings {totals['rxing'] / k:.2f}")
    print(f"in-CLB crossings: {totals['ixing']} (free slot {totals['i_free']}, swap {totals['i_swap']}, no {totals['i_no']})")
    print(f"routing-crossing connections: {totals['r_free'] + totals['r_swap'] + totals['r_no'] + totals['r_hard']} "
          f"(free slot {totals['r_free']}, swap {totals['r_swap']}, no {totals['r_no']}, both ends hard/io {totals['r_hard']}; "
          f"one end hard/io {totals['r_hardend']})")


if __name__ == "__main__":
    main()


def joint(run, n=10, cross_ps=(548.96, 211.62)):
    """Per CLB, re-pick the layers of its top-path FLEs (other FLEs fill the rest, 10 per layer),
    other CLBs held fixed, minimizing crossing delay summed over the top-N paths' connections;
    sweeps over CLBs until nothing improves. Hard blocks / IO keep the layer their pin used.
    Returns crossing counts before and after, and the crossing delay on path 1 before/after."""
    import itertools
    where, used = load_net(next(run.glob("*.net")))
    lay = {}  # atom-free FLE key (clb, fle) -> layer
    for c, fles in used.items():
        for f in fles:
            lay[(c, f)] = int(f >= 10)
    edges = []  # (path index, kind, src key, dst key)  key = (clb, fle) or ("pin", layer)
    for p, (rows, slack) in enumerate(paths(run / "report_timing.setup.rpt", n)):
        for src, dst, kind, nodes, delay in connections(rows):
            pins = [int(z) for t in nodes if t.startswith(("| (OPIN", "| (IPIN"))
                    for _, _, z in NODE_LAYER.findall(t)[:1]]
            a = where.get(src[0]); b = where.get(dst[0])
            if kind == "intra" and (a is None or b is None):
                continue
            ka = a if a else ("pin", pins[0] if pins else 0)
            kb = b if b else ("pin", pins[-1] if pins else 0)
            edges.append((p, kind, ka, kb))
    edges = list(dict.fromkeys(edges))
    L = lambda k: k[1] if k[0] == "pin" else lay[k]
    cost = lambda e: (cross_ps[0] if e[1] == "intra" else cross_ps[1]) * (L(e[2]) != L(e[3]))
    uniq = {(k, a, b) for _, k, a, b in edges}
    def count():
        return (sum(1 for k, a, b in uniq if k == "intra" and L(a) != L(b)),
                sum(1 for k, a, b in uniq if k == "inter" and L(a) != L(b)),
                sum(cost(e) for e in edges if e[0] == 0))
    before = count()
    clbs = sorted({k[0] for _, _, a, b in edges for k in (a, b) if k[0] != "pin"})
    for _ in range(10):
        changed = False
        for c in clbs:
            mine = sorted({k for _, _, a, b in edges for k in (a, b) if k[0] == c})
            if len(mine) > 16:
                continue
            touching = [e for e in edges if e[2] in mine or e[3] in mine]
            base = {k: lay[k] for k in mine}
            best, best_cost = None, None
            for bits in itertools.product((0, 1), repeat=len(mine)):
                ones = sum(bits)
                # the CLB's other FLEs fill whatever slots are left, so only these must fit
                if len(mine) - ones > 10 or ones > 10:
                    continue
                for k, v in zip(mine, bits):
                    lay[k] = v
                total = sum(cost(e) for e in touching)
                if best_cost is None or total < best_cost - 1e-9:
                    best, best_cost = bits, total
            for k in mine:
                lay[k] = base[k]
            now = sum(cost(e) for e in touching)
            if best_cost < now - 1e-9:
                for k, v in zip(mine, best):
                    lay[k] = v
                changed = True
        if not changed:
            break
    return before, count()


if __name__ == "__main__" and len(sys.argv) > 3 and sys.argv[3] == "joint":
    b, a = joint(Path(sys.argv[1]), int(sys.argv[2]))
    print(f"unique top-path connections crossing: in-CLB {b[0]} -> {a[0]}, routing {b[1]} -> {a[1]}; "
          f"crossing delay on path 1 {b[2]:.0f} -> {a[2]:.0f} ps")
