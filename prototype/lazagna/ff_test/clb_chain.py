#!/usr/bin/env python3
"""Works out the bits to shift into one CLB's config chain to load a design.

Follows the scan chain through the CLB netlist, from ccff_head through every
memory to ccff_tail, and reads each memory's value from OpenFPGA's preconfigured
testbench. Writes clb_config.txt: one bit per line, in the order they are shifted.
Usage: clb_chain.py <OpenFPGA Verilog folder> <CLB instance path in the formal testbench> <output>
"""
import pathlib
import re
import sys

TOP = "logical_tile_clb_mode_clb_"


def modules(source):
    found = {}
    for path in list(source.glob("lb/*.v")) + list(source.glob("sub_module/*.v")):
        text = path.read_text()
        for match in re.finditer(r"^\s*module\s+(\w+)", text, re.M):
            found[match.group(1)] = text[match.start():text.index("endmodule", match.start())]
    return found


def net(expr):
    return re.sub(r"\[0(:0)?\]$", "", expr.strip())


def chain(name, path, known):
    """Chain positions of one module instance, first to last: (memory path, bit)."""
    body = known[name]
    flops = re.findall(r"^\s*DFFR\s+(\w+)\s*\(", body, re.M)
    if flops:
        width = len(flops)
        return [(path, i) for i in range(width)]
    children = []
    for kind, inst in re.findall(r"^\s*(\w+)\s+(\w+)\s*\(", body, re.M):
        if kind in known:
            close = body.index(");", body.index(f"{kind} {inst}"))
            ports = dict((p, net(e)) for p, e in re.findall(r"\.(\w+)\(([^()]*)\)", body[body.index(f"{kind} {inst}"):close]))
            if "ccff_head" in ports:
                children.append((kind, inst, ports["ccff_head"], ports["ccff_tail"]))
    tail_net = "ccff_tail"
    assign = re.search(r"assign\s+ccff_tail(?:\[0\])?\s*=\s*([^;]+);", body)
    if assign:
        tail_net = net(assign.group(1))
    order, current = [], "ccff_head"
    while current != tail_net:
        step = [c for c in children if c[2] == current]
        if len(step) != 1:
            raise SystemExit(f"{name}: chain breaks at {current}")
        kind, inst, _, tail = step[0]
        order += chain(kind, f"{path}.{inst}" if path else inst, known)
        current = tail
    return order


def main():
    source, clb_path, output = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    known = modules(source)
    order = chain(TOP, "", known)
    formal = next(source.glob("*_top_formal_verification.v")).read_text()
    values = {}
    for path, bits in re.findall(rf"force\s+\S*{re.escape(clb_path)}\.(\S+)\.mem_out\[0:\d+\]\s*=\s*\{{?\d+'b([01]+)", formal):
        values[path] = bits
    missing = sorted({p for p, _ in order} - set(values))
    if missing:
        raise SystemExit(f"no value for {len(missing)} memories, e.g. {missing[:2]}")
    loaded = [values[p][i] for p, i in order]
    # The bit shifted in first ends at the far end of the chain.
    pathlib.Path(output).write_text("".join(f"{b}\n" for b in reversed(loaded)))
    print(f"{output}: {len(loaded)} bits, {loaded.count('1')} ones, {len({p for p, _ in order})} memories")


if __name__ == "__main__":
    main()
